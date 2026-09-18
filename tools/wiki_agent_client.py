"""Authenticated read-only client for the existing WIKI answer service."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class WikiAgentError(Exception):
    """Safe, user-facing WIKI API failure."""


@dataclass(frozen=True)
class WikiAnswer:
    answer: str
    sources: tuple[str, ...]
    wiki_synced_at: str


def ask_wiki(
    question: str,
    *,
    chat_id: str,
    endpoint: str,
    key_file: Path,
    opener: Callable = urlopen,
) -> WikiAnswer:
    clean_question = question.strip()
    clean_chat_id = chat_id.strip()
    if not clean_question or len(clean_question) > 2000 or not clean_chat_id or len(clean_chat_id) > 128:
        raise WikiAgentError("WIKI 질문 또는 채팅 식별자가 올바르지 않습니다.")
    if not endpoint.startswith(("http://", "https://")):
        raise WikiAgentError("WIKI API 주소가 설정되지 않았습니다.")
    try:
        secret = Path(key_file).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as error:
        raise WikiAgentError("WIKI API 인증 파일을 읽을 수 없습니다.") from error
    if not secret:
        raise WikiAgentError("WIKI API 인증 파일이 비어 있습니다.")

    payload = json.dumps(
        {"chatId": clean_chat_id, "question": clean_question},
        ensure_ascii=False,
    ).encode("utf-8")
    request = Request(
        endpoint,
        data=payload,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "X-Wiki-Agent-Key": secret,
        },
        method="POST",
    )
    try:
        with opener(request, timeout=35) as response:
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise WikiAgentError(f"WIKI 답변 서비스가 HTTP {error.code}을 반환했습니다.") from error
    except (URLError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError) as error:
        raise WikiAgentError("WIKI 답변 서비스에 연결할 수 없습니다.") from error

    if not isinstance(body, dict):
        raise WikiAgentError("WIKI 답변 형식이 올바르지 않습니다.")
    answer = body.get("answer")
    sources = body.get("sources")
    synced_at = body.get("wikiSyncedAt")
    if not isinstance(answer, str) or not answer.strip() or not isinstance(sources, list) or not all(isinstance(source, str) for source in sources) or not isinstance(synced_at, str):
        raise WikiAgentError("WIKI 답변 형식이 올바르지 않습니다.")
    return WikiAnswer(answer.strip(), tuple(sources), synced_at)
