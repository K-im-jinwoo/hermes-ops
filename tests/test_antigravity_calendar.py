from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from tools.antigravity_calendar import (
    AntigravityCalendarError,
    create_approved_events,
    propose_today_schedule,
)


def _brief() -> dict:
    return {
        "referenceDate": "2026-09-18",
        "confirmed": [
            {
                "path": "wiki/10_Projects/hermes.md",
                "lineNumber": 20,
                "text": "Hermes 일정 기능 검증",
                "dueDate": "2026-09-18",
                "priority": "high",
                "estimateMinutes": 90,
                "reason": "오늘 확정 작업",
            }
        ],
        "carryOver": [],
        "recommended": [],
    }


def _runner_with(structured_output):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        if command[1:3] == ["mcp", "list"]:
            return SimpleNamespace(returncode=0, stdout="calendar enabled", stderr="")
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"status": "SUCCESS", "structured_output": structured_output}),
            stderr="",
        )

    return run, calls


def test_proposal_reads_calendar_and_returns_validated_events():
    output = {
        "calendarChecked": True,
        "summary": "오전 집중 작업",
        "events": [
            {
                "sourceRef": "wiki/10_Projects/hermes.md#20",
                "title": "Hermes 일정 기능 검증",
                "start": "2026-09-18T09:00:00+09:00",
                "end": "2026-09-18T10:30:00+09:00",
                "description": "WIKI Task 기반",
                "reason": "마감 및 우선순위가 높음",
            }
        ],
        "unscheduled": [],
    }
    runner, calls = _runner_with(output)

    result = propose_today_schedule(_brief(), executable="agy", runner=runner)

    assert result == output
    command = calls[1][0]
    assert "--dangerously-skip-permissions" not in command
    assert "--json-schema" in command
    assert "create_event" in command[2]
    assert "절대 호출하지 마라" in command[2]


def test_proposal_fails_closed_when_calendar_was_not_checked():
    output = {"calendarChecked": False, "summary": "", "events": [], "unscheduled": []}
    runner, _ = _runner_with(output)

    with pytest.raises(AntigravityCalendarError, match="권한 또는 인증"):
        propose_today_schedule(_brief(), executable="agy", runner=runner)


def test_proposal_rejects_event_during_lunch():
    output = {
        "calendarChecked": True,
        "summary": "점심 일정",
        "events": [
            {
                "sourceRef": "wiki/10_Projects/hermes.md#20",
                "title": "Hermes 일정 기능 검증",
                "start": "2026-09-18T12:00:00+09:00",
                "end": "2026-09-18T13:00:00+09:00",
                "description": "WIKI Task 기반",
                "reason": "추천",
            }
        ],
        "unscheduled": [],
    }
    runner, _ = _runner_with(output)

    with pytest.raises(AntigravityCalendarError, match="점심 시간"):
        propose_today_schedule(_brief(), executable="agy", runner=runner)


def test_create_approved_events_checks_duplicates_before_create():
    proposal = {
        "events": [
            {
                "sourceRef": "wiki/10_Projects/hermes.md#20",
                "title": "Hermes 일정 기능 검증",
                "start": "2026-09-18T09:00:00+09:00",
                "end": "2026-09-18T10:30:00+09:00",
                "description": "WIKI Task 기반",
                "reason": "마감 및 우선순위가 높음",
            }
        ]
    }
    output = {
        "calendarChecked": True,
        "created": [{"title": "Hermes 일정 기능 검증", "eventId": "event-1"}],
        "skipped": [],
        "failed": [],
    }
    runner, calls = _runner_with(output)

    result = create_approved_events(proposal, executable="agy", runner=runner)

    assert result["created"][0]["eventId"] == "event-1"
    assert "같은 시작·종료 시각과 제목" in calls[1][0][2]


def test_missing_calendar_mcp_is_reported_before_model_run():
    def runner(command, **kwargs):
        return SimpleNamespace(returncode=0, stdout="No MCP servers configured.", stderr="")

    with pytest.raises(AntigravityCalendarError, match="calendar MCP"):
        propose_today_schedule(_brief(), executable="agy", runner=runner)
