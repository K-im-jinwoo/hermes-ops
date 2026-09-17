from __future__ import annotations

import pytest

import telegram_gateway
from scripts.verify_tool_calling import TOOL_REGISTRY, TOOL_SCHEMAS
from tools.google_drive_tool import DriveFile, GoogleDriveError


class FakeDriveClient:
    def __init__(self, files: list[DriveFile] | None = None) -> None:
        self.files = files or [DriveFile("file-1", "회의록.md", "text/markdown")]
        self.calls: list[tuple[str, object]] = []

    def list_files(self, *, name_contains=None, parent_id=None, page_size=100):
        self.calls.append(("list", (name_contains, parent_id, page_size)))
        if name_contains:
            return [file for file in self.files if name_contains in file.name]
        return self.files

    def read_file(self, file_id):
        self.calls.append(("read", file_id))
        return "오늘 회의 본문"

    def create_file(self, name, content, *, parent_id=None, mime_type="text/markdown"):
        self.calls.append(("create", (name, content, parent_id, mime_type)))
        return DriveFile("created-1", name, mime_type, (parent_id,) if parent_id else ())

    def update_file(self, file_id, *, content=None, name=None, mime_type=None):
        self.calls.append(("update", (file_id, content, name, mime_type)))
        return DriveFile(file_id, name or "회의록.md", mime_type or "text/markdown")

    def delete_file(self, file_id):
        self.calls.append(("delete", file_id))

    def create_folder(self, name, *, parent_id=None):
        self.calls.append(("create_folder", (name, parent_id)))
        return DriveFile("folder-1", name, "application/vnd.google-apps.folder")

    def move_file(self, file_id, *, parent_id, remove_parent_id=None):
        self.calls.append(("move", (file_id, parent_id, remove_parent_id)))
        return DriveFile(file_id, "회의록.md", "text/markdown", (parent_id,))


def test_drive_list_and_read_use_the_client(monkeypatch):
    client = FakeDriveClient()
    monkeypatch.setattr(telegram_gateway, "_get_google_drive_client", lambda: client, raising=False)

    listed = telegram_gateway.process_user_prompt("구글드라이브에서 파일명: 회의록.md 찾아줘")
    read = telegram_gateway.process_user_prompt("Google Drive 파일 ID: file-1 읽어줘")

    assert "회의록.md" in listed
    assert "오늘 회의 본문" in read
    assert ("list", ("회의록.md", None, 100)) in client.calls
    assert ("read", "file-1") in client.calls


def test_drive_create_update_delete_folder_and_move_use_explicit_actions(monkeypatch):
    client = FakeDriveClient()
    monkeypatch.setattr(telegram_gateway, "_get_google_drive_client", lambda: client, raising=False)

    assert "생성" in telegram_gateway.process_user_prompt(
        "GDrive에 파일명: 새.md 내용: 본문 저장해줘"
    )
    assert "수정" in telegram_gateway.process_user_prompt(
        "구글드라이브 파일 ID: file-1 내용: 변경 본문 수정해줘"
    )
    assert "삭제" in telegram_gateway.process_user_prompt("구글드라이브 파일 ID: file-1 삭제해줘")
    assert "폴더" in telegram_gateway.process_user_prompt(
        "구글드라이브에 폴더명: 프로젝트 폴더 만들어줘"
    )
    assert "이동" in telegram_gateway.process_user_prompt(
        "구글드라이브 파일 ID: file-1 상위 폴더 ID: folder-1로 옮겨줘"
    )

    assert any(call[0] == "create" for call in client.calls)
    assert any(call[0] == "update" for call in client.calls)
    assert any(call[0] == "delete" for call in client.calls)
    assert any(call[0] == "create_folder" for call in client.calls)
    assert any(call[0] == "move" for call in client.calls)


def test_destructive_name_match_requires_exactly_one_file(monkeypatch):
    client = FakeDriveClient(
        files=[
            DriveFile("file-1", "회의록.md", "text/markdown"),
            DriveFile("file-2", "회의록.md", "text/markdown"),
        ]
    )
    monkeypatch.setattr(telegram_gateway, "_get_google_drive_client", lambda: client, raising=False)

    result = telegram_gateway.process_user_prompt("구글드라이브 파일명: 회의록.md 삭제해줘")

    assert "정확히 하나" in result
    assert not any(call[0] == "delete" for call in client.calls)


def test_missing_drive_credentials_are_reported_without_fallback(monkeypatch):
    def missing_credentials():
        raise GoogleDriveError("GOOGLE_DRIVE_CREDENTIALS_FILE이 설정되지 않았습니다.")

    monkeypatch.setattr(telegram_gateway, "_get_google_drive_client", missing_credentials, raising=False)

    result = telegram_gateway.process_user_prompt("구글드라이브에서 파일 목록 찾아줘")

    assert "자격" in result or "CREDENTIALS" in result
    assert "WIKI" not in result


def test_help_mentions_google_drive_operations():
    result = telegram_gateway.process_user_prompt("/help")

    assert "Google Drive" in result


def test_google_drive_operation_is_exposed_in_the_tool_registry():
    assert "google_drive" in TOOL_REGISTRY
    names = {schema["function"]["name"] for schema in TOOL_SCHEMAS}
    assert "google_drive" in names
