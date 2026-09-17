"""Natural-language parsing for explicit Hermes Google Drive operations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Optional


class DriveAction(str, Enum):
    LIST = "list"
    READ = "read"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    CREATE_FOLDER = "create_folder"
    MOVE = "move"


@dataclass(frozen=True)
class GoogleDriveRequest:
    action: DriveAction
    file_id: Optional[str] = None
    file_name: Optional[str] = None
    folder_name: Optional[str] = None
    parent_id: Optional[str] = None
    query: Optional[str] = None
    content: Optional[str] = None


_DRIVE_TERMS = ("구글드라이브", "google drive", "gdrive")
_QUOTED_VALUE = re.compile(r"[\"“”']([^\"“”']+)[\"“”']")
_FILE_ID = re.compile(r"(?:파일|file)\s*(?:id|아이디)\s*[:=]?\s*([A-Za-z0-9_-]+)", re.IGNORECASE)
_PARENT_ID = re.compile(r"(?:상위\s*폴더|부모\s*폴더|parent\s*folder)\s*(?:id|아이디)\s*[:=]?\s*([A-Za-z0-9_-]+)", re.IGNORECASE)
_FILE_NAME = re.compile(
    r"파일명\s*[:=]\s*(.+?)(?=\s+(?:내용|본문|찾아|검색|읽|열어|보여|만들|생성|수정|업데이트|삭제|지워|옮겨|이동)|$)",
    re.IGNORECASE,
)
_FOLDER_NAME = re.compile(
    r"폴더명\s*[:=]\s*(.+?)(?=\s+(?:폴더|찾아|검색|만들|생성|옮겨|이동)|$)",
    re.IGNORECASE,
)
_CONTENT = re.compile(
    r"(?:내용|본문)\s*[:=]\s*(.+?)(?=\s+(?:저장해줘|만들어줘|생성해줘|수정해줘|업데이트해줘)\s*$|$)",
    re.IGNORECASE,
)


def parse_google_drive_request(prompt: str) -> Optional[GoogleDriveRequest]:
    cleaned = prompt.strip()
    lowered = cleaned.casefold()
    if not cleaned or not any(term in lowered for term in _DRIVE_TERMS):
        return None

    action = _detect_action(lowered)
    if action is None:
        return None

    file_id = _match_value(_FILE_ID, cleaned)
    parent_id = _match_value(_PARENT_ID, cleaned)
    file_name = _match_value(_FILE_NAME, cleaned)
    folder_name = _match_value(_FOLDER_NAME, cleaned)
    content = _match_value(_CONTENT, cleaned)

    quoted_values = _QUOTED_VALUE.findall(cleaned)
    if file_name is None and action not in {DriveAction.CREATE_FOLDER} and quoted_values:
        file_name = quoted_values[0].strip()
    if folder_name is None and action is DriveAction.CREATE_FOLDER and quoted_values:
        folder_name = quoted_values[0].strip()

    query = file_name or _search_query(cleaned)
    return GoogleDriveRequest(
        action=action,
        file_id=file_id,
        file_name=_clean_optional(file_name),
        folder_name=_clean_optional(folder_name),
        parent_id=_clean_optional(parent_id),
        query=_clean_optional(query),
        content=_clean_optional(content),
    )


def _detect_action(lowered: str) -> Optional[DriveAction]:
    if "폴더" in lowered and any(phrase in lowered for phrase in ("만들", "생성", "새 폴더")):
        return DriveAction.CREATE_FOLDER
    if any(phrase in lowered for phrase in ("옮겨", "이동", "move")):
        return DriveAction.MOVE
    if any(phrase in lowered for phrase in ("삭제", "지워", "delete")):
        return DriveAction.DELETE
    if any(phrase in lowered for phrase in ("수정", "업데이트", "바꿔", "update")):
        return DriveAction.UPDATE
    if any(phrase in lowered for phrase in ("만들", "생성", "작성", "업로드", "저장", "create")):
        return DriveAction.CREATE
    if any(phrase in lowered for phrase in ("읽", "열어", "내용 보여", "내용 알려", "read")):
        return DriveAction.READ
    if any(phrase in lowered for phrase in ("찾아", "검색", "목록", "조회", "뭐 있어", "list")):
        return DriveAction.LIST
    return None


def _match_value(pattern: re.Pattern[str], text: str) -> Optional[str]:
    match = pattern.search(text)
    return match.group(1).strip() if match else None


def _search_query(text: str) -> Optional[str]:
    query = text
    for term in _DRIVE_TERMS:
        query = re.sub(re.escape(term), " ", query, flags=re.IGNORECASE)
    query = re.sub(
        r"(?:파일\s*id|파일명|파일|문서|폴더명|상위\s*폴더\s*id|폴더)\s*[:=]?",
        " ",
        query,
        flags=re.IGNORECASE,
    )
    query = re.sub(
        r"(?:찾아줘|검색해줘|목록\s*(?:보여줘|알려줘)?|조회해줘|읽어줘|열어줘|보여줘|뭐\s*있어\??|어떻게\s*써\??)",
        " ",
        query,
        flags=re.IGNORECASE,
    )
    query = re.sub(r"\b(?:에서|에|의|을|를|이|가|로|으로)\b", " ", query)
    query = re.sub(r"[,:?]", " ", query)
    query = " ".join(query.split())
    return query or None


def _clean_optional(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = value.strip().strip("'\"“”")
    return cleaned or None
