from __future__ import annotations

from intent_router import IntentKind, classify_intent
from scripts.verify_tool_calling import mock_llm_router


def test_empty_prompt_requires_clarification():
    intent = classify_intent("   ")

    assert intent.kind is IntentKind.CLARIFY
    assert intent.reason == "empty_prompt"


def test_help_commands_remain_available_without_an_ask_command():
    assert classify_intent("/start").kind is IntentKind.HELP
    assert classify_intent("/help").kind is IntentKind.HELP


def test_today_plan_and_calendar_approval_are_distinct_from_wiki_and_memo():
    assert classify_intent("오늘 할 일 정리하고 일정 추천해줘").kind is IntentKind.TODAY_PLAN
    assert classify_intent("일정 승인 C-1234ABCDEF56").kind is IntentKind.CALENDAR_APPROVE


def test_natural_language_wiki_question_is_read_only():
    intent = classify_intent("지난주 운동 기록 알려줘")

    assert intent.kind is IntentKind.WIKI_READ


def test_unprefixed_personal_question_routes_to_wiki_answer_service():
    intent = classify_intent("내가 지난달 읽은 책은?")

    assert intent.kind is IntentKind.WIKI_READ


def test_time_scoped_wiki_request_without_a_verb_is_still_a_lookup():
    intent = classify_intent("오늘 운동 기록")

    assert intent.kind is IntentKind.WIKI_READ


def test_legacy_ask_prefix_is_not_a_distinct_route():
    intent = classify_intent("/ask 지난주 운동 기록 알려줘")

    assert intent.kind is IntentKind.WIKI_READ
    assert intent.reason != "ask_command"


def test_save_language_takes_precedence_over_wiki_lookup():
    intent = classify_intent("이 회의 내용을 WIKI에 기록해줘")

    assert intent.kind is IntentKind.MEMO_WRITE


def test_natural_language_memo_approval_has_its_own_route():
    intent = classify_intent("승인 H-ABC123")

    assert intent.kind is IntentKind.MEMO_APPROVE


def test_inbox_question_without_a_write_verb_is_a_lookup():
    intent = classify_intent("인박스에 뭐 있어?")

    assert intent.kind is IntentKind.WIKI_READ


def test_natural_language_coding_request_routes_to_codex():
    intent = classify_intent("이 파이썬 코드의 버그를 수정해줘")

    assert intent.kind is IntentKind.CODEX


def test_natural_language_google_drive_request_has_its_own_route():
    intent = classify_intent("구글드라이브에서 파일명: 회의록.md 찾아줘")

    assert intent.kind is IntentKind.GOOGLE_DRIVE


def test_unrecognized_google_drive_request_does_not_fall_through_to_wiki():
    intent = classify_intent("구글드라이브 어떻게 써?")

    assert intent.kind is IntentKind.CLARIFY


def test_explicit_specialist_requests_are_distinguished():
    assert classify_intent("antigravity에게 분석을 요청해줘").kind is IntentKind.ANTIGRAVITY
    assert classify_intent("하네스 상태 확인해줘").kind is IntentKind.HARNESS
    assert classify_intent("삼성전자 주식 시세 알려줘").kind is IntentKind.STOCK


def test_ambiguous_prompt_does_not_fall_through_to_codex():
    intent = classify_intent("그거 좀 확인해줘")

    assert intent.kind is IntentKind.CLARIFY
    assert intent.reason == "ambiguous_prompt"


def test_verification_router_uses_the_shared_classifier_for_memo_requests():
    decision = mock_llm_router("회의 내용을 WIKI에 기록해줘")

    assert "tool_calls" not in decision
    assert "저장" in decision["content"]


def test_verification_router_keeps_memo_approval_out_of_model_tools():
    decision = mock_llm_router("승인 H-ABC123")

    assert "tool_calls" not in decision
    assert "승인" in decision["content"]


def test_verification_router_uses_the_shared_classifier_for_ambiguous_requests():
    decision = mock_llm_router("그거 좀 확인해줘")

    assert "tool_calls" not in decision
    assert "정확히" in decision["content"]
