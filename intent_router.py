from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class IntentKind(str, Enum):
    HELP = "help"
    WIKI_READ = "wiki_read"
    MEMO_WRITE = "memo_write"
    MEMO_APPROVE = "memo_approve"
    ANTIGRAVITY = "antigravity"
    CODEX = "codex"
    HARNESS = "harness"
    STOCK = "stock"
    CLARIFY = "clarify"


@dataclass(frozen=True)
class Intent:
    kind: IntentKind
    prompt: str
    reason: str


_MEMO_WRITE_PHRASES = (
    "기록해",
    "저장해",
    "남겨",
    "메모해",
    "추가해",
    "캡처해",
)
_MEMO_APPROVAL_TERMS = (
    "승인",
    "저장 승인",
)
_WIKI_READ_TERMS = (
    "운동",
    "위키",
    "wiki",
    "기록",
    "인박스",
    "프로젝트",
    "작업",
    "task",
)
_WIKI_READ_ACTIONS = (
    "찾아",
    "알려",
    "조회",
    "검색",
    "확인",
    "언제",
    "최근",
    "지난주",
    "오늘",
    "이번 주",
    "이번주",
    "어제",
    "뭐",
    "무엇",
    "있어",
    "있나",
)
_CODEX_TERMS = (
    "codex",
    "코덱스",
    "코드",
    "리팩터링",
    "리팩토링",
    "버그",
    "구현",
    "테스트",
    "개발",
)


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def classify_intent(user_text: str) -> Intent:
    """Classify natural-language requests without treating /ask as a command."""
    prompt = user_text.strip()
    if not prompt:
        return Intent(IntentKind.CLARIFY, prompt, "empty_prompt")

    lowered = prompt.casefold()
    if lowered in {"/start", "/help"}:
        return Intent(IntentKind.HELP, prompt, "help_command")

    if _contains_any(lowered, ("antigravity", "agy", "안티그래비티")):
        return Intent(IntentKind.ANTIGRAVITY, prompt, "antigravity_request")

    if _contains_any(lowered, _MEMO_APPROVAL_TERMS):
        return Intent(IntentKind.MEMO_APPROVE, prompt, "memo_approval_request")

    if _contains_any(lowered, _MEMO_WRITE_PHRASES):
        return Intent(IntentKind.MEMO_WRITE, prompt, "memo_write_request")

    if _contains_any(lowered, ("하네스", "파이프라인")):
        return Intent(IntentKind.HARNESS, prompt, "harness_request")

    if _contains_any(lowered, ("주식", "시세", "주가")):
        return Intent(IntentKind.STOCK, prompt, "stock_request")

    if _contains_any(lowered, _WIKI_READ_TERMS) and (
        _contains_any(lowered, _WIKI_READ_ACTIONS) or "?" in prompt or "？" in prompt
    ):
        return Intent(IntentKind.WIKI_READ, prompt, "wiki_read_request")

    if _contains_any(lowered, _CODEX_TERMS):
        return Intent(IntentKind.CODEX, prompt, "codex_request")

    return Intent(IntentKind.CLARIFY, prompt, "ambiguous_prompt")
