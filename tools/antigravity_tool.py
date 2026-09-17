"""
antigravity_tool.py - Antigravity CLI (agy) 연동 도구

Hermes 에이전트가 Google Antigravity 에이전트에게 질의하거나
고급 추론/코딩 작업을 위임할 때 호출하는 단일 책임 도구입니다.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Optional


def _locate_agy_executable() -> Optional[str]:
    """시스템 PATH 또는 표준 설치 경로에서 agy 실행 파일을 찾습니다."""
    system_path = shutil.which("agy")
    if system_path:
        return system_path

    standard_local_path = os.path.expandvars(r"%LOCALAPPDATA%\agy\bin\agy.exe")
    if os.path.isfile(standard_local_path):
        return standard_local_path

    return None


def ask_antigravity(prompt: str, timeout_seconds: int = 40) -> str:
    """
    Antigravity CLI(agy)를 실행하여 질문에 대한 답변이나 코드 생성 결과를 가져옵니다.

    Args:
        prompt: Antigravity에 전달할 지시문 또는 질문
        timeout_seconds: 실행 제한 시간(초)

    Returns:
        Antigravity의 실행 결과 텍스트
    """
    cleaned_prompt = prompt.strip()
    if not cleaned_prompt:
        return "오류: Antigravity에 전달할 프롬프트를 입력해주세요."

    executable = _locate_agy_executable()
    if not executable:
        return "오류: 시스템에서 'agy' 실행 파일을 찾을 수 없습니다."

    try:
        process_result = subprocess.run(
            [executable, "-p", cleaned_prompt],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False
        )

        output_text = process_result.stdout.strip()
        if process_result.returncode != 0:
            error_details = process_result.stderr.strip()
            return f"오류: Antigravity 실행 실패 (종료 코드 {process_result.returncode}): {error_details}"

        return output_text if output_text else "(응답 없음)"
    except subprocess.TimeoutExpired:
        return f"오류: Antigravity 응답 시간 초과 ({timeout_seconds}초 초과)"
    except Exception as exc:
        return f"오류: Antigravity 실행 중 예외 발생 ({str(exc)})"


if __name__ == "__main__":
    print(ask_antigravity("1+1은 뭐야? 단답형으로 숫자만 출력해줘"))
