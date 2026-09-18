from __future__ import annotations

import io
import json

import pytest

from tools.wiki_task_client import WikiTaskError, query_tasks


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


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


def test_query_tasks_calls_authenticated_structured_endpoint(tmp_path):
    key_file = tmp_path / "key"
    key_file.write_text("s" * 32, encoding="utf-8")
    seen = {}

    def opener(request, timeout):
        seen["url"] = request.full_url
        seen["key"] = request.headers["X-wiki-agent-key"]
        seen["payload"] = json.loads(request.data)
        seen["timeout"] = timeout
        return FakeResponse(json.dumps(_brief()).encode("utf-8"))

    result = query_tasks(
        endpoint="http://wiki-agent:8080/tasks/query",
        key_file=key_file,
        period="today",
        limit=5,
        opener=opener,
    )

    assert result["referenceDate"] == "2026-09-18"
    assert seen == {
        "url": "http://wiki-agent:8080/tasks/query",
        "key": "s" * 32,
        "payload": {"period": "today", "limit": 5},
        "timeout": 15,
    }


@pytest.mark.parametrize("limit", [0, 21, True, "5"])
def test_query_tasks_rejects_invalid_limit_before_network(tmp_path, limit):
    with pytest.raises(WikiTaskError):
        query_tasks(
            endpoint="http://wiki-agent:8080/tasks/query",
            key_file=tmp_path / "missing",
            limit=limit,
        )
