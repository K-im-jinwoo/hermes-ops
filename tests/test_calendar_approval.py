from datetime import datetime, timedelta, timezone

from tools.calendar_approval import CalendarApprovalStore


def test_calendar_approval_is_identity_bound_and_consumed_once(tmp_path):
    store = CalendarApprovalStore(tmp_path / "approvals.sqlite3", ttl_seconds=600)
    now = datetime(2026, 9, 18, tzinfo=timezone.utc)
    proposal = {"events": [{"title": "검토"}]}
    pending = store.issue(user_id="u1", chat_id="c1", proposal=proposal, now=now)

    assert pending.approval_id.startswith("C-")
    assert store.consume(pending.approval_id, user_id="u2", chat_id="c1", now=now) is None
    consumed = store.consume(pending.approval_id, user_id="u1", chat_id="c1", now=now)
    assert consumed is not None
    assert consumed.proposal == proposal
    assert store.consume(pending.approval_id, user_id="u1", chat_id="c1", now=now) is None


def test_calendar_approval_expires(tmp_path):
    store = CalendarApprovalStore(tmp_path / "approvals.sqlite3", ttl_seconds=60)
    now = datetime(2026, 9, 18, tzinfo=timezone.utc)
    pending = store.issue(user_id="u", chat_id="c", proposal={"events": []}, now=now)

    assert store.consume(
        pending.approval_id,
        user_id="u",
        chat_id="c",
        now=now + timedelta(seconds=60),
    ) is None
