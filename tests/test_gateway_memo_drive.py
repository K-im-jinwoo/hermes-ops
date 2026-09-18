from tools.google_drive_tool import DriveFile
from tools.memo_store import MemoSaveStatus
import telegram_gateway


class DriveInbox:
    def __init__(self):
        self.notes = {}

    def list_files(self, *, parent_id=None, page_size=100):
        assert parent_id == "inbox-1"
        return [item[0] for item in self.notes.values()]

    def read_file(self, file_id):
        return self.notes[file_id][1]

    def create_file(self, name, content, *, parent_id=None):
        assert parent_id == "inbox-1"
        file = DriveFile("created-1", name, "text/markdown")
        self.notes[file.file_id] = (file, content)
        return file


def test_drive_memo_sink_saves_approved_content_in_configured_inbox(monkeypatch):
    drive = DriveInbox()
    monkeypatch.setenv("HERMES_MEMO_SINK", "drive")
    monkeypatch.setenv("GOOGLE_DRIVE_ROOT_ID", "inbox-1")
    monkeypatch.setattr(telegram_gateway, "_get_google_drive_client", lambda: drive)

    result = telegram_gateway._save_memo("메모를 저장해줘")

    assert result.status is MemoSaveStatus.CREATED
    assert len(drive.notes) == 1
    assert "메모를 저장해줘" in next(iter(drive.notes.values()))[1]


def test_drive_memo_sink_refuses_missing_inbox_id(monkeypatch):
    monkeypatch.setenv("HERMES_MEMO_SINK", "drive")
    monkeypatch.delenv("GOOGLE_DRIVE_ROOT_ID", raising=False)
    monkeypatch.setattr(
        telegram_gateway,
        "_get_google_drive_client",
        lambda: (_ for _ in ()).throw(AssertionError("client must not be created")),
    )

    result = telegram_gateway._save_memo("메모를 저장해줘")

    assert result.status is MemoSaveStatus.UNAVAILABLE
    assert "Google Drive" in telegram_gateway._format_memo_save_result(result)
