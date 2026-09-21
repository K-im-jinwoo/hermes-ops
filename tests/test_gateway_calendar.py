from __future__ import annotations

import re

import telegram_gateway
from tools.calendar_approval import CalendarApprovalStore
from tools.task_selection import TaskSelectionStore


def _brief() -> dict:
    return {
        "period": "today",
        "referenceDate": "2026-09-18",
        "confirmed": [
            {
                "path": "wiki/10_Projects/hermes.md",
                "lineNumber": 20,
                "text": "Hermes 일정 기능 검증",
                "reason": "오늘 확정",
                "estimateMinutes": 90,
            }
        ],
        "carryOver": [],
        "recommended": [],
        "candidates": [],
        "scheduledLater": [],
        "onHold": [],
        "unknown": [],
    }


def _recommendation_brief() -> dict:
    brief = _brief()
    brief["confirmed"] = []
    brief["recommended"] = [
        {
            "path": f"wiki/10_Projects/project-{index}.md",
            "lineNumber": 10 + index,
            "text": f"추천 작업 {index}",
            "reason": "추천 이유",
            "estimateMinutes": None,
        }
        for index in range(1, 4)
    ]
    return brief


def _proposal() -> dict:
    return {
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


def test_today_plan_requires_preview_then_calendar_approval(monkeypatch, tmp_path):
    store = CalendarApprovalStore(tmp_path / "approvals.sqlite3")
    monkeypatch.setattr(telegram_gateway, "_get_calendar_approval_store", lambda: store)
    monkeypatch.setattr(telegram_gateway, "query_tasks", lambda **kwargs: _brief())
    monkeypatch.setattr(telegram_gateway, "propose_today_schedule", lambda brief: _proposal())
    created = []
    monkeypatch.setattr(
        telegram_gateway,
        "create_approved_events",
        lambda proposal: created.append(proposal) or {
            "calendarChecked": True,
            "created": [{"title": "Hermes 일정 기능 검증", "eventId": "event-1"}],
            "skipped": [],
            "failed": [],
        },
    )
    monkeypatch.setattr(telegram_gateway, "record_tool_event", lambda *args: None)

    preview = telegram_gateway.process_user_prompt(
        "오늘 할 일 정리하고 일정 추천해줘",
        user_id="user-1",
        chat_id="chat-1",
    )

    assert "아직 캘린더에는 생성하지 않았습니다" in preview
    assert created == []
    approval_id = re.search(r"C-[A-F0-9]{12}", preview).group(0)

    result = telegram_gateway.process_user_prompt(
        f"일정 승인 {approval_id}",
        user_id="user-1",
        chat_id="chat-1",
    )

    assert "생성 1건" in result
    assert len(created) == 1
    repeated = telegram_gateway.process_user_prompt(
        f"일정 승인 {approval_id}",
        user_id="user-1",
        chat_id="chat-1",
    )
    assert "이미 사용" in repeated


def test_calendar_approval_rejects_other_user(monkeypatch, tmp_path):
    store = CalendarApprovalStore(tmp_path / "approvals.sqlite3")
    monkeypatch.setattr(telegram_gateway, "_get_calendar_approval_store", lambda: store)
    monkeypatch.setattr(telegram_gateway, "query_tasks", lambda **kwargs: _brief())
    monkeypatch.setattr(telegram_gateway, "propose_today_schedule", lambda brief: _proposal())
    monkeypatch.setattr(telegram_gateway, "record_tool_event", lambda *args: None)

    preview = telegram_gateway.process_user_prompt(
        "오늘 할 일 정리하고 일정 추천해줘",
        user_id="user-1",
        chat_id="chat-1",
    )
    approval_id = re.search(r"C-[A-F0-9]{12}", preview).group(0)
    result = telegram_gateway.process_user_prompt(
        f"일정 승인 {approval_id}",
        user_id="user-2",
        chat_id="chat-1",
    )

    assert "다른 사용자" in result


def test_recommended_tasks_require_number_selection_before_calendar_preview(monkeypatch, tmp_path):
    database = tmp_path / "approvals.sqlite3"
    selection_store = TaskSelectionStore(database)
    approval_store = CalendarApprovalStore(database)
    monkeypatch.setattr(telegram_gateway, "_get_task_selection_store", lambda: selection_store)
    monkeypatch.setattr(telegram_gateway, "_get_calendar_approval_store", lambda: approval_store)
    monkeypatch.setattr(telegram_gateway, "query_tasks", lambda **kwargs: _recommendation_brief())
    proposed = []
    monkeypatch.setattr(
        telegram_gateway,
        "propose_today_schedule",
        lambda brief: proposed.append(brief) or _proposal(),
    )
    monkeypatch.setattr(telegram_gateway, "record_tool_event", lambda *args: None)

    recommendations = telegram_gateway.process_user_prompt(
        "오늘 할 일 정리하고 일정 추천해줘",
        user_id="user-1",
        chat_id="chat-1",
    )

    assert "오늘 확정 작업 0건, 이월 작업 0건" in recommendations
    assert "미지정(일정 생성 시 60분 가정)" in recommendations
    assert proposed == []
    selection_id = re.search(r"S-[A-F0-9]{12}", recommendations).group(0)

    preview = telegram_gateway.process_user_prompt(
        f"추천 선택 {selection_id} 1,3",
        user_id="user-1",
        chat_id="chat-1",
    )

    assert "아직 캘린더에는 생성하지 않았습니다" in preview
    assert [item["text"] for item in proposed[0]["recommended"]] == ["추천 작업 1", "추천 작업 3"]
    assert proposed[0]["confirmed"] == []
    assert re.search(r"C-[A-F0-9]{12}", preview)
