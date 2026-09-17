"""
harness_tool.py - 하네스(Harness) 실행 상태 및 파이프라인 모니터링 도구

진행 중인 하네스 프로세스, 테스트 파이프라인, 백그라운드 작업의 현재 상태를 점검합니다.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Optional


def _fetch_remote_harness_status(api_url: str, project_name: str, timeout_seconds: int = 5) -> Optional[str]:
    """원격 하네스 서버에서 프로젝트 상태를 조회합니다."""
    encoded_name = urllib.parse.quote(project_name)
    request_url = f"{api_url}?project={encoded_name}"

    request = urllib.request.Request(
        request_url,
        headers={"User-Agent": "Hermes-Agent/1.0", "Accept": "application/json"}
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            if response.status != 200:
                return None
            body = response.read().decode("utf-8")
            data = json.loads(body)
            return data.get("status_summary")
    except Exception:
        return None


def _get_mock_harness_status(project_name: str) -> str:
    """로컬 테스트용 모의 하네스 상태를 반환합니다."""
    registered_projects = {
        "codex": "현재 3단계 코드 리뷰 및 테스트 자동 실행 중 (진행률: 75%)",
        "gemini": "대기 중 (최근 완료: 10분 전)",
        "eval": "벤치마크 평가 진행 중 (12/50 완료)"
    }

    normalized_name = project_name.strip().lower()
    for name, status in registered_projects.items():
        if name in normalized_name:
            return f"[하네스:{project_name}] {status}"

    return f"[하네스:{project_name}] 가동 중인 작업 없음 (유휴 상태)"


def harness_status(project_name: str = "default") -> str:
    """
    하네스 파이프라인 또는 백그라운드 에이전트 작업의 진행 상태를 조회합니다.

    Args:
        project_name: 확인할 프로젝트 이름 (예: "codex", "gemini", "eval")

    Returns:
        하네스 현재 동작 상태 요약
    """
    cleaned_name = project_name.strip()
    if not cleaned_name:
        return "오류: 상태를 확인할 프로젝트 이름을 지정해주세요."

    api_url = os.getenv("HARNESS_API_URL")
    if api_url:
        remote_status = _fetch_remote_harness_status(api_url, cleaned_name)
        if remote_status:
            return f"[원격 하네스] {remote_status}"

    return _get_mock_harness_status(cleaned_name)


if __name__ == "__main__":
    print(harness_status("codex"))
    print(harness_status("gemini"))
    print(harness_status("unknown"))
