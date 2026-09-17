"""
metrics_hook.py - Hermes 에이전트 텔레메트리 및 로깅 훅

LangSmith 없이도 도구 호출 지연 시간(duration_ms), 성공/실패 여부,
사용된 도구명을 JSON Lines 형식으로 영구 보관합니다.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


def _ensure_log_directory_exists(file_path: str) -> None:
    """로그 파일이 위치할 상위 디렉터리를 생성합니다."""
    log_directory = Path(file_path).parent
    log_directory.mkdir(parents=True, exist_ok=True)


def _append_log_entry(file_path: str, record: Dict[str, Any]) -> None:
    """단일 JSON 레코드를 파일 끝에 추가합니다."""
    _ensure_log_directory_exists(file_path)
    with open(file_path, mode="a", encoding="utf-8") as file:
        json_line = json.dumps(record, ensure_ascii=False)
        file.write(json_line + "\n")


def record_tool_event(
    tool_name: str,
    duration_ms: float,
    status: str,
    error_message: Optional[str] = None,
    log_destination: Optional[str] = None,
) -> Dict[str, Any]:
    """
    도구 실행 결과를 포맷팅하여 JSONL 로그 파일에 기록합니다.

    Args:
        tool_name: 실행된 도구 함수 이름
        duration_ms: 실행 소요 시간(밀리초)
        status: 실행 결과 ("success" 또는 "error")
        error_message: 실패 시 전달된 에러 메시지
        log_destination: 기록할 로그 파일 경로

    Returns:
        기록된 로그 엔트리 딕셔너리
    """
    destination = log_destination or os.getenv(
        "HERMES_METRICS_LOG",
        "./logs/events.jsonl",
    )
    timestamp = datetime.now(timezone.utc).isoformat()

    event_payload: Dict[str, Any] = {
        "timestamp": timestamp,
        "event_type": "tool_execution",
        "tool_name": tool_name,
        "duration_ms": round(duration_ms, 2),
        "status": status,
    }

    if error_message:
        event_payload["error"] = error_message

    _append_log_entry(destination, event_payload)
    return event_payload


# Hermes Hook 호환 인터페이스
def post_tool_call(tool_name: str, duration_ms: float, success: bool, error: Optional[Exception] = None) -> None:
    """Hermes Agent의 post_tool_call 이벤트 발생 시 호출되는 콜백 핸들러입니다."""
    status = "success" if success else "error"
    error_text = str(error) if error else None

    record_tool_event(
        tool_name=tool_name,
        duration_ms=duration_ms,
        status=status,
        error_message=error_text
    )


if __name__ == "__main__":
    test_record = record_tool_event(
        tool_name="wiki_search",
        duration_ms=45.2,
        status="success"
    )
    print(f"테스트 로그 기록 완료: {test_record}")
