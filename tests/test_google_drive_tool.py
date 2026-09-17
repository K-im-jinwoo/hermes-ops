from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from tools.google_drive_tool import (
    DriveFile,
    GoogleDriveClient,
    GoogleDriveError,
    HttpResponse,
    load_google_drive_client,
)


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
    ) -> HttpResponse:
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "body": body,
            }
        )
        if url.startswith("https://oauth2.googleapis.com/token"):
            return HttpResponse(
                status=200,
                headers={"content-type": "application/json"},
                body=b'{"access_token":"access-1","expires_in":3600}',
            )

        path = urlparse(url).path
        if method == "GET" and path.endswith("/files"):
            return HttpResponse(
                status=200,
                headers={"content-type": "application/json"},
                body=json.dumps({"files": [{"id": "file-1", "name": "회의록.md", "mimeType": "text/markdown", "parents": ["folder-1"]}], "nextPageToken": "next"}).encode("utf-8"),
            )
        if method == "GET" and "/files/file-1" in path:
            return HttpResponse(status=200, headers={}, body="기존 내용".encode())
        if method == "POST" and "/upload/drive/v3/files" in path:
            return HttpResponse(
                status=200,
                headers={"content-type": "application/json"},
                body=json.dumps({"id": "file-2", "name": "새 메모.md", "mimeType": "text/markdown", "parents": ["folder-1"]}).encode("utf-8"),
            )
        if method == "POST" and path.endswith("/files"):
            return HttpResponse(
                status=200,
                headers={"content-type": "application/json"},
                body=json.dumps({"id": "folder-2", "name": "프로젝트", "mimeType": "application/vnd.google-apps.folder", "parents": ["root"]}).encode("utf-8"),
            )
        if method == "PATCH" and "/upload/drive/v3/files/file-1" in path:
            return HttpResponse(
                status=200,
                headers={"content-type": "application/json"},
                body=json.dumps({"id": "file-1", "name": "회의록.md", "mimeType": "text/markdown"}).encode("utf-8"),
            )
        if method == "PATCH" and "/drive/v3/files/file-1" in path:
            return HttpResponse(
                status=200,
                headers={"content-type": "application/json"},
                body=json.dumps({"id": "file-1", "name": "회의록-수정.md", "mimeType": "text/markdown"}).encode("utf-8"),
            )
        if method == "DELETE" and "/files/file-1" in path:
            return HttpResponse(status=204, headers={}, body=b"")
        raise AssertionError(f"unexpected request: {method} {url}")


def _credentials_file(tmp_path: Path) -> Path:
    path = tmp_path / "google-drive-credentials.json"
    path.write_text(
        json.dumps(
            {
                "client_id": "client-1",
                "client_secret": "secret-1",
                "refresh_token": "refresh-1",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        ),
        encoding="utf-8",
    )
    return path


def test_load_client_refreshes_token_once_and_reuses_it(tmp_path: Path):
    transport = FakeTransport()
    client = load_google_drive_client(
        credentials_path=_credentials_file(tmp_path),
        root_id="root",
        transport=transport,
    )

    client.list_files()
    client.list_files()

    token_calls = [call for call in transport.calls if "oauth2.googleapis.com/token" in str(call["url"])]
    drive_calls = [call for call in transport.calls if "googleapis.com/drive" in str(call["url"])]
    assert len(token_calls) == 1
    assert all(call["headers"]["Authorization"] == "Bearer access-1" for call in drive_calls)


def test_missing_credentials_fail_closed(tmp_path: Path):
    with pytest.raises(GoogleDriveError, match="자격 증명 파일"):
        load_google_drive_client(
            credentials_path=tmp_path / "missing.json",
            transport=FakeTransport(),
        )


def test_list_files_escapes_name_query_and_applies_parent(tmp_path: Path):
    transport = FakeTransport()
    client = load_google_drive_client(
        credentials_path=_credentials_file(tmp_path),
        transport=transport,
    )

    result = client.list_files(name_contains="O'Reilly", parent_id="folder-1", page_size=25)

    assert result == [
        DriveFile(
            file_id="file-1",
            name="회의록.md",
            mime_type="text/markdown",
            parents=("folder-1",),
            web_view_link=None,
        )
    ]
    request = next(call for call in transport.calls if call["method"] == "GET")
    params = parse_qs(urlparse(str(request["url"])).query)
    assert "name contains 'O\\'Reilly'" in params["q"][0]
    assert "'folder-1' in parents" in params["q"][0]
    assert params["pageSize"] == ["25"]


def test_read_create_update_delete_folder_and_move_use_drive_api(tmp_path: Path):
    transport = FakeTransport()
    client = load_google_drive_client(
        credentials_path=_credentials_file(tmp_path),
        root_id="root",
        transport=transport,
    )

    assert client.read_file("file-1") == "기존 내용"
    assert client.create_file("새 메모.md", "새 내용").file_id == "file-2"
    assert client.update_file("file-1", content="수정 내용", name="회의록-수정.md").file_id == "file-1"
    client.delete_file("file-1")
    assert client.create_folder("프로젝트").file_id == "folder-2"
    assert client.move_file("file-1", parent_id="folder-2", remove_parent_id="folder-1").file_id == "file-1"

    urls = [str(call["url"]) for call in transport.calls]
    assert any("alt=media" in url for url in urls)
    assert any("uploadType=multipart" in url for url in urls)
    assert any("uploadType=media" in url for url in urls)
    assert any("addParents=folder-2" in url and "removeParents=folder-1" in url for url in urls)
    assert any(call["method"] == "DELETE" for call in transport.calls)


def test_api_error_does_not_expose_authorization(tmp_path: Path):
    transport = FakeTransport()

    def failing_transport(method: str, url: str, headers: dict[str, str], body: bytes | None) -> HttpResponse:
        if url.startswith("https://oauth2.googleapis.com/token"):
            return HttpResponse(200, {}, b'{"access_token":"secret-access","expires_in":3600}')
        return HttpResponse(403, {}, b'{"error":{"message":"permission denied"}}')

    client = GoogleDriveClient(
        credentials_path=_credentials_file(tmp_path),
        transport=failing_transport,
    )

    with pytest.raises(GoogleDriveError) as error:
        client.list_files()

    assert error.value.status == 403
    assert "secret-access" not in str(error.value)
    assert "permission denied" in str(error.value)
