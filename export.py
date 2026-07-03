"""
export.py
=========
결과를 CSV / Excel / HTML 리포트로 내보내는 유틸.

- to_csv_bytes()      : 조합 요약표를 CSV 바이트로 변환(다운로드용)
- to_excel_bytes()    : 요약표 + 선택 시나리오 월별표를 여러 시트로 담은 Excel 바이트
- build_html_report() : 입력요약·3관점표·그래프 전체를 담은 자체완결 HTML(브라우저에서 PDF 저장용)
"""

from __future__ import annotations

import io
from datetime import date

import pandas as pd
import plotly.io as pio
from plotly.offline import get_plotlyjs

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


# ---------------------------------------------------------------------------
# HTML 리포트(브라우저에서 인쇄 → PDF 저장용)
# ---------------------------------------------------------------------------
_REPORT_CSS = """
body{font-family:'Malgun Gothic','Apple SD Gothic Neo',sans-serif;margin:24px;color:#222;}
h1{border-bottom:3px solid #2E86DE;padding-bottom:8px;}
h2{margin-top:28px;color:#1A5276;border-left:5px solid #2E86DE;padding-left:8px;}
table{border-collapse:collapse;margin:8px 0;font-size:13px;width:100%;}
th,td{border:1px solid #ccc;padding:6px 8px;text-align:center;}
th{background:#EBF5FB;}
.meta{color:#555;font-size:13px;}
.chart{margin:10px 0 26px;}
@media print{h2{page-break-before:auto;} .chart{page-break-inside:avoid;}}
"""


def _tops_table_html(top: pd.DataFrame, view: str) -> str:
    """한 관점의 상위 5개 표를 HTML 표로 변환."""
    rows = ["<tr><th>순위</th><th>국민연금 나이(남/여)</th><th>주택연금</th>"
            "<th>총수령(현가)</th><th>부족개월</th><th>상속</th><th>점수</th></tr>"]
    for i, (_, r) in enumerate(top.iterrows(), 1):
        housing = f"{int(r['housing'])}세" if r.get("use_housing") else "미사용"
        rows.append(
            f"<tr><td>{i}</td><td>{int(r['h_claim'])}/{int(r['w_claim'])}세</td>"
            f"<td>{housing}</td><td>{r['total_pv']/1e8:.2f}억</td>"
            f"<td>{r['shortfall_months']:.0f}개월</td><td>{r['bequest']/1e8:.2f}억</td>"
            f"<td>{r[f'score_{view}']:.3f}</td></tr>"
        )
    return "<table>" + "".join(rows) + "</table>"


def build_html_report(figs, tops: dict, summary: dict) -> bytes:
    """
    전체 결과를 담은 자체완결 HTML 리포트를 생성.

    figs    : [(제목, plotly Figure), ...]
    tops    : {"stable": df, "maximize": df, "bequest": df}  (관점별 상위 5)
    summary : {"inputs": [(라벨,값)...], "margin": str, "normal_ages": str, "n_combos": int}

    plotly.js 를 인라인으로 넣어 인터넷 없이도 열리며, 브라우저에서 인쇄(Ctrl+P) →
    'PDF로 저장'하면 한글·그래프가 그대로 보존된 PDF가 만들어진다.
    """
    parts = [f"<h1>👴👵 부부 노후자금 시뮬레이션 리포트</h1>",
             f"<p class='meta'>작성일: {date.today().isoformat()} · "
             f"평가 조합 수: {summary.get('n_combos', 0):,}개 · {summary.get('normal_ages','')}</p>"]

    # 입력 요약
    parts.append("<h2>📋 입력 요약</h2><table>")
    for label, value in summary.get("inputs", []):
        parts.append(f"<tr><th style='text-align:left;width:220px'>{label}</th>"
                     f"<td style='text-align:left'>{value}</td></tr>")
    parts.append("</table>")

    # 물가 안전 마진
    if summary.get("margin"):
        parts.append(f"<h2>🌡️ 물가 안전 마진</h2><p>{summary['margin']}</p>")

    # 3관점 상위 5
    view_ko = {"stable": "🛡️ 안정형", "maximize": "📈 총수령액 극대화형", "bequest": "🎁 상속중시형"}
    parts.append("<h2>🏆 성향별 추천 전략 (상위 5)</h2>")
    for view, ko in view_ko.items():
        if view in tops:
            parts.append(f"<h3>{ko}</h3>{_tops_table_html(tops[view], view)}")

    # 그래프
    parts.append("<h2>📊 그래프</h2>")
    for caption, fig in figs:
        chart = pio.to_html(fig, include_plotlyjs=False, full_html=False,
                            default_width="100%", default_height="430px")
        parts.append(f"<div class='chart'>{chart}</div>")

    html = (f"<!DOCTYPE html><html lang='ko'><head><meta charset='utf-8'>"
            f"<title>노후자금 리포트</title><style>{_REPORT_CSS}</style>"
            f"<script>{get_plotlyjs()}</script></head><body>"
            f"{''.join(parts)}"
            f"<p class='meta' style='margin-top:30px'>※ 본 리포트의 연금액은 근사 계산이며 "
            f"실제 수급액과 다를 수 있습니다. 저장하려면 브라우저에서 Ctrl+P → 'PDF로 저장'.</p>"
            f"</body></html>")
    return html.encode("utf-8")
