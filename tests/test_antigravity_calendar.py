from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

import pytest

from tools.antigravity_calendar import AntigravityCalendarError, create_approved_events, propose_today_schedule
from tools.google_calendar_tool import CalendarEvent, GoogleCalendarError


def _brief() -> dict:
    return {"referenceDate": "2026-09-18", "confirmed": [{"path": "wiki/hermes.md", "lineNumber": 20,
            "text": "Hermes 일정 기능 검증", "dueDate": "2026-09-18", "priority": "high",
            "estimateMinutes": 90, "reason": "오늘 확정 작업"}], "carryOver": [], "recommended": []}


class FakeCalendar:
    def __init__(self, events=None, fail=False):
        self.events = list(events or [])
        self.fail = fail
        self.calls = []

    def list_events(self, start, end):
        self.calls.append(("list", start, end))
        if self.fail:
            raise GoogleCalendarError("failed")
        return list(self.events)

    def create_event(self, title, start, end, *, description=""):
        self.calls.append(("create", title, start, end, description))
        return CalendarEvent("event-1", title, start, end)


def _runner_with(structured_output):
    calls = []
    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout=json.dumps(
            {"status": "SUCCESS", "structured_output": structured_output}), stderr="")
    return run, calls


def _proposal_output():
    return {"calendarChecked": True, "summary": "오전 집중 작업", "events": [{
        "sourceRef": "wiki/hermes.md#20", "title": "Hermes 일정 기능 검증",
        "start": "2026-09-18T09:00:00+09:00", "end": "2026-09-18T10:30:00+09:00",
        "description": "WIKI Task 기반", "reason": "마감 우선"}], "unscheduled": []}


def test_proposal_reads_calendar_before_antigravity_and_validates_output():
    runner, calls = _runner_with(_proposal_output())
    calendar = FakeCalendar([CalendarEvent("busy", "회의", "2026-09-18T11:00:00+09:00", "2026-09-18T12:00:00+09:00")])
    result = propose_today_schedule(_brief(), executable="agy", runner=runner, calendar_client=calendar)
    assert result == _proposal_output()
    assert calendar.calls[0][0] == "list"
    assert "[CALENDAR_EVENTS]" in calls[0][0][2]
    assert "도구나 셸 명령은 호출하지 마라" in calls[0][0][2]
    assert "--dangerously-skip-permissions" not in calls[0][0]


def test_proposal_fails_closed_when_calendar_read_fails():
    runner, _ = _runner_with(_proposal_output())
    with pytest.raises(AntigravityCalendarError, match="일정을 확인하지 못했습니다"):
        propose_today_schedule(_brief(), executable="agy", runner=runner, calendar_client=FakeCalendar(fail=True))


def test_proposal_rejects_event_during_lunch():
    output = _proposal_output()
    output["events"][0]["start"] = "2026-09-18T12:00:00+09:00"
    output["events"][0]["end"] = "2026-09-18T13:00:00+09:00"
    runner, _ = _runner_with(output)
    with pytest.raises(AntigravityCalendarError, match="점심시간"):
        propose_today_schedule(_brief(), executable="agy", runner=runner, calendar_client=FakeCalendar())


def test_proposal_uses_next_half_hour_and_rejects_past_slots():
    output = _proposal_output()
    output["events"][0]["start"] = "2026-09-18T10:00:00+09:00"
    output["events"][0]["end"] = "2026-09-18T11:00:00+09:00"
    runner, calls = _runner_with(output)
    calendar = FakeCalendar()

    with pytest.raises(AntigravityCalendarError, match="이미 지난 시간"):
        propose_today_schedule(
            _brief(),
            executable="agy",
            runner=runner,
            calendar_client=calendar,
            now=datetime(2026, 9, 18, 10, 1, tzinfo=timezone(timedelta(hours=9))),
        )

    assert calendar.calls[0][1] == "2026-09-18T10:30:00+09:00"
    assert "10:30~18:00" in calls[0][0][2]


def test_proposal_returns_no_events_after_business_hours():
    result = propose_today_schedule(
        _brief(),
        executable="agy",
        runner=lambda *args, **kwargs: pytest.fail("Antigravity must not run"),
        calendar_client=FakeCalendar(),
        now=datetime(2026, 9, 18, 18, 1, tzinfo=timezone(timedelta(hours=9))),
    )

    assert result["events"] == []
    assert "시간이 남아 있지 않습니다" in result["summary"]


def test_proposal_rejects_overlap_with_existing_calendar_event():
    output = _proposal_output()
    runner, _ = _runner_with(output)
    calendar = FakeCalendar([
        CalendarEvent(
            "busy",
            "기존 회의",
            "2026-09-18T09:30:00+09:00",
            "2026-09-18T10:00:00+09:00",
        )
    ])

    with pytest.raises(AntigravityCalendarError, match="기존 Google Calendar 일정과 겹치는"):
        propose_today_schedule(_brief(), executable="agy", runner=runner, calendar_client=calendar)


def test_approved_create_checks_exact_duplicate_before_write():
    proposal = {"events": _proposal_output()["events"]}
    calendar = FakeCalendar()
    result = create_approved_events(proposal, calendar_client=calendar)
    assert result["created"] == [{"title": "Hermes 일정 기능 검증", "eventId": "event-1"}]
    assert [call[0] for call in calendar.calls] == ["list", "create"]


def test_exact_duplicate_is_skipped_without_create():
    event = _proposal_output()["events"][0]
    calendar = FakeCalendar([CalendarEvent("existing", event["title"], event["start"], event["end"])])
    result = create_approved_events({"events": [event]}, calendar_client=calendar)
    assert result["created"] == []
    assert result["skipped"][0]["title"] == event["title"]
    assert [call[0] for call in calendar.calls] == ["list"]
