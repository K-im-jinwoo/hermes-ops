from __future__ import annotations

from pathlib import Path
import re

import pytest

import telegram_gateway
from tools.memo_approval import MemoApprovalStore
from tools.memo_store import MemoSaveResult, MemoSaveStatus


def test_ambiguous_prompt_is_not_sent_to_codex(monkeypatch):
    def unexpected_codex_call(*args, **kwargs):
        pytest.fail("ambiguous prompt must not fall through to Codex")

    monkeypatch.setattr(telegram_gateway, "ask_codex", unexpected_codex_call)

    result = telegram_gateway.process_user_prompt("그거 좀 확인해줘")

    assert "어떤 작업인지" in result


def test_help_mentions_natural_language_memo_saving():
    result = telegram_gateway.process_user_prompt("/help")

    assert "메모 저장" in result


def test_memo_request_returns_preview_and_approval_id_without_writing(monkeypatch, tmp_path):
    store = MemoApprovalStore(tmp_path / "approvals.sqlite3")

    def unexpected_save(*args, **kwargs):
        pytest.fail("memo request must wait for approval before saving")

    monkeypatch.setattr(telegram_gateway, "_get_memo_approval_store", lambda: store)
    monkeypatch.setattr(telegram_gateway, "_save_memo", unexpected_save)
    monkeypatch.setattr(
        telegram_gateway,
        "wiki_search",
        lambda *args, **kwargs: pytest.fail("memo request must not search WIKI"),
    )

    result = telegram_gateway.process_user_prompt(
        "회의 내용을 WIKI에 기록해줘",
        user_id="user-1",
        chat_id="chat-1",
    )

    assert "아직 저장하지 않았습니다" in result
    assert "wiki/00_Inbox" in result
    assert re.search(r"H-[A-F0-9]{12}", result)


def test_memo_approval_consumes_id_once_and_then_saves(monkeypatch, tmp_path):
    store = MemoApprovalStore(tmp_path / "approvals.sqlite3")
    calls = []

    def save_memo(prompt):
        calls.append(prompt)
        return MemoSaveResult(
            MemoSaveStatus.CREATED,
            path=Path("wiki/00_Inbox/2026-09-17_1405_회의-내용.md"),
        )

    monkeypatch.setattr(telegram_gateway, "_get_memo_approval_store", lambda: store)
    monkeypatch.setattr(telegram_gateway, "_save_memo", save_memo)

    preview = telegram_gateway.process_user_prompt(
        "회의 내용을 WIKI에 기록해줘",
        user_id="user-1",
        chat_id="chat-1",
    )
    approval_id = re.search(r"H-[A-F0-9]{12}", preview).group(0)

    result = telegram_gateway.process_user_prompt(
        f"승인 {approval_id}",
        user_id="user-1",
        chat_id="chat-1",
    )

    assert calls == ["회의 내용을 WIKI에 기록해줘"]
    assert "저장했습니다" in result
    assert "wiki/00_Inbox/2026-09-17_1405_회의-내용.md" in result

    repeated = telegram_gateway.process_user_prompt(
        f"승인 {approval_id}",
        user_id="user-1",
        chat_id="chat-1",
    )
    assert "없거나 만료" in repeated


def test_memo_approval_rejects_a_different_user(monkeypatch, tmp_path):
    store = MemoApprovalStore(tmp_path / "approvals.sqlite3")
    monkeypatch.setattr(telegram_gateway, "_get_memo_approval_store", lambda: store)

    preview = telegram_gateway.process_user_prompt(
        "회의 내용을 WIKI에 기록해줘",
        user_id="user-1",
        chat_id="chat-1",
    )
    approval_id = re.search(r"H-[A-F0-9]{12}", preview).group(0)

    result = telegram_gateway.process_user_prompt(
        f"승인 {approval_id}",
        user_id="user-2",
        chat_id="chat-1",
    )

    assert "없거나 만료" in result


def test_memo_approval_reports_queue_registration(monkeypatch, tmp_path):
    store = MemoApprovalStore(tmp_path / "approvals.sqlite3")
    monkeypatch.setattr(telegram_gateway, "_get_memo_approval_store", lambda: store)
    monkeypatch.setenv("HERMES_MEMO_SINK", "queue")
    monkeypatch.setenv("HERMES_INBOX_QUEUE_DIR", str(tmp_path / "queue"))

    preview = telegram_gateway.process_user_prompt(
        "Oracle 전환 메모를 WIKI에 기록해줘",
        user_id="user-1",
        chat_id="chat-1",
    )
    approval_id = re.search(r"H-[A-F0-9]{12}", preview).group(0)

    result = telegram_gateway.process_user_prompt(
        f"승인 {approval_id}",
        user_id="user-1",
        chat_id="chat-1",
    )

    assert "저장 대기열에 등록했습니다" in result
    assert len(list((tmp_path / "queue" / "pending").glob("*.md"))) == 1
