"""
export.py
=========
결과를 CSV / Excel 로 내보내는 유틸.

- to_csv_bytes()   : 조합 요약표를 CSV 바이트로 변환(다운로드용)
- to_excel_bytes() : 요약표 + 선택 시나리오 월별표를 여러 시트로 담은 Excel 바이트
"""

from __future__ import annotations

import io

import pandas as pd

from cashflow import Scenario

# 화면 표시에 쓰는 컬럼 한글 라벨 매핑.
COLUMN_LABELS = {
    "h_claim": "남편수령나이",
    "w_claim": "아내수령나이",
    "housing": "주택연금개시",
    "use_chunap": "추납",
    "use_voluntary": "임의가입",
    "total_nominal": "명목총수령액",
    "total_pv": "총수령액(현재가치)",
    "shortfall_total": "부족액총합",
    "shortfall_months": "부족개월수",
    "worst_shortfall": "최악월부족액",
    "depletion_age": "자산고갈나이",
    "bequest": "잔여자산(상속)",
    "score_stable": "안정형점수",
    "score_maximize": "총수령액극대화점수",
    "score_bequest": "상속중시점수",
}


def _relabel(df: pd.DataFrame) -> pd.DataFrame:
    """존재하는 컬럼만 한글 라벨로 변경한 사본 반환."""
    cols = {k: v for k, v in COLUMN_LABELS.items() if k in df.columns}
    return df[list(cols.keys())].rename(columns=cols)


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    """요약표를 UTF-8 (BOM) CSV 바이트로. (엑셀 한글 깨짐 방지 위해 utf-8-sig)"""
    return _relabel(df).to_csv(index=False).encode("utf-8-sig")


def to_excel_bytes(summary: pd.DataFrame, scenario: Scenario | None = None) -> bytes:
    """요약표와(선택) 월별 현금흐름표를 담은 Excel 바이트 반환."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        _relabel(summary).to_excel(writer, sheet_name="조합요약", index=False)
        if scenario is not None:
            scenario.frame.to_excel(writer, sheet_name="월별현금흐름", index=False)
    return buf.getvalue()
