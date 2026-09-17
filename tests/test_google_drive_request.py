from __future__ import annotations

import pytest

from tools.google_drive_request import DriveAction, parse_google_drive_request


@pytest.mark.parametrize(
    ("prompt", "action", "file_id", "file_name", "folder_name", "parent_id"),
    [
        ("구글드라이브에서 파일명: 회의록.md 찾아줘", DriveAction.LIST, None, "회의록.md", None, None),
        ("Google Drive 파일 ID: abc123 읽어줘", DriveAction.READ, "abc123", None, None, None),
        ("GDrive에 파일명: 새 메모.md 내용: 오늘 결정사항 저장해줘", DriveAction.CREATE, None, "새 메모.md", None, None),
        ("구글드라이브 파일명: 회의록.md 내용: 수정된 본문 수정해줘", DriveAction.UPDATE, None, "회의록.md", None, None),
        ("구글드라이브 파일 ID: abc123 삭제해줘", DriveAction.DELETE, "abc123", None, None, None),
        ("구글드라이브에 폴더명: 프로젝트A 폴더 만들어줘", DriveAction.CREATE_FOLDER, None, None, "프로젝트A", None),
        ("구글드라이브 파일 ID: abc123를 상위 폴더 ID: folder-2로 옮겨줘", DriveAction.MOVE, "abc123", None, None, "folder-2"),
    ],
)
def test_parse_explicit_drive_operations(
    prompt: str,
    action: DriveAction,
    file_id: str | None,
    file_name: str | None,
    folder_name: str | None,
    parent_id: str | None,
):
    request = parse_google_drive_request(prompt)

    assert request is not None
    assert request.action is action
    assert request.file_id == file_id
    assert request.file_name == file_name
    assert request.folder_name == folder_name
    assert request.parent_id == parent_id


def test_parse_drive_content_and_search_query():
    create = parse_google_drive_request(
        '구글드라이브에 "회의록.md" 파일 내용: 오늘 회의에서 배포일을 확정했다 저장해줘'
    )
    search = parse_google_drive_request("구글드라이브에서 배포일 회의록 찾아줘")

    assert create is not None
    assert create.action is DriveAction.CREATE
    assert create.file_name == "회의록.md"
    assert create.content == "오늘 회의에서 배포일을 확정했다"
    assert search is not None
    assert search.action is DriveAction.LIST
    assert search.query == "배포일 회의록"


def test_unrecognized_drive_request_returns_none():
    assert parse_google_drive_request("구글드라이브 어떻게 써?") is None
