"""
verify_tool_calling.py - Karpathy 스타일 Micro-Agent 루프

프레임워크의 과도한 마법 없이 다음 도구들의 라우팅 및 실행을 명시적으로 검증합니다:
1. .wiki 검색 및 읽기 (실제 Obsidian WIKI 연동)
2. Antigravity CLI (agy) 실행
3. OpenAI Codex CLI (codex) 실행
4. 하네스 상태 모니터링
5. 주식 시세 조회
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import time
from typing import Any, Callable, Dict, List

# 프로젝트 루트 경로를 sys.path에 추가
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from tools.wiki_tool import read_wiki_file, wiki_search
from tools.antigravity_tool import ask_antigravity
from tools.codex_tool import ask_codex
from tools.harness_tool import harness_status
from tools.stock_tool import stock_research
from intent_router import IntentKind, classify_intent


# -----------------------------------------------------------------------------
# 1. 도구 레지스트리 및 스키마
# -----------------------------------------------------------------------------

TOOL_REGISTRY: Dict[str, Callable[..., Any]] = {
    "wiki_search": wiki_search,
    "read_wiki_file": read_wiki_file,
    "ask_antigravity": ask_antigravity,
    "ask_codex": ask_codex,
    "harness_status": harness_status,
    "stock_research": stock_research,
}

TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "wiki_search",
            "description": "실제 개인 Obsidian .wiki 문서에서 키워드를 검색합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "검색할 단어나 문장"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_wiki_file",
            "description": "WIKI 내부의 특정 마크다운 파일 전체 내용을 읽습니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "relative_path": {"type": "string", "description": "WIKI 루트 기준 상대 파일 경로"}
                },
                "required": ["relative_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ask_antigravity",
            "description": "Google Antigravity CLI(agy)에 고급 추론 또는 코딩 질문을 전달합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Antigravity에 보낼 프롬프트"}
                },
                "required": ["prompt"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ask_codex",
            "description": "OpenAI Codex CLI에 코딩 또는 엔지니어링 분석 질문을 전달합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Codex에 보낼 프롬프트"}
                },
                "required": ["prompt"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "harness_status",
            "description": "하네스 및 파이프라인의 작업 상태를 점검합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_name": {"type": "string", "description": "조회할 프로젝트 명칭"}
                },
                "required": ["project_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "stock_research",
            "description": "주식 종목의 현재 가격과 상태를 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "종목 코드 또는 이름"}
                },
                "required": ["symbol"]
            }
        }
    }
]


# -----------------------------------------------------------------------------
# 2. 도구 실행 디스패처
# -----------------------------------------------------------------------------

def execute_tool_call(tool_name: str, raw_arguments: str) -> Dict[str, Any]:
    """도구를 안전하게 실행하고 지연시간과 결과를 반환합니다."""
    if tool_name not in TOOL_REGISTRY:
        return {
            "status": "error",
            "error_message": f"등록되지 않은 도구: {tool_name}",
            "duration_ms": 0.0,
            "result": None
        }

    try:
        parsed_args = json.loads(raw_arguments) if raw_arguments else {}
    except json.JSONDecodeError as err:
        return {
            "status": "error",
            "error_message": f"인자 JSON 파싱 실패: {str(err)}",
            "duration_ms": 0.0,
            "result": None
        }

    start_time = time.perf_counter()
    try:
        execution_result = TOOL_REGISTRY[tool_name](**parsed_args)
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return {
            "status": "success",
            "tool_name": tool_name,
            "duration_ms": round(elapsed_ms, 2),
            "result": execution_result
        }
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return {
            "status": "error",
            "tool_name": tool_name,
            "duration_ms": round(elapsed_ms, 2),
            "error_message": f"예외 발생: {str(exc)}",
            "result": None
        }


# -----------------------------------------------------------------------------
# 3. 모의(Mock) LLM 라우터
# -----------------------------------------------------------------------------

def mock_llm_router(user_prompt: str) -> Dict[str, Any]:
    """공유 자연어 분류 결과를 검증용 도구 호출 JSON으로 변환합니다."""
    intent = classify_intent(user_prompt)

    if intent.kind is IntentKind.ANTIGRAVITY:
        return {
            "tool_calls": [{
                "id": "call_agy_001",
                "type": "function",
                "function": {
                    "name": "ask_antigravity",
                    "arguments": json.dumps({"prompt": user_prompt})
                }
            }]
        }

    if intent.kind is IntentKind.CODEX:
        return {
            "tool_calls": [{
                "id": "call_codex_002",
                "type": "function",
                "function": {
                    "name": "ask_codex",
                    "arguments": json.dumps({"prompt": user_prompt})
                }
            }]
        }

    if intent.kind is IntentKind.WIKI_READ:
        return {
            "tool_calls": [{
                "id": "call_wiki_003",
                "type": "function",
                "function": {
                    "name": "wiki_search",
                    "arguments": json.dumps({"query": user_prompt})
                }
            }]
        }

    if intent.kind is IntentKind.HARNESS:
        return {
            "tool_calls": [{
                "id": "call_harness_004",
                "type": "function",
                "function": {
                    "name": "harness_status",
                    "arguments": json.dumps({"project_name": "Codex"})
                }
            }]
        }

    if intent.kind is IntentKind.STOCK:
        return {
            "tool_calls": [{
                "id": "call_stock_005",
                "type": "function",
                "function": {
                    "name": "stock_research",
                    "arguments": json.dumps({"symbol": "삼성전자"})
                }
            }]
        }

    if intent.kind is IntentKind.MEMO_WRITE:
        return {
            "content": (
                "메모 저장 요청을 확인했습니다. 실제 저장 대상은 "
                "wiki/00_Inbox입니다."
            )
        }

    if intent.kind is IntentKind.MEMO_APPROVE:
        return {
            "content": (
                "메모 승인 요청을 확인했습니다. 실제 저장은 게이트웨이의 "
                "사용자·채팅·만료 검증 후 수행됩니다."
            )
        }

    if intent.kind is IntentKind.HELP:
        return {"content": "사용 가능한 기능을 확인했습니다."}

    return {
        "content": (
            "요청을 정확히 이해하지 못했습니다. WIKI 조회, 메모 저장, "
            "코드 작업, 하네스 상태 확인 중 어떤 작업인지 알려주세요."
        )
    }


# -----------------------------------------------------------------------------
# 4. 에이전트 실행 루프
# -----------------------------------------------------------------------------

def run_agent_turn(user_input: str) -> None:
    """단일 턴의 질문 분석, 도구 디스패치, 결과 합성을 수행합니다."""
    print(f"\n==========================================")
    print(f"[사용자 입력]: {user_input}")
    print(f"==========================================")

    decision = mock_llm_router(user_input)
    if "tool_calls" not in decision:
        print(f"[LLM 응답]: {decision.get('content')}")
        return

    tool_call = decision["tool_calls"][0]
    func_name = tool_call["function"]["name"]
    func_args = tool_call["function"]["arguments"]

    print(f"[LLM 라우팅]: 도구 '{func_name}' 선택 (인자: {func_args})")
    execution = execute_tool_call(func_name, func_args)
    print(f"[실행 소요시간]: {execution['duration_ms']}ms")
    print(f"[도구 반환 결과]:\n{execution['result']}")


if __name__ == "__main__":
    queries = [
        "위키에서 최근 운동 기록 찾아줘",
        "antigravity에게 3+5가 뭔지 단답형으로 물어봐줘",
        "codex에게 파이썬으로 현재 날짜 출력하는 코드 한 줄 물어봐줘",
        "하네스 진행 상태 점검해줘",
        "삼성전자 시세 알려줘"
    ]

    for q in queries:
        run_agent_turn(q)
