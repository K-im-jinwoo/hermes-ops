import pytest

import telegram_gateway
from tools.wiki_agent_client import WikiAgentError, WikiAnswer


def test_natural_language_wiki_question_uses_existing_answer_service(monkeypatch):
    seen = {}

    def fake_ask(question, *, chat_id, endpoint, key_file):
        seen.update(question=question, chat_id=chat_id, endpoint=endpoint, key_file=str(key_file).replace("\\", "/"))
        return WikiAnswer("9월 16일에 어깨 운동을 했습니다.", ("wiki/daily/2026-09-16.md",), "2026-09-18T00:00:00Z")

    monkeypatch.setenv("WIKI_AGENT_URL", "http://wiki-agent:8080/ask")
    monkeypatch.setenv("WIKI_AGENT_KEY_FILE", "/run/secrets/wiki-agent-key")
    monkeypatch.setattr(telegram_gateway, "ask_wiki", fake_ask, raising=False)
    monkeypatch.setattr(telegram_gateway, "ask_antigravity", lambda *args, **kwargs: pytest.fail("agy must not run"))
    monkeypatch.setattr(telegram_gateway, "record_tool_event", lambda *args, **kwargs: None)

    result = telegram_gateway.process_user_prompt("최근 운동 기록 알려줘", chat_id="chat-1")

    assert seen == {
        "question": "최근 운동 기록 알려줘",
        "chat_id": "chat-1",
        "endpoint": "http://wiki-agent:8080/ask",
        "key_file": "/run/secrets/wiki-agent-key",
    }
    assert "9월 16일" in result
    assert "wiki/daily/2026-09-16.md" in result


def test_wiki_api_failure_is_reported_without_raw_fallback(monkeypatch):
    monkeypatch.setenv("WIKI_AGENT_URL", "http://wiki-agent:8080/ask")
    monkeypatch.setenv("WIKI_AGENT_KEY_FILE", "/run/secrets/wiki-agent-key")
    monkeypatch.setattr(telegram_gateway, "ask_wiki", lambda *args, **kwargs: (_ for _ in ()).throw(WikiAgentError("WIKI 답변 서비스가 HTTP 503을 반환했습니다.")), raising=False)
    monkeypatch.setattr(telegram_gateway, "record_tool_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(telegram_gateway, "wiki_search", lambda *args, **kwargs: pytest.fail("raw fallback must not run"))

    result = telegram_gateway.process_user_prompt("최근 운동 기록 알려줘", chat_id="chat-1")

    assert "503" in result
    assert "찾아" not in result
