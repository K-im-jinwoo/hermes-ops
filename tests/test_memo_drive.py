from datetime import datetime, timezone

from tools.google_drive_tool import DriveFile, GoogleDriveError
from tools.memo_store import MemoSaveStatus
from tools.memo_drive import save_memo_to_drive_inbox


class InMemoryDrive:
    def __init__(self):
        self.files = {}
        self.created = 0
        self.fail_read = False
        self.parents_seen = []

    def list_files(self, *, parent_id=None, page_size=100):
        self.parents_seen.append(parent_id)
        return [item[0] for item in self.files.values()]

    def read_file(self, file_id):
        if self.fail_read:
            raise GoogleDriveError("read unavailable")
        return self.files[file_id][1]

    def create_file(self, name, content, *, parent_id=None):
        self.parents_seen.append(parent_id)
        self.created += 1
        file = DriveFile(f"file-{self.created}", name, "text/markdown")
        self.files[file.file_id] = (file, content)
        return file


WHEN = datetime(2026, 9, 18, 0, 0, tzinfo=timezone.utc)


def test_approved_memo_creates_one_draft_in_drive_inbox():
    drive = InMemoryDrive()

    result = save_memo_to_drive_inbox("회의 결정", client=drive, inbox_id="inbox-1", now=WHEN)

    assert result.status is MemoSaveStatus.CREATED
    assert str(result.path).replace("\\", "/").startswith("wiki/00_Inbox/2026-09-18_0900_")
    assert len(drive.files) == 1
    assert drive.parents_seen == ["inbox-1", "inbox-1"]
    note = next(iter(drive.files.values()))[1]
    assert "type: inbox\nstatus: draft" in note
    assert "source: telegram" in note
    assert note.endswith("# 회의 결정\n\n회의 결정\n")


def test_same_content_is_duplicate_without_second_create():
    drive = InMemoryDrive()
    first = save_memo_to_drive_inbox("회의 결정", client=drive, inbox_id="inbox-1", now=WHEN)

    second = save_memo_to_drive_inbox("회의 결정", client=drive, inbox_id="inbox-1", now=WHEN)

    assert first.status is MemoSaveStatus.CREATED
    assert second.status is MemoSaveStatus.DUPLICATE
    assert drive.created == 1


def test_same_title_with_different_content_needs_review():
    drive = InMemoryDrive()
    drive.files["old"] = (
        DriveFile("old", "기존.md", "text/markdown"),
        "---\ntype: inbox\n---\n\n# 회의 결정\n\n다른 내용\n",
    )

    result = save_memo_to_drive_inbox("회의 결정", client=drive, inbox_id="inbox-1", now=WHEN)

    assert result.status is MemoSaveStatus.NEEDS_REVIEW
    assert drive.created == 0


def test_unreadable_existing_note_fails_closed():
    drive = InMemoryDrive()
    drive.files["old"] = (DriveFile("old", "기존.md", "text/markdown"), "content")
    drive.fail_read = True

    result = save_memo_to_drive_inbox("새 메모", client=drive, inbox_id="inbox-1", now=WHEN)

    assert result.status is MemoSaveStatus.UNAVAILABLE
    assert drive.created == 0
