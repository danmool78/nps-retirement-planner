"""
visualization.py
================
plotly 기반 그래프 생성 모듈. 각 함수는 하나의 Figure 를 반환하며 Streamlit 에서 렌더링한다.

그래프 목록
1. fig_monthly_cashflow()      : 연령별 월 현금흐름(수입/지출/순액)
2. fig_cumulative_assets()     : 연령별 누적자산
3. fig_nps_by_claim_age()      : 국민연금 수령시점별 총수령액 비교
4. fig_shortfall_by_housing()  : 주택연금 개시시점별 부족액 비교
5. fig_heatmap()               : 국민연금 × 주택연금 개시나이 히트맵
6. fig_shortfall_by_inflation(): 물가상승률별 부족액
7. fig_best_by_life()          : 기대수명별 유리한 전략 비교
8. fig_pareto()                : 최적점 표시 Pareto Frontier

모든 금액은 '만원' 단위로 축약 표시(가독성).
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from cashflow import Scenario

_MAN = 10_000  # 원 -> 만원


# 1) 연령별 월 현금흐름 ------------------------------------------------------
def fig_monthly_cashflow(sc: Scenario, deaths=None) -> go.Figure:
    """
    선택된 전략의 월별 수입/지출/순현금흐름을 남편 나이축으로 표시.
    deaths: [(라벨, 남편나이축_사망나이)] — 사망 시점에 세로 점선을 그어 그래프 급변 이유를 표시.
    """
    df = sc.frame
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["husband_age"], y=df["income"] / _MAN,
                             name="연금 등 수입", line=dict(color="#2E86DE")))
    fig.add_trace(go.Scatter(x=df["husband_age"], y=df["expense"] / _MAN,
                             name="생활비 지출", line=dict(color="#E74C3C")))
    fig.add_trace(go.Scatter(x=df["husband_age"], y=df["net"] / _MAN,
                             name="순현금흐름", line=dict(color="#27AE60", dash="dot")))

    # 사망 시점 세로선(수입·지출이 급변하는 이유를 명시).
    for label, age in (deaths or []):
        fig.add_vline(x=age, line_dash="dash", line_color="#7F8C8D",
                      annotation_text=f"⚰️ {label}", annotation_position="top",
                      annotation_font_size=11, annotation_font_color="#566573")

    fig.update_layout(title="① 연령별 월 현금흐름", xaxis_title="남편 나이",
                      yaxis_title="월 금액(만원)", hovermode="x unified")
    return fig


# 2) 연령별 누적자산 ---------------------------------------------------------
def fig_cumulative_assets(sc: Scenario) -> go.Figure:
    """금융자산 잔액 추이. 0 에 닿는 시점이 자산 고갈."""
    df = sc.frame
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["husband_age"], y=df["assets"] / _MAN,
                             name="금융자산 잔액", fill="tozeroy", line=dict(color="#8E44AD")))
    fig.update_layout(title="② 연령별 누적자산", xaxis_title="남편 나이",
                      yaxis_title="금융자산(만원)", hovermode="x unified")
    return fig


# 3) 연금 수령시점별 총수령액 + 납입원금/원금확보 시점 -----------------------
def fig_nps_by_claim_age(df: pd.DataFrame, label: str = "남편") -> go.Figure:
    """
    수령개시나이별 명목 총수령액(막대) + 개시시점 월액(선).
    추가로 '납입원금' 수평선과 각 막대 위 '원금확보 나이'를 표시하여
    언제부터 받으면 몇 세에 원금을 회수하는지 함께 보여준다.
    """
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df["claim_age"], y=df["total_nominal"] / _MAN,
                         name="명목 총수령액", marker_color="#2E86DE"))
    fig.add_trace(go.Scatter(x=df["claim_age"], y=df["monthly"] / _MAN,
                             name="개시 월수령액", yaxis="y2", line=dict(color="#E67E22")))

    # 납입원금(입력이 있을 때만) 수평 기준선 + 원금확보 나이 주석.
    principal = float(df["principal"].iloc[0]) if "principal" in df and len(df) else 0.0
    if principal > 0:
        fig.add_hline(
            y=principal / _MAN, line_dash="dash", line_color="#C0392B",
            annotation_text=f"납입원금 {principal/_MAN:,.0f}만원",
            annotation_position="top left",
        )
        # 각 개시나이 막대 위에 '원금확보 XX세' 표시(회수 못하면 '미회수').
        for _, r in df.iterrows():
            be = r.get("breakeven_age")
            txt = f"원금확보<br>{int(be)}세" if be and not pd.isna(be) else "원금<br>미회수"
            fig.add_annotation(x=r["claim_age"], y=(r["total_nominal"] / _MAN),
                               text=txt, showarrow=False, yshift=14,
                               font=dict(size=9, color="#C0392B"))

    fig.update_layout(
        title=f"③ 연금 수령시점별 총수령액·원금확보 시점 ({label})",
        xaxis_title="수령개시나이",
        yaxis=dict(title="총수령액(만원)"),
        yaxis2=dict(title="월수령액(만원)", overlaying="y", side="right"),
        hovermode="x unified",
    )
    return fig


# 3-b) 나이별 누적 수령액 + 원금확보 시점(선 그래프) -------------------------
def fig_cumulative_receipts(curves, principal, breakevens, death, reps, monthlies=None,
                            label="남편") -> go.Figure:
    """
    수령개시나이별 '나이에 따른 누적 수령액' 선 그래프.

    - 범례에 개시나이별 **월수령액**(월 얼마 받는지)을 함께 표시.
    - 가로 빨간 점선 = 납입원금. 곡선이 이 선을 넘는 지점이 '원금확보(손익분기)'.
    - 세로 회색 점선 = 기대수명(그래프 우측 끝). 원금확보~기대수명 구간이 '이득 구간'.
    - 각 곡선의 원금확보 지점에 마커와 '원금확보 XX세·이득 YY년' 주석을 표시.
    원금확보가 기대수명보다 충분히 이르게(중간쯤) 올수록 이득 기간이 길다.
    """
    palette = ["#27AE60", "#2E86DE", "#E67E22", "#8E44AD"]
    monthlies = monthlies or {}
    fig = go.Figure()

    for i, ca in enumerate(reps):
        sub = curves[curves["claim_age"] == ca]
        color = palette[i % len(palette)]
        # 범례명에 '월 얼마'를 넣어 개시나이별 월수령액을 바로 보이게 함.
        mon = monthlies.get(ca)
        name = f"{ca}세 개시 · 월 {mon/_MAN:,.0f}만원" if mon else f"{ca}세 개시"
        fig.add_trace(go.Scatter(
            x=sub["age"], y=sub["cumulative"] / _MAN,
            mode="lines", name=name, line=dict(color=color, width=2),
        ))
        # 원금확보 지점 마커 + 주석(이득 기간 = 기대수명 - 원금확보나이).
        be = breakevens.get(ca)
        if be is not None:
            profit_years = max(0, death - be)
            fig.add_trace(go.Scatter(
                x=[be], y=[principal / _MAN], mode="markers",
                marker=dict(color=color, size=11, symbol="circle",
                            line=dict(width=1.5, color="white")),
                showlegend=False,
            ))
            fig.add_annotation(
                x=be, y=principal / _MAN,
                text=f"{ca}세개시→원금확보 {be}세·이득 {profit_years}년",
                showarrow=True, arrowhead=2, ax=0, ay=-30 - i * 18,
                font=dict(size=10, color=color),
            )

    # 납입원금 수평선.
    if principal > 0:
        fig.add_hline(y=principal / _MAN, line_dash="dash", line_color="#C0392B",
                      annotation_text=f"납입원금 {principal/_MAN:,.0f}만원",
                      annotation_position="bottom right")
    # 기대수명 수직선(그래프 우측 끝).
    fig.add_vline(x=death, line_dash="dot", line_color="gray",
                  annotation_text=f"기대수명 {death}세", annotation_position="top left")

    fig.update_layout(
        title=f"③ 나이별 누적 수령액·원금확보 시점 ({label})",
        xaxis_title="나이", yaxis_title="누적 수령액(만원)",
        hovermode="x unified",
    )
    return fig


# 4) 주택연금 개시시점별 부족액 ---------------------------------------------
def fig_shortfall_by_housing(df: pd.DataFrame) -> go.Figure:
    """주택연금 개시나이별 생활비 부족액총합."""
    fig = px.line(df, x="housing_age", y=df["shortfall_total"] / _MAN, markers=True)
    fig.update_traces(line_color="#E74C3C")
    fig.update_layout(title="④ 주택연금 개시시점별 부족액 비교",
                      xaxis_title="주택연금 개시나이", yaxis_title="부족액총합(만원)")
    return fig


# 5) 국민연금 × 주택연금 히트맵 ---------------------------------------------
def fig_heatmap(df: pd.DataFrame, value: str = "shortfall_total") -> go.Figure:
    """
    남편 국민연금 수령나이 × 주택연금 개시나이 조합의 지표 히트맵.
    (다른 축은 각 (h_claim, housing) 그룹의 최적값으로 집계)
    """
    sub = df[df["use_housing"]].copy()
    if sub.empty:
        return go.Figure().update_layout(title="⑤ 히트맵 (주택연금 조합 없음)")
    pivot = sub.pivot_table(index="h_claim", columns="housing", values=value, aggfunc="min")
    fig = px.imshow(
        pivot / _MAN,
        labels=dict(x="주택연금 개시나이", y="남편 국민연금 수령나이", color="부족액(만원)"),
        color_continuous_scale="RdYlGn_r",
        aspect="auto",
        text_auto=".0f",
    )
    fig.update_layout(title="⑤ 국민연금 × 주택연금 개시나이 히트맵(부족액)")
    return fig


# 6) 물가상승률별 부족액 -----------------------------------------------------
def fig_shortfall_by_inflation(df: pd.DataFrame) -> go.Figure:
    """물가상승률 시나리오별 부족액총합."""
    fig = px.bar(df, x=(df["inflation"] * 100), y=df["shortfall_total"] / _MAN)
    fig.update_traces(marker_color="#C0392B")
    fig.update_layout(title="⑥ 물가상승률별 생활비 부족액",
                      xaxis_title="물가상승률(%)", yaxis_title="부족액총합(만원)")
    return fig


# 7) 기대수명별 유리한 전략 --------------------------------------------------
def fig_best_by_life(df: pd.DataFrame) -> go.Figure:
    """기대수명별 최적 전략의 총수령액/잔여자산 비교 + 채택 수령나이 주석."""
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df["life"], y=df["total_pv"] / _MAN,
                         name="총수령액(현재가치)", marker_color="#2E86DE"))
    fig.add_trace(go.Bar(x=df["life"], y=df["bequest"] / _MAN,
                         name="잔여자산(상속)", marker_color="#27AE60"))
    # 각 막대 위에 채택된 수령나이 조합 주석.
    for _, r in df.iterrows():
        fig.add_annotation(x=r["life"], y=(r["total_pv"] / _MAN),
                           text=f"국민{int(r['h_claim'])}/{int(r['w_claim'])}세",
                           showarrow=False, yshift=12, font=dict(size=10))
    fig.update_layout(title="⑦ 기대수명별 유리한 전략 비교", barmode="group",
                      xaxis_title="기대수명(세)", yaxis_title="금액(만원)")
    return fig


# 8) Pareto Frontier ---------------------------------------------------------
def fig_pareto(df: pd.DataFrame, pareto: pd.DataFrame, best_id: int | None = None) -> go.Figure:
    """
    전체 조합 산점도 위에 파레토 경계와 최적점을 강조.
    x축: 총수령액(현재가치), y축: 부족액총합(작을수록 좋음).
    """
    fig = go.Figure()

    # --- 안전/위험 배경색(가로 띠). 아래(부족 적음)=안전, 위(부족 많음)=위험 ---
    # 안전 경계: 최대 부족액의 15% 지점(전부 0이면 작은 기본값)을 기준선으로 둔다.
    max_sf = float(df["shortfall_total"].max()) / _MAN
    safe_line = max_sf * 0.15 if max_sf > 0 else 1.0
    top = max_sf * 1.05 if max_sf > 0 else 10.0
    fig.add_hrect(y0=0, y1=safe_line, fillcolor="#27AE60", opacity=0.08, line_width=0,
                  annotation_text="🟢 안전구간 (부족 거의 없음)", annotation_position="top left",
                  annotation_font_color="#1E8449")
    fig.add_hrect(y0=safe_line, y1=top, fillcolor="#E74C3C", opacity=0.07, line_width=0,
                  annotation_text="🔴 위험구간 (부족 큼)", annotation_position="top left",
                  annotation_font_color="#C0392B")

    # 전체 조합(회색 점).
    fig.add_trace(go.Scatter(
        x=df["total_pv"] / _MAN, y=df["shortfall_total"] / _MAN,
        mode="markers", name="전체 조합",
        marker=dict(color="lightgray", size=6),
        text=[f"국민{h}/{w}세" for h, w in zip(df["h_claim"], df["w_claim"])],
    ))
    # 파레토 경계(빨간 선+점).
    fig.add_trace(go.Scatter(
        x=pareto["total_pv"] / _MAN, y=pareto["shortfall_total"] / _MAN,
        mode="lines+markers", name="Pareto 경계",
        line=dict(color="#E74C3C"), marker=dict(size=9, color="#E74C3C"),
    ))
    # 최적점 강조 + 주석.
    if best_id is not None and best_id in df["id"].values:
        b = df[df["id"] == best_id].iloc[0]
        bx = float(b["total_pv"]) / _MAN
        by = float(b["shortfall_total"]) / _MAN
        housing = f"주택 {int(b['housing'])}세" if b.get("use_housing") else "주택 미사용"
        fig.add_trace(go.Scatter(
            x=[bx], y=[by], mode="markers", name="⭐추천 최적점",
            marker=dict(size=18, color="#F1C40F", symbol="star",
                        line=dict(width=1.2, color="black")),
        ))
        fig.add_annotation(
            x=bx, y=by,
            text=f"⭐ 추천: 부족 0 + 최대수령<br>국민 {int(b['h_claim'])}/{int(b['w_claim'])}세 · {housing}",
            showarrow=True, arrowhead=2, ax=30, ay=40,
            font=dict(size=11, color="#B7950B"), bgcolor="rgba(255,255,255,0.75)",
            bordercolor="#F1C40F", borderwidth=1,
        )
    fig.update_layout(title="⑧ Pareto Frontier (총수령액↑ · 부족액↓)",
                      xaxis_title="총수령액 현재가치(만원)",
                      yaxis_title="부족액총합(만원)")
    return fig


# 조합별 점수 산점도 ----------------------------------------------------------
def _combo_label(row) -> str:
    """한 조합의 수령개시 조건 텍스트(국민연금 나이 / 주택연금 나이)."""
    use_h = bool(row.get("use_housing"))
    housing = "주택 미사용"
    if use_h and row.get("housing") is not None and not pd.isna(row.get("housing")):
        housing = f"주택 {int(row['housing'])}세"
    return f"국민 {int(row['h_claim'])}/{int(row['w_claim'])}세 · {housing}"


def fig_score_scatter(df: pd.DataFrame, view: str = "stable",
                      best_id: int | None = None) -> go.Figure:
    """
    총수령액(→) 대비 잔여자산(↑) 산점도. 색상=관점 점수(밝을수록 좋음).
    - 각 점 hover 에 수령개시 조건(국민연금·주택연금 나이) 표시.
    - best_id 가 주어지면 ⭐추천 조합을 별표로 강조하고 조건을 라벨로 붙인다.

    plotly 버전 호환을 위해 pandas Series 대신 순수 list 를 전달한다.
    """
    x = (df["total_pv"] / _MAN).tolist()
    y = (df["bequest"] / _MAN).tolist()
    colors = df[f"score_{view}"].tolist()
    hover = [_combo_label(r) for _, r in df.iterrows()]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=y, mode="markers",
        marker=dict(color=colors, colorscale="Viridis", size=7,
                    colorbar=dict(title=dict(text="점수")), showscale=True),
        text=hover, hovertemplate="%{text}<br>총수령 %{x:,.0f}만·상속 %{y:,.0f}만<extra></extra>",
        name="조합",
    ))

    # ⭐ 추천 조합 별표 + 조건 라벨.
    ids = df["id"].tolist()
    if best_id is not None and best_id in ids:
        b = df[df["id"] == best_id].iloc[0]
        bx = float(b["total_pv"]) / _MAN
        by = float(b["bequest"]) / _MAN
        label = _combo_label(b)
        fig.add_trace(go.Scatter(
            x=[bx], y=[by], mode="markers", name="⭐추천 조합",
            marker=dict(size=20, color="#F1C40F", symbol="star",
                        line=dict(width=1.5, color="black")),
            text=[label], hovertemplate="추천: %{text}<extra></extra>",
        ))
        fig.add_annotation(x=bx, y=by, text=f"⭐ 추천: {label}",
                           showarrow=True, arrowhead=2, ax=0, ay=-35,
                           font=dict(size=12, color="#B7950B"),
                           bgcolor="rgba(255,255,255,0.7)")

    fig.update_layout(title=f"⑨ 조합별 점수 산점도 ({view})",
                      xaxis_title="총수령액 현재가치(만원)", yaxis_title="잔여자산(만원)")
    return fig
