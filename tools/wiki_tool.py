"""
wiki_tool.py - 실제 Obsidian LLM WIKI (.wiki) 연동 검색 및 파일 읽기 도구

로컬에 마운트된 개인 WIKI(G:\\내 드라이브\\WIKI\\wiki 등)를 검색하고,
필요 시 특정 마크다운 문서를 읽어오는 단일 책임 도구입니다.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional, Tuple


def _locate_wiki_root() -> Optional[Path]:
    """WIKI 루트 디렉터리를 우선순위(환경변수 -> codex 설정 -> 기본 드라이브)에 따라 탐색합니다."""
    env_root = os.getenv("LLM_WIKI_ROOT")
    if env_root and os.path.isdir(env_root):
        return Path(env_root)

    codex_config_path = Path("C:/Users/USER/.codex/wiki-config.json")
    if codex_config_path.is_file():
        try:
            with open(codex_config_path, mode="r", encoding="utf-8") as file:
                config = json.load(file)
                configured_root = config.get("wikiRoot")
                if configured_root and os.path.isdir(configured_root):
                    candidate = Path(configured_root)
                    wiki_subdir = candidate / "wiki"
                    return wiki_subdir if wiki_subdir.is_dir() else candidate
        except Exception:
            pass

    default_gdrive_path = Path(r"G:\내 드라이브\WIKI\wiki")
    if default_gdrive_path.is_dir():
        return default_gdrive_path

    return None


def _is_excluded_path(relative_path: str) -> bool:
    """검색에서 제외할 시스템 및 메타데이터 경로인지 확인합니다."""
    excluded_keywords = {".git", ".obsidian", "raw", "staging", "trash"}
    return any(part in excluded_keywords for part in Path(relative_path).parts)


def _scan_matching_documents(wiki_root: Path, query_terms: List[str], max_results: int) -> List[Tuple[str, str]]:
    """WIKI 루트 내 마크다운 파일을 순회하며 최신 날짜와 관련도 높은 순으로 검색합니다."""
    scored_matches: List[Tuple[int, str, str]] = []

    all_files = sorted(
        [p for p in wiki_root.rglob("*.md") if not _is_excluded_path(str(p.relative_to(wiki_root)))],
        key=lambda p: p.name,
        reverse=True
    )

    for file_path in all_files:
        rel_path = str(file_path.relative_to(wiki_root))
        normalized_rel_path = rel_path.lower()

        path_matches = sum(1 for term in query_terms if term in normalized_rel_path)

        try:
            with open(file_path, mode="r", encoding="utf-8", errors="ignore") as file:
                content_excerpt = file.read(1500)
        except Exception:
            continue

        normalized_content = content_excerpt.lower()
        content_matches = sum(1 for term in query_terms if term in normalized_content)

        if path_matches > 0 or content_matches > 0:
            score = (path_matches * 10) + content_matches
            # 운동 관련 질문 시 실제 운동 리소스에 높은 가중치 부여
            if "운동" in normalized_rel_path and "health" in normalized_rel_path:
                score += 50
            summary_snippet = content_excerpt[:300].strip().replace("\n", " ")
            scored_matches.append((score, rel_path, summary_snippet))

    scored_matches.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [(rel_path, snippet) for _, rel_path, snippet in scored_matches[:max_results]]


def wiki_search(query: str, max_results: int = 5) -> str:
    """
    개인 WIKI 지식 베이스(.wiki)에서 키워드와 관련된 문서를 검색합니다.

    Args:
        query: 검색할 단어 또는 질문 (예: "운동", "하네스", "n8n")
        max_results: 반환할 최대 결과 수 (기본값: 5)

    Returns:
        검색된 파일 경로와 요약 발췌문
    """
    cleaned_query = query.strip()
    if not cleaned_query:
        return "오류: 검색어를 입력해주세요."

    wiki_root = _locate_wiki_root()
    if not wiki_root:
        return "오류: .wiki 루트 디렉터리를 찾을 수 없습니다."

    query_terms = [term.lower() for term in cleaned_query.split() if term]
    if not query_terms:
        return "오류: 유효한 검색어가 없습니다."

    search_hits = _scan_matching_documents(wiki_root, query_terms, max_results)
    if not search_hits:
        return f"'{cleaned_query}'에 대한 WIKI 문서를 찾지 못했습니다."

    formatted_results = [f"[WIKI 검색 결과: '{cleaned_query}'] (총 {len(search_hits)}건)"]
    for path, snippet in search_hits:
        formatted_results.append(f"- 경로: {path}\n  내용: {snippet}...")

    return "\n\n".join(formatted_results)


def read_wiki_file(relative_path: str) -> str:
    """
    WIKI 내부의 특정 마크다운 파일 전체 내용을 읽습니다.

    Args:
        relative_path: WIKI 루트 기준 상대 경로 (예: "30_Resources/Health/2026-09-14_운동기록_하체.md")

    Returns:
        문서의 텍스트 본문
    """
    cleaned_path = relative_path.strip().replace("\\", "/")
    if not cleaned_path:
        return "오류: 읽을 파일 경로를 입력해주세요."

    if not cleaned_path.endswith(".md"):
        return "오류: 마크다운(.md) 파일만 읽을 수 있습니다."

    if ".." in cleaned_path or cleaned_path.startswith("/"):
        return "오류: 상위 디렉터리 이탈 경로는 허용되지 않습니다."

    wiki_root = _locate_wiki_root()
    if not wiki_root:
        return "오류: .wiki 루트 디렉터리를 찾을 수 없습니다."

    target_file = (wiki_root / cleaned_path).resolve()
    if not target_file.is_file():
        return f"오류: '{cleaned_path}' 파일이 존재하지 않습니다."

    try:
        with open(target_file, mode="r", encoding="utf-8") as file:
            content = file.read()
        return f"[WIKI 파일: {cleaned_path}]\n\n{content}"
    except Exception as err:
        return f"오류: 파일 읽기 실패 ({str(err)})"


if __name__ == "__main__":
    print(wiki_search("운동"))
