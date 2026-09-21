from __future__ import annotations

import json
from pathlib import Path

from tools.google_calendar_tool import GoogleCalendarClient, HttpResponse


def _credentials(path: Path) -> Path:
    path.write_text(json.dumps({"client_id": "client", "client_secret": "secret",
        "refresh_token": "refresh", "token_uri": "https://oauth.example/token"}), encoding="utf-8")
    return path


class Transport:
    def __init__(self):
        self.calls = []
    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, body))
        if url == "https://oauth.example/token":
            return HttpResponse(200, {}, json.dumps({"access_token": "access", "expires_in": 3600}).encode())
        if method == "GET":
            return HttpResponse(200, {}, json.dumps({"items": [{"id": "e1", "summary": "Focus",
                "start": {"dateTime": "2026-09-21T09:00:00+09:00"},
                "end": {"dateTime": "2026-09-21T10:00:00+09:00"}}]}).encode())
        return HttpResponse(200, {}, json.dumps({"id": "created"}).encode())


def test_list_and_create_use_calendar_v3_with_bearer_token(tmp_path):
    transport = Transport()
    client = GoogleCalendarClient(_credentials(tmp_path / "credentials.json"), transport=transport, clock=lambda: 1)
    events = client.list_events("2026-09-21T09:00:00+09:00", "2026-09-21T18:00:00+09:00")
    created = client.create_event("Task", "2026-09-21T10:00:00+09:00", "2026-09-21T11:00:00+09:00")
    assert events[0].event_id == "e1"
    assert created.event_id == "created"
    api_calls = [call for call in transport.calls if "calendar/v3" in call[1]]
    assert [call[0] for call in api_calls] == ["GET", "POST"]
    assert all(call[2]["Authorization"] == "Bearer access" for call in api_calls)
    assert sum(call[1] == "https://oauth.example/token" for call in transport.calls) == 1
