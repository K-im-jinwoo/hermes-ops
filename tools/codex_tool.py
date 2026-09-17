"""
codex_tool.py - OpenAI Codex CLI 연동 도구

Hermes 에이전트가 Codex 에이전트에게 코드 분석, 리팩토링,
엔지니어링 태스크를 위임할 때 호출하는 단일 책임 도구입니다.
"""

from __future__ import annotations

import os
import subprocess


def ask_codex(prompt: str, timeout_seconds: int = 45) -> str:
    """
    Codex CLI를 비대화형(exec) 모드로 실행하여 코드 생성 및 분석 결과를 가져옵니다.

    Args:
        prompt: Codex에 전달할 지시문 또는 코드 질문
        timeout_seconds: 실행 제한 시간(초)

    Returns:
        Codex의 실행 결과 텍스트
    """
    cleaned_prompt = prompt.strip()
    if not cleaned_prompt:
        return "오류: Codex에 전달할 프롬프트를 입력해주세요."

    # Windows 환경에서 npm 전역 스크립트인 codex.cmd를 호출
    command = ["cmd.exe", "/c", "codex", "exec", "--skip-git-repo-check", cleaned_prompt]

    try:
        process_result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False
        )

        output_text = process_result.stdout.strip()
        if output_text:
            return output_text

        # stdout이 비어 있는 경우 stderr(오류 또는 사용량 제한 안내) 확인
        error_details = process_result.stderr.strip()
        if error_details:
            return f"[Codex 메시지]\n{error_details}"

        return "(Codex 응답 없음)"
    except subprocess.TimeoutExpired:
        return f"오류: Codex 응답 시간 초과 ({timeout_seconds}초 초과)"
    except Exception as exc:
        return f"오류: Codex 실행 중 예외 발생 ({str(exc)})"


if __name__ == "__main__":
    print(ask_codex("간단한 인사말 한 줄 출력해줘"))
