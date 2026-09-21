"""Minimal Google Calendar v3 client for deterministic Hermes reads and creates."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import time
from typing import Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


CALENDAR_API_URL = "https://www.googleapis.com/calendar/v3"
DEFAULT_TOKEN_URI = "https://oauth2.googleapis.com/token"


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


Transport = Callable[[str, str, dict[str, str], bytes | None], HttpResponse]


class GoogleCalendarError(RuntimeError):
    """Safe Calendar failure that never includes credentials or auth headers."""

    def __init__(self, message: str, *, status: int | None = None):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class CalendarEvent:
    event_id: str
    title: str
    start: str
    end: str


def _default_transport(
    method: str, url: str, headers: dict[str, str], body: bytes | None
) -> HttpResponse:
    request = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            return HttpResponse(response.status, dict(response.headers.items()), response.read())
    except HTTPError as error:
        return HttpResponse(error.code, dict(error.headers.items()), error.read())
    except (URLError, OSError) as error:
        raise GoogleCalendarError("Google Calendar 네트워크 요청에 실패했습니다.") from error


class _TokenProvider:
    def __init__(self, path: Path, *, transport: Transport, clock: Callable[[], float]):
        self._transport = transport
        self._clock = clock
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise GoogleCalendarError("Google Calendar 자격 증명 파일을 읽을 수 없습니다.") from error
        if not isinstance(payload, dict):
            raise GoogleCalendarError("Google Calendar 자격 증명 형식이 올바르지 않습니다.")
        required = ("client_id", "client_secret", "refresh_token")
        if any(not isinstance(payload.get(key), str) or not payload[key] for key in required):
            raise GoogleCalendarError("Google Calendar OAuth 자격 증명이 불완전합니다.")
        self._credentials = payload
        self._token: str | None = None
        self._expires_at = 0.0

    def get(self) -> str:
        if self._token and self._expires_at > self._clock() + 60:
            return self._token
        form = urlencode(
            {
                "client_id": self._credentials["client_id"],
                "client_secret": self._credentials["client_secret"],
                "refresh_token": self._credentials["refresh_token"],
                "grant_type": "refresh_token",
            }
        ).encode("utf-8")
        response = self._transport(
            "POST",
            str(self._credentials.get("token_uri", DEFAULT_TOKEN_URI)),
            {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            form,
        )
        payload = _json(response.body)
        if not 200 <= response.status < 300:
            raise GoogleCalendarError("Google Calendar OAuth 토큰 갱신에 실패했습니다.", status=response.status)
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise GoogleCalendarError("Google Calendar OAuth 응답에 access_token이 없습니다.")
        self._token = token
        try:
            expires_in = float(payload.get("expires_in", 3600))
        except (TypeError, ValueError):
            expires_in = 3600.0
        self._expires_at = self._clock() + max(60.0, expires_in)
        return token


class GoogleCalendarClient:
    def __init__(
        self,
        credentials_path: Path | str,
        *,
        transport: Transport | None = None,
        clock: Callable[[], float] = time.time,
        api_url: str = CALENDAR_API_URL,
    ) -> None:
        self._transport = transport or _default_transport
        self._api_url = api_url.rstrip("/")
        self._tokens = _TokenProvider(Path(credentials_path), transport=self._transport, clock=clock)

    def list_events(self, start: str, end: str, *, calendar_id: str = "primary") -> list[CalendarEvent]:
        params = {
            "timeMin": start,
            "timeMax": end,
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": "2500",
        }
        response = self._request(
            "GET",
            f"{self._api_url}/calendars/{quote(calendar_id, safe='')}/events",
            params=params,
        )
        payload = _json(response.body)
        items = payload.get("items", [])
        if not isinstance(items, list):
            raise GoogleCalendarError("Google Calendar 일정 목록 형식이 올바르지 않습니다.")
        events: list[CalendarEvent] = []
        for item in items:
            if not isinstance(item, dict) or item.get("status") == "cancelled":
                continue
            start_value = item.get("start", {})
            end_value = item.get("end", {})
            if not isinstance(start_value, dict) or not isinstance(end_value, dict):
                continue
            event_id = item.get("id")
            event_start = start_value.get("dateTime") or start_value.get("date")
            event_end = end_value.get("dateTime") or end_value.get("date")
            if all(isinstance(value, str) and value for value in (event_id, event_start, event_end)):
                events.append(
                    CalendarEvent(
                        event_id=event_id,
                        title=str(item.get("summary") or "(제목 없음)")[:200],
                        start=event_start,
                        end=event_end,
                    )
                )
        return events

    def create_event(
        self,
        title: str,
        start: str,
        end: str,
        *,
        description: str = "",
        calendar_id: str = "primary",
    ) -> CalendarEvent:
        body = json.dumps(
            {
                "summary": title,
                "description": description,
                "start": {"dateTime": start, "timeZone": "Asia/Seoul"},
                "end": {"dateTime": end, "timeZone": "Asia/Seoul"},
            },
            ensure_ascii=False,
        ).encode("utf-8")
        response = self._request(
            "POST",
            f"{self._api_url}/calendars/{quote(calendar_id, safe='')}/events",
            body=body,
            extra_headers={"Content-Type": "application/json; charset=utf-8"},
        )
        payload = _json(response.body)
        event_id = payload.get("id")
        if not isinstance(event_id, str) or not event_id:
            raise GoogleCalendarError("생성된 Google Calendar 일정 ID가 없습니다.")
        return CalendarEvent(event_id, title, start, end)

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
        body: bytes | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        if params:
            url = f"{url}?{urlencode(params)}"
        headers = {"Accept": "application/json", "Authorization": f"Bearer {self._tokens.get()}"}
        if extra_headers:
            headers.update(extra_headers)
        response = self._transport(method, url, headers, body)
        if not 200 <= response.status < 300:
            raise GoogleCalendarError("Google Calendar API 요청이 거부되었습니다.", status=response.status)
        return response


def _json(body: bytes) -> dict[str, object]:
    try:
        payload = json.loads(body.decode("utf-8")) if body else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}
