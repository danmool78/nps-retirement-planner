"""
scenarios.py
============
시나리오 비교: 현재 결과를 이름 붙여 저장하고(세션 동안) 핵심 지표를 나란히 비교한다.

- 저장 내용: 입력값 쿼리 문자열(불러오기·링크용) + 결과 핵심 지표(다시 계산하지 않고 바로 비교).
- 저장은 이 브라우저 탭(세션) 동안 유지된다. 오래 보관하려면 각 시나리오의 링크를 저장하면 된다.
"""

from __future__ import annotations

import html

MAX_SCENARIOS = 5

# 비교표 행: (라벨, 지표 키, 표시 함수, 좋은 방향) — 좋은 방향 'max'/'min'/None(강조 안 함)
def _eok(v: float) -> str:
    return f"{v/1e8:,.2f}억" if abs(v) >= 1e8 else f"{v/1e4:,.0f}만"


ROWS = [
    ("은퇴나이 · 월 생활비", "inputs", lambda m: m, None),
    ("추천 연금 개시", "claims", lambda m: m, None),
    ("주택연금 개시", "housing", lambda m: m, None),
    ("생활비 부족", "shortfall_total",
     lambda v: "없음" if v <= 0 else f"{_eok(v)} 부족", "min"),
    ("남는 재산(상속)", "bequest", _eok, "max"),
    ("평생 총수령(현재가치)", "total_pv", _eok, "max"),
    ("물가 안전 마진", "margin_value", lambda v: "0% 미만" if v is None else f"~{v*100:.1f}%", "max"),
    ("투자 변동성 성공확률", "success_rate", lambda v: f"{v*100:.0f}%", "max"),
]


def summarize(name: str, query: str, user, R) -> dict:
    """현재 결과에서 비교에 필요한 값만 뽑아 저장용 dict 로."""
    b = R["tops"]["stable"].iloc[0]
    return {
        "name": name,
        "query": query,
        "inputs": f"{user.retirement_age}세 · {user.living_expense_monthly/1e4:,.0f}만원",
        "claims": (f"{int(b['h_claim'])}세" if user.is_single
                   else f"{int(b['h_claim'])}세 / {int(b['w_claim'])}세"),
        "housing": f"{int(b['housing'])}세" if b["use_housing"] else "미사용",
        "shortfall_total": float(b["shortfall_total"]),
        "bequest": float(b["bequest"]),
        "total_pv": float(b["total_pv"]),
        "margin_value": R["margin"],
        "success_rate": float(R["montecarlo"]["success_rate"]),
    }


def _best_index(values, direction):
    """가장 좋은 값의 위치(동점이거나 비교 불가면 None)."""
    if direction is None or len(values) < 2:
        return None
    keyed = [(-1e18 if v is None else v) for v in values]
    target = max(keyed) if direction == "max" else min(keyed)
    hits = [i for i, v in enumerate(keyed) if v == target]
    return hits[0] if len(hits) == 1 else None


def table_html(items: list) -> str:
    """시나리오들(열)을 지표(행)로 비교하는 표. 행마다 가장 좋은 값을 초록으로 강조."""
    head = "".join(f"<th>{html.escape(it['name'])}</th>" for it in items)
    body = []
    for label, key, fmt, direction in ROWS:
        vals = [it.get(key) for it in items]
        best = _best_index(vals, direction)
        cells = "".join(
            f'<td class="{"best" if i == best else ""}">{html.escape(str(fmt(v)))}</td>'
            for i, v in enumerate(vals))
        body.append(f"<tr><th>{label}</th>{cells}</tr>")
    return (f'<div class="tbl-wrap"><table class="bd sc"><thead><tr><th>항목</th>{head}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')
