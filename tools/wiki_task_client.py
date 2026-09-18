"""Authenticated client for the WIKI agent's structured task endpoint."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class WikiTaskError(Exception):
    """Safe, user-facing structured task API failure."""


_TASK_GROUPS = (
    "confirmed",
    "carryOver",
    "recommended",
    "candidates",
    "scheduledLater",
    "onHold",
    "unknown",
)


def query_tasks(
    *,
    endpoint: str,
    key_file: Path,
    period: str = "today",
    limit: int = 5,
    opener: Callable = urlopen,
) -> dict:
    if (
        period not in {"today", "week"}
        or isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 1 <= limit <= 20
    ):
        raise WikiTaskError("Task 조회 조건이 올바르지 않습니다.")
    if not endpoint.startswith(("http://", "https://")):
        raise WikiTaskError("WIKI Task API 주소가 설정되지 않았습니다.")
    try:
        secret = Path(key_file).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as error:
        raise WikiTaskError("WIKI API 인증 파일을 읽을 수 없습니다.") from error
    if not secret:
        raise WikiTaskError("WIKI API 인증 파일이 비어 있습니다.")

    request = Request(
        endpoint,
        data=json.dumps({"period": period, "limit": limit}).encode("utf-8"),
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "X-Wiki-Agent-Key": secret,
        },
        method="POST",
    )
    try:
        with opener(request, timeout=15) as response:
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise WikiTaskError(f"WIKI Task 서비스가 HTTP {error.code}을 반환했습니다.") from error
    except (URLError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError) as error:
        raise WikiTaskError("WIKI Task 서비스에 연결할 수 없습니다.") from error

    _validate_task_brief(body)
    return body


def _validate_task_brief(body: object) -> None:
    if not isinstance(body, dict):
        raise WikiTaskError("WIKI Task 응답 형식이 올바르지 않습니다.")
    if body.get("period") not in {"today", "week"}:
        raise WikiTaskError("WIKI Task 응답 형식이 올바르지 않습니다.")
    reference_date = body.get("referenceDate")
    if not isinstance(reference_date, str) or len(reference_date) != 10:
        raise WikiTaskError("WIKI Task 응답 형식이 올바르지 않습니다.")
    for group in _TASK_GROUPS:
        items = body.get(group)
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise WikiTaskError("WIKI Task 응답 형식이 올바르지 않습니다.")
