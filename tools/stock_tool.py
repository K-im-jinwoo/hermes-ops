"""
stock_tool.py - 주식 종목 시세 및 기본 동향 조회 도구

종목 심볼 또는 한글 종목명을 기반으로 현재 시세 및 요약 정보를 반환합니다.
추후 복잡한 리스크 분석이나 재시도 로직이 요구될 경우,
이 함수 내부에서 LangGraph 서브루프를 구동할 수 있도록 인터페이스를 단순하게 유지합니다.
"""

from __future__ import annotations

import json
from typing import Dict


def _query_stock_ticker(symbol: str) -> Dict[str, str]:
    """기본 종목 정보 데이터셋 조회 (실제 증권사/금융 API로 확장 가능)"""
    market_snapshot: Dict[str, Dict[str, str]] = {
        "005930": {"name": "삼성전자", "price": "78,200원", "change": "+1.3%"},
        "삼성전자": {"name": "삼성전자", "price": "78,200원", "change": "+1.3%"},
        "000660": {"name": "SK하이닉스", "price": "189,500원", "change": "+2.8%"},
        "sk하이닉스": {"name": "SK하이닉스", "price": "189,500원", "change": "+2.8%"},
        "AAPL": {"name": "Apple", "price": "$224.23", "change": "-0.5%"},
        "NVDA": {"name": "Nvidia", "price": "$128.90", "change": "+3.4%"},
    }

    normalized_key = symbol.strip()
    return market_snapshot.get(normalized_key, {})


def stock_research(symbol: str) -> str:
    """
    지정된 주식 종목의 현재가 및 등락률을 조회합니다.

    Args:
        symbol: 종목 코드 또는 종목명 (예: "005930", "삼성전자", "AAPL")

    Returns:
        종목 시세 요약 정보
    """
    cleaned_symbol = symbol.strip()
    if not cleaned_symbol:
        return "오류: 조회할 종목 코드나 회사명을 입력해주세요."

    ticker_info = _query_stock_ticker(cleaned_symbol)
    if not ticker_info:
        return f"'{cleaned_symbol}'에 대한 시세 정보를 찾을 수 없습니다."

    return (
        f"[{ticker_info['name']}] 현재가: {ticker_info['price']} "
        f"(전일 대비 {ticker_info['change']})"
    )


if __name__ == "__main__":
    print(stock_research("삼성전자"))
    print(stock_research("AAPL"))
    print(stock_research("없는회사"))
