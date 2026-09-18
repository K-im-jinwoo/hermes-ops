import json
from pathlib import Path
from urllib.error import HTTPError

import pytest

from tools.wiki_agent_client import WikiAgentError, ask_wiki


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_ask_wiki_preserves_chat_session_and_returns_sources(tmp_path: Path):
    key_file = tmp_path / "key"
    key_file.write_text("private-key\n", encoding="utf-8")
    seen = {}

    def opener(request, timeout):
        seen["request"] = request
        seen["timeout"] = timeout
        return Response({"answer": "어깨 운동은 9월 16일입니다.", "sources": ["wiki/daily/2026-09-16.md"], "wikiSyncedAt": "2026-09-18T00:00:00Z"})

    result = ask_wiki(
        "최근 운동은?",
        chat_id="chat-1",
        endpoint="http://wiki-agent:8080/ask",
        key_file=key_file,
        opener=opener,
    )

    request = seen["request"]
    assert request.full_url == "http://wiki-agent:8080/ask"
    assert json.loads(request.data) == {"chatId": "chat-1", "question": "최근 운동은?"}
    assert request.get_header("X-wiki-agent-key") == "private-key"
    assert result.answer == "어깨 운동은 9월 16일입니다."
    assert result.sources == ("wiki/daily/2026-09-16.md",)


def test_missing_key_fails_before_network(tmp_path: Path):
    with pytest.raises(WikiAgentError, match="인증"):
        ask_wiki(
            "질문",
            chat_id="chat-1",
            endpoint="http://wiki-agent:8080/ask",
            key_file=tmp_path / "missing",
            opener=lambda *args, **kwargs: pytest.fail("must not call network"),
        )


def test_http_failure_does_not_expose_shared_key(tmp_path: Path):
    key_file = tmp_path / "key"
    key_file.write_text("private-key", encoding="utf-8")

    def opener(request, timeout):
        raise HTTPError(request.full_url, 503, "unavailable", {}, None)

    with pytest.raises(WikiAgentError) as error:
        ask_wiki("질문", chat_id="chat-1", endpoint="http://wiki-agent:8080/ask", key_file=key_file, opener=opener)

    assert "503" in str(error.value)
    assert "private-key" not in str(error.value)
