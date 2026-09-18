from __future__ import annotations

import re

import telegram_gateway
from tools.calendar_approval import CalendarApprovalStore


def _brief() -> dict:
    return {
        "period": "today",
        "referenceDate": "2026-09-18",
        "confirmed": [],
        "carryOver": [],
        "recommended": [],
        "candidates": [],
        "scheduledLater": [],
        "onHold": [],
        "unknown": [],
    }


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
