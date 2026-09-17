"""
test_tools.py - 도구 단위 테스트

실제 .wiki 연동, Antigravity CLI, Codex CLI, 하네스, 주식, 훅의
입력 검증 및 조기 반환(Early Return) 동작을 검증합니다.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from tools.wiki_tool import read_wiki_file, wiki_search
from tools.antigravity_tool import ask_antigravity
from tools.codex_tool import ask_codex
from tools.harness_tool import harness_status
from tools.stock_tool import stock_research
from hooks.metrics_hook import record_tool_event


class TestWikiTool:
    def test_empty_query_returns_error(self):
        result = wiki_search("   ")
        assert "오류: 검색어를 입력해주세요." in result

    def test_search_real_wiki_returns_results(self):
        result = wiki_search("운동")
        assert "WIKI 검색 결과" in result

    def test_read_wiki_file_path_traversal_blocked(self):
        result = read_wiki_file("../secret.md")
        assert "상위 디렉터리 이탈" in result

    def test_read_wiki_file_non_md_blocked(self):
        result = read_wiki_file("image.png")
        assert "마크다운(.md) 파일만" in result


class TestCliTools:
    def test_antigravity_empty_prompt_returns_error(self):
        result = ask_antigravity("  ")
        assert "오류: Antigravity에 전달할 프롬프트" in result

    def test_codex_empty_prompt_returns_error(self):
        result = ask_codex("  ")
        assert "오류: Codex에 전달할 프롬프트" in result


class TestDomainTools:
    def test_harness_empty_name_returns_error(self):
        result = harness_status("")
        assert "오류: 상태를 확인할 프로젝트" in result

    def test_stock_empty_symbol_returns_error(self):
        result = stock_research("  ")
        assert "오류: 조회할 종목 코드" in result


class TestMetricsHook:
    def test_record_tool_event_creates_valid_jsonl(self, tmp_path: Path):
        test_log_file = tmp_path / "test_events.jsonl"
        event = record_tool_event(
            tool_name="test_tool",
            duration_ms=15.5,
            status="success",
            log_destination=str(test_log_file)
        )

        assert test_log_file.exists()
        with open(test_log_file, "r", encoding="utf-8") as file:
            data = json.loads(file.readline())
            assert data["tool_name"] == "test_tool"
            assert data["duration_ms"] == 15.5
