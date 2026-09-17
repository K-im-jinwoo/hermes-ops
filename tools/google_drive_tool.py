"""Direct Google Drive v3 REST client for Hermes.

The client deliberately depends only on the Python standard library. Runtime
credentials are loaded from a file outside the repository and access tokens
are cached in memory for the life of the process.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import time
from typing import Callable, Mapping, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
import uuid


DEFAULT_DRIVE_API_URL = "https://www.googleapis.com/drive/v3"
DEFAULT_UPLOAD_API_URL = "https://www.googleapis.com/upload/drive/v3"
DEFAULT_TOKEN_URI = "https://oauth2.googleapis.com/token"
DEFAULT_FILE_FIELDS = "id,name,mimeType,parents,webViewLink"
FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"

Transport = Callable[[str, str, dict[str, str], Optional[bytes]], "HttpResponse"]


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


class GoogleDriveError(RuntimeError):
    """Safe, user-facing Drive failure that never contains auth headers."""

    def __init__(self, message: str, *, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class DriveFile:
    file_id: str
    name: str
    mime_type: str
    parents: tuple[str, ...] = ()
    web_view_link: Optional[str] = None


def _default_transport(
    method: str,
    url: str,
    headers: dict[str, str],
    body: Optional[bytes],
) -> HttpResponse:
    request = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            return HttpResponse(
                status=response.status,
                headers=dict(response.headers.items()),
                body=response.read(),
            )
    except HTTPError as error:
        return HttpResponse(
            status=error.code,
            headers=dict(error.headers.items()),
            body=error.read(),
        )
    except URLError as error:
        raise GoogleDriveError(f"Google Drive 네트워크 요청에 실패했습니다: {error.reason}") from error
    except OSError as error:
        raise GoogleDriveError(f"Google Drive 요청에 실패했습니다: {error}") from error


class _OAuthTokenProvider:
    def __init__(
        self,
        credentials_path: Path,
        *,
        transport: Transport,
        clock: Callable[[], float],
    ) -> None:
        self._credentials_path = credentials_path
        self._transport = transport
        self._clock = clock
        self._credentials = self._read_credentials(credentials_path)
        self._access_token: Optional[str] = self._credentials.get("access_token")
        self._expires_at = 0.0

    @staticmethod
    def _read_credentials(path: Path) -> dict[str, str]:
        if not path.is_file():
            raise GoogleDriveError(f"Google Drive 자격 증명 파일을 찾을 수 없습니다: {path}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise GoogleDriveError("Google Drive 자격 증명 파일을 읽을 수 없습니다.") from error
        if not isinstance(payload, dict):
            raise GoogleDriveError("Google Drive 자격 증명 파일 형식이 올바르지 않습니다.")

        required = ("client_id", "client_secret", "refresh_token")
        if any(not isinstance(payload.get(key), str) or not payload[key] for key in required):
            raise GoogleDriveError(
                "Google Drive 자격 증명에는 client_id, client_secret, refresh_token이 필요합니다."
            )
        return {str(key): str(value) for key, value in payload.items() if isinstance(value, (str, int, float))}

    def get_access_token(self) -> str:
        if self._access_token and self._expires_at > self._clock() + 60:
            return self._access_token

        token_uri = self._credentials.get("token_uri", DEFAULT_TOKEN_URI)
        form = urlencode(
            {
                "client_id": self._credentials["client_id"],
                "client_secret": self._credentials["client_secret"],
                "refresh_token": self._credentials["refresh_token"],
                "grant_type": "refresh_token",
            }
        ).encode("utf-8")
        response = self._transport(
            "POST",
            token_uri,
            {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            form,
        )
        payload = _parse_json(response.body)
        if not 200 <= response.status < 300:
            raise GoogleDriveError(
                _safe_error_message(payload, "Google Drive 토큰 갱신에 실패했습니다."),
                status=response.status,
            )

        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise GoogleDriveError("Google Drive 토큰 응답에 access_token이 없습니다.")
        try:
            expires_in = float(payload.get("expires_in", 3600))
        except (TypeError, ValueError):
            expires_in = 3600.0
        self._access_token = access_token
        self._expires_at = self._clock() + max(60.0, expires_in)
        return access_token


class GoogleDriveClient:
    def __init__(
        self,
        credentials_path: Path | str,
        *,
        root_id: Optional[str] = None,
        transport: Optional[Transport] = None,
        clock: Callable[[], float] = time.time,
        drive_api_url: str = DEFAULT_DRIVE_API_URL,
        upload_api_url: str = DEFAULT_UPLOAD_API_URL,
    ) -> None:
        self._transport = transport or _default_transport
        self._drive_api_url = drive_api_url.rstrip("/")
        self._upload_api_url = upload_api_url.rstrip("/")
        self._root_id = root_id.strip() if root_id and root_id.strip() else None
        self._token_provider = _OAuthTokenProvider(
            Path(credentials_path),
            transport=self._transport,
            clock=clock,
        )

    def list_files(
        self,
        *,
        name_contains: Optional[str] = None,
        parent_id: Optional[str] = None,
        page_size: int = 100,
    ) -> list[DriveFile]:
        clauses = ["trashed = false"]
        effective_parent = parent_id or self._root_id
        if effective_parent:
            clauses.append(f"{_drive_query_literal(effective_parent)} in parents")
        if name_contains and name_contains.strip():
            clauses.append(f"name contains {_drive_query_literal(name_contains.strip())}")

        response = self._request(
            "GET",
            f"{self._drive_api_url}/files",
            params={
                "q": " and ".join(clauses),
                "pageSize": str(max(1, min(page_size, 1000))),
                "orderBy": "name",
                "fields": f"files({DEFAULT_FILE_FIELDS})",
            },
        )
        payload = _parse_json(response.body)
        files = payload.get("files", [])
        if not isinstance(files, list):
            return []
        return [_drive_file(item) for item in files if isinstance(item, dict)]

    def read_file(self, file_id: str) -> str:
        clean_id = _require_id(file_id)
        response = self._request(
            "GET",
            f"{self._drive_api_url}/files/{quote(clean_id, safe='')}",
            params={"alt": "media"},
        )
        try:
            return response.body.decode("utf-8")
        except UnicodeDecodeError as error:
            raise GoogleDriveError("Drive 파일이 UTF-8 텍스트가 아니어서 읽을 수 없습니다.") from error

    def create_file(
        self,
        name: str,
        content: str,
        *,
        parent_id: Optional[str] = None,
        mime_type: str = "text/markdown",
    ) -> DriveFile:
        clean_name = _require_text(name, "파일명")
        if not isinstance(content, str):
            raise GoogleDriveError("파일 내용은 문자열이어야 합니다.")
        metadata = self._metadata(clean_name, mime_type, parent_id)
        boundary = f"hermes-{uuid.uuid4().hex}"
        body = _multipart_body(metadata, mime_type, content.encode("utf-8"), boundary)
        response = self._request(
            "POST",
            f"{self._upload_api_url}/files",
            params={"uploadType": "multipart", "fields": DEFAULT_FILE_FIELDS},
            body=body,
            extra_headers={"Content-Type": f'multipart/related; boundary="{boundary}"'},
        )
        return _drive_file(_parse_json(response.body))

    def update_file(
        self,
        file_id: str,
        *,
        content: Optional[str] = None,
        name: Optional[str] = None,
        mime_type: Optional[str] = None,
    ) -> DriveFile:
        clean_id = _require_id(file_id)
        if content is None and name is None and mime_type is None:
            raise GoogleDriveError("수정할 파일 내용이나 이름이 필요합니다.")

        result: Optional[DriveFile] = None
        if name is not None or mime_type is not None:
            metadata = {}
            if name is not None:
                metadata["name"] = _require_text(name, "파일명")
            if mime_type is not None:
                metadata["mimeType"] = _require_text(mime_type, "MIME 타입")
            response = self._request(
                "PATCH",
                f"{self._drive_api_url}/files/{quote(clean_id, safe='')}",
                params={"fields": DEFAULT_FILE_FIELDS},
                body=json.dumps(metadata, ensure_ascii=False).encode("utf-8"),
                extra_headers={"Content-Type": "application/json; charset=utf-8"},
            )
            result = _drive_file(_parse_json(response.body))

        if content is not None:
            response = self._request(
                "PATCH",
                f"{self._upload_api_url}/files/{quote(clean_id, safe='')}",
                params={"uploadType": "media", "fields": DEFAULT_FILE_FIELDS},
                body=content.encode("utf-8"),
                extra_headers={"Content-Type": mime_type or "text/markdown"},
            )
            result = _drive_file(_parse_json(response.body))

        if result is None:
            raise GoogleDriveError("파일 수정 결과를 확인할 수 없습니다.")
        return result

    def delete_file(self, file_id: str) -> None:
        clean_id = _require_id(file_id)
        self._request(
            "DELETE",
            f"{self._drive_api_url}/files/{quote(clean_id, safe='')}",
        )

    def create_folder(self, name: str, *, parent_id: Optional[str] = None) -> DriveFile:
        clean_name = _require_text(name, "폴더명")
        metadata = self._metadata(clean_name, FOLDER_MIME_TYPE, parent_id)
        response = self._request(
            "POST",
            f"{self._drive_api_url}/files",
            params={"fields": DEFAULT_FILE_FIELDS},
            body=json.dumps(metadata, ensure_ascii=False).encode("utf-8"),
            extra_headers={"Content-Type": "application/json; charset=utf-8"},
        )
        return _drive_file(_parse_json(response.body))

    def move_file(
        self,
        file_id: str,
        *,
        parent_id: str,
        remove_parent_id: Optional[str] = None,
    ) -> DriveFile:
        clean_id = _require_id(file_id)
        clean_parent = _require_id(parent_id)
        params = {"addParents": clean_parent, "fields": DEFAULT_FILE_FIELDS}
        if remove_parent_id:
            params["removeParents"] = _require_id(remove_parent_id)
        response = self._request(
            "PATCH",
            f"{self._drive_api_url}/files/{quote(clean_id, safe='')}",
            params=params,
        )
        return _drive_file(_parse_json(response.body))

    def _metadata(self, name: str, mime_type: str, parent_id: Optional[str]) -> dict[str, object]:
        metadata: dict[str, object] = {"name": name, "mimeType": mime_type}
        effective_parent = parent_id or self._root_id
        if effective_parent:
            metadata["parents"] = [_require_id(effective_parent)]
        return metadata

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: Optional[Mapping[str, str]] = None,
        body: Optional[bytes] = None,
        extra_headers: Optional[Mapping[str, str]] = None,
    ) -> HttpResponse:
        if params:
            url = f"{url}?{urlencode(params)}"
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._token_provider.get_access_token()}",
        }
        if body is not None:
            headers["Content-Length"] = str(len(body))
        if extra_headers:
            headers.update(extra_headers)
        response = self._transport(method, url, headers, body)
        if not 200 <= response.status < 300:
            payload = _parse_json(response.body)
            raise GoogleDriveError(
                _safe_error_message(payload, "Google Drive 요청이 거부되었습니다."),
                status=response.status,
            )
        return response


def load_google_drive_client(
    *,
    credentials_path: Optional[Path | str] = None,
    root_id: Optional[str] = None,
    transport: Optional[Transport] = None,
) -> GoogleDriveClient:
    configured_path = credentials_path or os.getenv("GOOGLE_DRIVE_CREDENTIALS_FILE")
    if not configured_path:
        raise GoogleDriveError("GOOGLE_DRIVE_CREDENTIALS_FILE이 설정되지 않았습니다.")
    configured_root = root_id if root_id is not None else os.getenv("GOOGLE_DRIVE_ROOT_ID")
    return GoogleDriveClient(
        configured_path,
        root_id=configured_root,
        transport=transport,
    )


def _drive_file(payload: Mapping[str, object]) -> DriveFile:
    file_id = payload.get("id")
    name = payload.get("name")
    mime_type = payload.get("mimeType")
    if not all(isinstance(value, str) and value for value in (file_id, name, mime_type)):
        raise GoogleDriveError("Google Drive 응답에 파일 식별 정보가 없습니다.")
    parents_value = payload.get("parents", [])
    parents = tuple(item for item in parents_value if isinstance(item, str)) if isinstance(parents_value, list) else ()
    web_view_link = payload.get("webViewLink")
    return DriveFile(
        file_id=file_id,
        name=name,
        mime_type=mime_type,
        parents=parents,
        web_view_link=web_view_link if isinstance(web_view_link, str) else None,
    )


def _parse_json(body: bytes) -> dict[str, object]:
    if not body:
        return {}
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _safe_error_message(payload: Mapping[str, object], fallback: str) -> str:
    error = payload.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message:
            return message[:300]
    message = payload.get("message")
    if isinstance(message, str) and message:
        return message[:300]
    return fallback


def _drive_query_literal(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _require_id(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GoogleDriveError("Google Drive 파일 또는 폴더 ID가 필요합니다.")
    return value.strip()


def _require_text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GoogleDriveError(f"Google Drive {label}이(가) 필요합니다.")
    return value.strip()


def _multipart_body(metadata: Mapping[str, object], mime_type: str, content: bytes, boundary: str) -> bytes:
    metadata_bytes = json.dumps(metadata, ensure_ascii=False).encode("utf-8")
    return (
        f"--{boundary}\r\n".encode("ascii")
        + b"Content-Type: application/json; charset=UTF-8\r\n\r\n"
        + metadata_bytes
        + f"\r\n--{boundary}\r\n".encode("ascii")
        + f"Content-Type: {mime_type}\r\n\r\n".encode("ascii")
        + content
        + f"\r\n--{boundary}--\r\n".encode("ascii")
    )
