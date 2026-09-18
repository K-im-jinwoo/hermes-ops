"""
telegram_gateway.py - Karpathy 스타일 경량 Telegram-Codex 게이트웨이

외부의 무거운 프레임워크나 추가 유료 API Key 없이,
Telegram Bot API의 Long Polling 방식으로 메시지를 수신하여
이미 로컬에 로그인된 Codex / Antigravity CLI 및 .wiki 도구로 연결합니다.
"""

from __future__ import annotations

import html
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

# 프로젝트 루트 sys.path 추가
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from tools.wiki_tool import read_wiki_file, wiki_search
from tools.memo_approval import MemoApprovalStore, PendingMemo
from tools.memo_queue import stage_memo_to_queue
from tools.memo_drive import save_memo_to_drive_inbox
from tools.memo_store import MemoSaveResult, MemoSaveStatus, locate_wiki_repo_root, save_memo_to_inbox
from tools.antigravity_tool import ask_antigravity
from tools.codex_tool import ask_codex
from tools.harness_tool import harness_status
from tools.stock_tool import stock_research
from tools.google_drive_request import DriveAction, GoogleDriveRequest, parse_google_drive_request
from tools.google_drive_tool import DriveFile, GoogleDriveError, GoogleDriveClient, load_google_drive_client
from tools.wiki_agent_client import WikiAgentError, ask_wiki
from hooks.metrics_hook import record_tool_event
from intent_router import IntentKind, classify_intent

_APPROVAL_ID_PATTERN = re.compile(r"\bH-[A-F0-9]{12}\b", re.IGNORECASE)
_memo_approval_store: Optional[MemoApprovalStore] = None
_google_drive_client: Optional[GoogleDriveClient] = None


# -----------------------------------------------------------------------------
# 1. Telegram Bot API 원시 HTTP 통신 계층 (No Heavy Framework)
# -----------------------------------------------------------------------------

def _load_env_file_value(name: str) -> Optional[str]:
    """환경변수 또는 프로젝트 .env 파일에서 설정값을 읽습니다."""
    value = os.getenv(name)
    if value:
        return value.strip().strip('"').strip("'")

    file_path = os.getenv(f"{name}_FILE")
    if file_path:
        try:
            file_value = Path(file_path).read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError):
            file_value = ""
        if file_value:
            return file_value.strip('"').strip("'")

    env_file = _PROJECT_ROOT / ".env"
    if not env_file.is_file():
        return None

    with open(env_file, mode="r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line.startswith(f"{name}="):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                if val:
                    return val
    return None


def _load_env_token() -> Optional[str]:
    """환경변수 또는 .env 파일에서 TELEGRAM_BOT_TOKEN을 읽어옵니다."""
    token = _load_env_file_value("TELEGRAM_BOT_TOKEN")
    if token and token != "your_telegram_bot_token_here":
        return token
    return None


def _load_allowed_user_ids() -> frozenset[int]:
    """허용된 Telegram 사용자 ID를 읽으며 잘못된 설정은 fail-closed 처리합니다."""
    raw_value = _load_env_file_value("TELEGRAM_ALLOWED_USER_IDS")
    if not raw_value:
        return frozenset()

    raw_ids = [item.strip() for item in raw_value.split(",")]
    if not raw_ids or any(not item.isdecimal() or int(item) <= 0 for item in raw_ids):
        return frozenset()
    return frozenset(int(item) for item in raw_ids)


def _is_allowed_telegram_user(message_obj: Dict[str, Any], allowed_user_ids: frozenset[int]) -> bool:
    """메시지 발신자가 명시된 허용 목록에 포함되는지 확인합니다."""
    sender = message_obj.get("from")
    if not isinstance(sender, dict):
        return False
    sender_id = sender.get("id")
    return isinstance(sender_id, int) and sender_id in allowed_user_ids


def _should_delete_webhook() -> bool:
    """Webhook 삭제는 운영 수신 경로를 바꾸므로 명시적으로만 허용합니다."""
    return (_load_env_file_value("TELEGRAM_DELETE_WEBHOOK") or "").casefold() == "true"


def ensure_webhook_deleted(bot_token: str) -> None:
    """기존 Webhook(n8n 등)이 활성화되어 409 Conflict가 발생하는 것을 방지합니다."""
    url = f"https://api.telegram.org/bot{bot_token}/deleteWebhook"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            pass
    except Exception:
        pass


def fetch_telegram_updates(bot_token: str, offset: Optional[int], timeout_seconds: int = 25) -> List[Dict[str, Any]]:
    """Telegram getUpdates 엔드포인트에 롱 폴링(Long Polling) 요청을 보냅니다."""
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates?timeout={timeout_seconds}"
    if offset is not None:
        url += f"&offset={offset}"

    request = urllib.request.Request(url, headers={"User-Agent": "Codex-Telegram-Gateway/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds + 5) as response:
            if response.status != 200:
                return []
            data = json.loads(response.read().decode("utf-8"))
            return data.get("result", [])
    except Exception as exc:
        print(f"[getUpdates 에러]: {str(exc)}")
        time.sleep(2)
        return []


def format_markdown_to_telegram_html(text: str) -> str:
    """마크다운(**, `, ``` 등)을 텔레그램 호환 HTML 태그로 안전하게 변환합니다."""
    # 1. 특수문자 이스케이프
    escaped = html.escape(text, quote=False)

    # 2. 코드 블록 (``` ... ```)
    def replace_code_block(match: re.Match) -> str:
        code_body = match.group(2)
        return f"<pre><code>{code_body}</code></pre>"

    escaped = re.sub(r"```([a-zA-Z0-9_-]*)\n?(.*?)```", replace_code_block, escaped, flags=re.DOTALL)

    # 3. 인라인 코드 (`...`)
    escaped = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", escaped)

    # 4. 볼드 (**...**)
    escaped = re.sub(r"\*\*([^\*\n]+)\*\*", r"<b>\1</b>", escaped)

    # 5. 마크다운 헤더 (### ...)
    escaped = re.sub(r"^(?:#{1,6})\s+(.+)$", r"<b>\1</b>", escaped, flags=re.MULTILINE)

    return escaped


def send_telegram_message(bot_token: str, chat_id: int, text: str) -> bool:
    """Telegram sendMessage 엔드포인트로 응답 메시지를 전송합니다 (HTML 렌더링 지원 및 일반 텍스트 폴백)."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    # HTML 렌더링 시도
    formatted_html = format_markdown_to_telegram_html(text)
    payload = json.dumps({
        "chat_id": chat_id,
        "text": formatted_html,
        "parse_mode": "HTML"
    }, ensure_ascii=False).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": "Codex-Telegram-Gateway/1.0"}
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status == 200
    except Exception as exc:
        print(f"[HTML 전송 에러, 일반 텍스트 폴백 시도]: {str(exc)}")
        # HTML 파싱 오류 시 원본 일반 텍스트로 즉시 안전 전송
        fallback_payload = json.dumps({"chat_id": chat_id, "text": text}, ensure_ascii=False).encode("utf-8")
        fallback_request = urllib.request.Request(
            url,
            data=fallback_payload,
            headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": "Codex-Telegram-Gateway/1.0"}
        )
        try:
            with urllib.request.urlopen(fallback_request, timeout=10) as fb_resp:
                return fb_resp.status == 200
        except Exception as fb_exc:
            print(f"[일반 텍스트 전송 실패]: {str(fb_exc)}")
            return False


# -----------------------------------------------------------------------------
# 2. 메시지 라우터 및 에이전트 디스패처 (Codex & 도구 연동)
# -----------------------------------------------------------------------------

def _save_memo(prompt: str) -> MemoSaveResult:
    sink = os.getenv("HERMES_MEMO_SINK", "direct").strip().casefold()
    if sink == "drive":
        inbox_id = os.getenv("GOOGLE_DRIVE_ROOT_ID", "").strip()
        if not inbox_id:
            return MemoSaveResult(
                MemoSaveStatus.UNAVAILABLE,
                reason="drive_inbox_not_configured",
            )
        try:
            client = _get_google_drive_client()
        except GoogleDriveError:
            return MemoSaveResult(
                MemoSaveStatus.UNAVAILABLE,
                reason="drive_unavailable",
            )
        return save_memo_to_drive_inbox(prompt, client=client, inbox_id=inbox_id)
    if sink == "queue":
        queue_root = Path(
            os.getenv(
                "HERMES_INBOX_QUEUE_DIR",
                str(_PROJECT_ROOT / "data" / "inbox_queue"),
            )
        )
        return stage_memo_to_queue(prompt, queue_root=queue_root)
    if sink not in {"direct", ""}:
        return MemoSaveResult(
            MemoSaveStatus.UNAVAILABLE,
            reason="invalid_memo_sink",
        )

    wiki_repo_root = locate_wiki_repo_root()
    if wiki_repo_root is None:
        return MemoSaveResult(
            MemoSaveStatus.UNAVAILABLE,
            reason="valid_wiki_root_not_found",
        )
    return save_memo_to_inbox(prompt, wiki_repo_root=wiki_repo_root)


def _get_memo_approval_store() -> MemoApprovalStore:
    global _memo_approval_store
    if _memo_approval_store is None:
        database_path = Path(
            os.getenv(
                "HERMES_APPROVAL_DB_PATH",
                str(_PROJECT_ROOT / "data" / "memo_approvals.sqlite3"),
            )
        )
        raw_ttl = os.getenv("HERMES_APPROVAL_TTL_SECONDS", "300")
        try:
            ttl_seconds = int(raw_ttl)
        except ValueError:
            ttl_seconds = 300
        _memo_approval_store = MemoApprovalStore(
            database_path,
            ttl_seconds=max(1, ttl_seconds),
        )
    return _memo_approval_store


def _extract_approval_id(prompt: str) -> Optional[str]:
    match = _APPROVAL_ID_PATTERN.search(prompt)
    return match.group(0).upper() if match else None


def _build_memo_preview(prompt: str, pending: Optional[PendingMemo]) -> str:
    if pending is None:
        return (
            "메모 저장 미리보기를 만들었지만 Telegram 사용자·채팅 식별자가 없어 "
            "승인 ID를 발급하지 않았습니다."
        )
    return (
        "메모 저장 요청으로 이해했습니다. 아직 저장하지 않았습니다.\n\n"
        "저장 대상: wiki/00_Inbox\n"
        f"승인 ID: {pending.approval_id}\n"
        f"내용:\n{prompt}\n\n"
        f"저장하려면 5분 안에 '승인 {pending.approval_id}'라고 답하세요."
    )


def _request_memo_approval(
    prompt: str,
    *,
    user_id: Optional[str],
    chat_id: Optional[str],
) -> str:
    if not user_id or not chat_id:
        return _build_memo_preview(prompt, None)
    try:
        pending = _get_memo_approval_store().issue(
            user_id=user_id,
            chat_id=chat_id,
            content=prompt,
        )
    except (OSError, sqlite3.Error, ValueError):
        return "메모 승인 상태를 저장할 수 없어 기록을 시작하지 못했습니다."
    return _build_memo_preview(prompt, pending)


def _approve_memo(
    prompt: str,
    *,
    user_id: Optional[str],
    chat_id: Optional[str],
) -> str:
    approval_id = _extract_approval_id(prompt)
    if not approval_id:
        return "승인 ID가 없습니다. 미리보기의 승인 ID를 함께 보내주세요."
    if not user_id or not chat_id:
        return "Telegram 사용자·채팅 식별자가 없어 승인을 처리할 수 없습니다."
    try:
        pending = _get_memo_approval_store().consume(
            approval_id,
            user_id=user_id,
            chat_id=chat_id,
        )
    except (OSError, sqlite3.Error, ValueError):
        return "메모 승인 상태를 확인할 수 없어 저장하지 못했습니다."
    if pending is None:
        return "승인 ID가 없거나 만료되었거나 다른 사용자에게 발급된 ID입니다."
    return _format_memo_save_result(_save_memo(pending.content))


def _format_memo_save_result(result: MemoSaveResult) -> str:
    path = result.path.as_posix() if result.path else "wiki/00_Inbox"
    if result.status is MemoSaveStatus.QUEUED:
        return (
            "메모를 저장 대기열에 등록했습니다.\n"
            f"대기열 경로: {path}\n"
            "Google Drive 업로드는 별도 동기화 작업에서 처리됩니다."
        )
    if result.status is MemoSaveStatus.CREATED:
        return f"메모를 저장했습니다.\n경로: {path}"
    if result.status is MemoSaveStatus.DUPLICATE:
        return f"같은 내용의 메모가 이미 있습니다. 새 파일은 만들지 않았습니다.\n경로: {path}"
    if result.status is MemoSaveStatus.NEEDS_REVIEW:
        return (
            "같은 제목의 Inbox 초안이 있어 저장하지 않았습니다.\n"
            f"확인 대상: {path}"
        )
    if result.reason in {"drive_inbox_not_configured", "drive_unavailable", "inbox_listing_limit"}:
        return "Google Drive Inbox에 메모를 저장하지 못했습니다. 연결과 대상 폴더 설정을 확인해주세요."
    return (
        "메모를 저장하지 못했습니다. WIKI 구조를 확인한 뒤 다시 시도해주세요.\n"
        f"대상: {path}"
    )


def _get_google_drive_client() -> GoogleDriveClient:
    global _google_drive_client
    if _google_drive_client is None:
        _google_drive_client = load_google_drive_client()
    return _google_drive_client


def _handle_google_drive_request(prompt: str) -> str:
    request = parse_google_drive_request(prompt)
    if request is None:
        return (
            "Google Drive 작업을 이해하지 못했습니다. "
            "목록, 읽기, 생성, 수정, 삭제, 폴더 생성, 이동 중 하나를 명시해주세요."
        )

    started = time.perf_counter()
    try:
        client = _get_google_drive_client()
        result = _execute_google_drive_request(client, request)
        record_tool_event("google_drive", (time.perf_counter() - started) * 1000, "success")
        return result
    except GoogleDriveError as error:
        record_tool_event("google_drive", (time.perf_counter() - started) * 1000, "error")
        status = f" (HTTP {error.status})" if error.status is not None else ""
        return f"Google Drive 작업에 실패했습니다{status}: {error}"


def _execute_google_drive_request(client: GoogleDriveClient, request: GoogleDriveRequest) -> str:
    if request.action is DriveAction.LIST:
        files = client.list_files(
            name_contains=request.file_name or request.query,
            parent_id=request.parent_id,
        )
        return _format_drive_file_list(files)

    if request.action is DriveAction.READ:
        file_id, error = _resolve_drive_file_id(client, request)
        if error:
            return error
        return f"[Google Drive 파일: {file_id}]\n\n{client.read_file(file_id)}"

    if request.action is DriveAction.CREATE:
        if not request.file_name:
            return "생성할 파일명이 없습니다. '파일명: 회의록.md'처럼 지정해주세요."
        if request.content is None:
            return "생성할 파일 내용이 없습니다. '내용: ...'처럼 지정해주세요."
        created = client.create_file(
            request.file_name,
            request.content,
            parent_id=request.parent_id,
        )
        return f"Google Drive 파일을 생성했습니다.\n{_format_drive_file(created)}"

    if request.action is DriveAction.UPDATE:
        file_id, error = _resolve_drive_file_id(client, request, destructive=True)
        if error:
            return error
        if request.content is None:
            return "수정할 내용이 없습니다. '내용: ...'처럼 지정해주세요."
        updated = client.update_file(file_id, content=request.content)
        return f"Google Drive 파일을 수정했습니다.\n{_format_drive_file(updated)}"

    if request.action is DriveAction.DELETE:
        file_id, error = _resolve_drive_file_id(client, request, destructive=True)
        if error:
            return error
        client.delete_file(file_id)
        return f"Google Drive 파일을 삭제했습니다.\n파일 ID: {file_id}"

    if request.action is DriveAction.CREATE_FOLDER:
        if not request.folder_name:
            return "생성할 폴더명이 없습니다. '폴더명: 프로젝트A'처럼 지정해주세요."
        created = client.create_folder(request.folder_name, parent_id=request.parent_id)
        return f"Google Drive 폴더를 생성했습니다.\n{_format_drive_file(created)}"

    if request.action is DriveAction.MOVE:
        if not request.parent_id:
            return "이동할 상위 폴더 ID가 없습니다. '상위 폴더 ID: ...'처럼 지정해주세요."
        file_id, error = _resolve_drive_file_id(client, request, destructive=True)
        if error:
            return error
        moved = client.move_file(file_id, parent_id=request.parent_id)
        return f"Google Drive 파일을 이동했습니다.\n{_format_drive_file(moved)}"

    return "지원하지 않는 Google Drive 작업입니다."


def _resolve_drive_file_id(
    client: GoogleDriveClient,
    request: GoogleDriveRequest,
    *,
    destructive: bool = False,
) -> tuple[str, Optional[str]]:
    if request.file_id:
        return request.file_id, None
    lookup = request.file_name or request.query
    if not lookup:
        return "", "대상 파일 ID 또는 파일명이 없습니다."
    matches = client.list_files(name_contains=lookup)
    if len(matches) != 1:
        operation = "수정·삭제·이동" if destructive else "읽기"
        return "", f"{operation} 대상이 정확히 하나로 확인되지 않았습니다. 파일 ID를 지정해주세요. (검색 결과: {len(matches)}건)"
    return matches[0].file_id, None


def _format_drive_file_list(files: list[DriveFile]) -> str:
    if not files:
        return "Google Drive에서 조건에 맞는 파일을 찾지 못했습니다."
    lines = [f"Google Drive 검색 결과: {len(files)}건"]
    lines.extend(f"- {_format_drive_file(file)}" for file in files)
    return "\n".join(lines)


def _format_drive_file(file: DriveFile) -> str:
    link = f"\n  링크: {file.web_view_link}" if file.web_view_link else ""
    return f"{file.name} (ID: {file.file_id}, MIME: {file.mime_type}){link}"


def process_user_prompt(
    user_text: str,
    *,
    user_id: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> str:
    """자연어 의도를 분류하여 적절한 도구 또는 확인 응답으로 전달합니다."""
    cleaned = user_text.strip()
    intent = classify_intent(cleaned)

    if intent.kind is IntentKind.HELP:
        return (
            "안녕하세요! JinPro님의 개인 비서 봇입니다. 🤖\n\n"
            "다음과 같은 작업을 도와드릴 수 있습니다:\n"
            "📖 WIKI 조회: '최근 운동 기록 찾아줘', 'WIKI에서 프로젝트 검색'\n"
            "📝 메모 저장: '이 내용을 WIKI에 기록해줘' (미리보기 후 승인)\n"
            "☁️ Google Drive: '구글드라이브에서 회의록 찾아줘', '파일을 생성/수정/삭제해줘'\n"
            "💻 코딩/분석: 'codex에게 파이썬 코드 물어봐줘'\n"
            "🧠 심층 추론: 'antigravity에게 분석 요청해줘'\n"
            "⚙️ 하네스 점검: '하네스 상태 어때?'\n"
            "📈 주식 조회: '삼성전자 주식 시세 알려줘'\n\n"
            "편하게 말씀해 주세요!"
        )

    if intent.kind is IntentKind.CLARIFY:
        if intent.reason == "empty_prompt":
            return "메시지를 입력해주세요."
        return (
            "요청을 정확히 이해하지 못했습니다.\n"
            "WIKI 조회, 메모 저장, 코드 작업, 하네스 상태 확인 중 어떤 작업인지 알려주세요."
        )

    if intent.kind is IntentKind.GOOGLE_DRIVE:
        return _handle_google_drive_request(cleaned)

    if intent.kind is IntentKind.MEMO_WRITE:
        return _request_memo_approval(
            cleaned,
            user_id=user_id,
            chat_id=chat_id,
        )

    if intent.kind is IntentKind.MEMO_APPROVE:
        return _approve_memo(
            cleaned,
            user_id=user_id,
            chat_id=chat_id,
        )

    if intent.kind is IntentKind.ANTIGRAVITY:
        start_time = time.perf_counter()
        result = ask_antigravity(cleaned)
        duration = (time.perf_counter() - start_time) * 1000
        record_tool_event("ask_antigravity", duration, "success")
        return result

    if intent.kind is IntentKind.WIKI_READ:
        start_time = time.perf_counter()
        if not chat_id:
            return "WIKI 질문에 필요한 채팅 식별자가 없습니다."
        try:
            result = ask_wiki(
                cleaned,
                chat_id=chat_id,
                endpoint=os.getenv("WIKI_AGENT_URL", ""),
                key_file=Path(os.getenv("WIKI_AGENT_KEY_FILE", "")),
            )
        except WikiAgentError as error:
            record_tool_event("wiki_agent_ask", (time.perf_counter() - start_time) * 1000, "error")
            return str(error)
        record_tool_event("wiki_agent_ask", (time.perf_counter() - start_time) * 1000, "success")
        sources = tuple(dict.fromkeys(result.sources))
        if not sources:
            return result.answer
        return result.answer + "\n\n출처:\n" + "\n".join(f"- {source}" for source in sources)

    if intent.kind is IntentKind.HARNESS:
        start_time = time.perf_counter()
        result = harness_status("Codex")
        duration = (time.perf_counter() - start_time) * 1000
        record_tool_event("harness_status", duration, "success")
        return result

    if intent.kind is IntentKind.STOCK:
        start_time = time.perf_counter()
        result = stock_research("삼성전자")
        duration = (time.perf_counter() - start_time) * 1000
        record_tool_event("stock_research", duration, "success")
        return result

    if intent.kind is IntentKind.CODEX:
        start_time = time.perf_counter()
        codex_response = ask_codex(cleaned)
        duration = (time.perf_counter() - start_time) * 1000
        record_tool_event("ask_codex", duration, "success")
        return codex_response

    # 분류기가 새 의도를 추가할 때 안전한 기본값을 유지합니다.
    return "요청을 처리할 수 있는 의도를 찾지 못했습니다."


# -----------------------------------------------------------------------------
# 3. 메인 게이트웨이 폴링 루프
# -----------------------------------------------------------------------------

def start_gateway_polling() -> None:
    """Telegram 봇 폴링 데몬을 실행합니다."""
    bot_token = _load_env_token()
    if not bot_token:
        print("[오류] TELEGRAM_BOT_TOKEN이 설정되지 않았습니다.")
        print(".env 파일에 올바른 TELEGRAM_BOT_TOKEN을 입력해주세요.")
        return

    allowed_user_ids = _load_allowed_user_ids()
    if not allowed_user_ids:
        print("[오류] TELEGRAM_ALLOWED_USER_IDS가 비어 있거나 잘못되었습니다.")
        print("허용된 사용자 ID를 쉼표로 구분해 설정해주세요.")
        return

    # 기존 Webhook 충돌 해제는 명시적으로 opt-in한 경우에만 수행합니다.
    if _should_delete_webhook():
        ensure_webhook_deleted(bot_token)

    print("==================================================")
    print("🤖 Codex 기반 Telegram 게이트웨이 서비스 가동 중...")
    print("   - WIKI: G:\\내 드라이브\\WIKI 연동")
    print("   - 두뇌: OpenAI Codex CLI / Antigravity CLI 직결")
    print("   - 대기 중... (종료: Ctrl + C)")
    print("==================================================")

    current_offset: Optional[int] = None

    while True:
        try:
            updates = fetch_telegram_updates(bot_token, current_offset)
            for item in updates:
                update_id = item.get("update_id")
                current_offset = update_id + 1

                message_obj = item.get("message")
                if not message_obj:
                    continue

                if not _is_allowed_telegram_user(message_obj, allowed_user_ids):
                    continue

                chat_id = message_obj.get("chat", {}).get("id")
                user_text = message_obj.get("text", "")
                sender_name = message_obj.get("from", {}).get("first_name", "User")

                if not user_text or not chat_id:
                    continue

                print(f"\n[수신] {sender_name}: {user_text}")
                response_text = process_user_prompt(
                    user_text,
                    user_id=str(message_obj.get("from", {}).get("id")),
                    chat_id=str(chat_id),
                )
                print(f"[답변] {response_text[:60]}...")

                send_telegram_message(bot_token, chat_id, response_text)

        except KeyboardInterrupt:
            print("\n[알림] 사용자에 의해 게이트웨이가 종료되었습니다.")
            break
        except Exception as error:
            print(f"[루프 예외]: {str(error)}")
            time.sleep(3)


if __name__ == "__main__":
    start_gateway_polling()
