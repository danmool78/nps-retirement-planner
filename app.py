"""
app.py
======
부부 노후자금 계획 시뮬레이터 — Streamlit 진입점.

실행:  streamlit run app.py

구성
- 좌측 사이드바 : 부부 입력값 + 제도 파라미터(고급) 입력 → UserInput / Config 생성
- 본문         : 조합 전수 평가 → 3가지 관점(안정형/총수령액극대화형/상속중시형) 상위 5개 표 + 자동 장단점
                 → 그래프 8종 → CSV/Excel 내보내기

MVP 원칙: 실행 가능한 최소버전. 세부 제도 산식은 각 모듈의 TODO 지점에서 확장한다.
"""

from __future__ import annotations

import streamlit as st

import nps
import pension
import optimizer as opt
import visualization as viz
import export
from cashflow import simulate, build_strategy_from_user
from config import (
    Config, NpsPolicy, TeacherPolicy, HousingPolicy, OptimizerConfig,
    Person, UserInput,
)

st.set_page_config(page_title="부부 노후자금 계획", layout="wide")


# ---------------------------------------------------------------------------
# 사이드바 입력 → UserInput / Config
# ---------------------------------------------------------------------------
def build_inputs():
    """사이드바 위젯을 그려 UserInput 과 Config 를 반환."""
    st.sidebar.header("👫 부부 기본정보")

    # 연금 종류 라벨 <-> 내부 코드 매핑.
    PENSION_TYPES = {"국민연금": "nps", "교직원연금(사학연금)": "teacher"}

    c1, c2 = st.sidebar.columns(2)
    with c1:
        st.caption("남편")
        h_ptype = PENSION_TYPES[st.selectbox("남편 연금종류", list(PENSION_TYPES), key="hpt")]
        h_birth = st.number_input("남편 출생연도", 1940, 2000, 1965, key="hb")
        h_nps = st.number_input("남편 연금 월액(원)", 0, 5_000_000, 1_100_000, 50_000, key="hn")
        h_principal = st.number_input("남편 총 납입원금(원)", 0, 1_000_000_000,
                                      100_000_000, 5_000_000, key="hpp")
        h_life = st.number_input("남편 기대수명", 70, 110, 86, key="hl")
        # 추납/임의가입은 국민연금 전용 → 교직원연금이면 비활성화.
        h_teacher = h_ptype == "teacher"
        h_chunap_y = st.number_input("남편 추납기간(년)", 0, 20, 0, key="hcy", disabled=h_teacher)
        h_chunap_c = st.number_input("남편 추납비용(원)", 0, 200_000_000, 0, 1_000_000,
                                     key="hcc", disabled=h_teacher)
    with c2:
        st.caption("아내")
        w_ptype = PENSION_TYPES[st.selectbox("아내 연금종류", list(PENSION_TYPES),
                                             index=0, key="wpt")]
        w_birth = st.number_input("아내 출생연도", 1940, 2000, 1967, key="wb")
        w_nps = st.number_input("아내 연금 월액(원)", 0, 5_000_000, 700_000, 50_000, key="wn")
        w_principal = st.number_input("아내 총 납입원금(원)", 0, 1_000_000_000,
                                      80_000_000, 5_000_000, key="wpp")
        w_life = st.number_input("아내 기대수명", 70, 110, 90, key="wl")
        w_teacher = w_ptype == "teacher"
        w_chunap_y = st.number_input("아내 추납기간(년)", 0, 20, 0, key="wcy", disabled=w_teacher)
        w_chunap_c = st.number_input("아내 추납비용(원)", 0, 200_000_000, 0, 1_000_000,
                                     key="wcc", disabled=w_teacher)

    st.sidebar.header("💰 생활/자산")
    retire_age = st.sidebar.number_input("은퇴나이(남편 기준)", 50, 75, 60)
    living = st.sidebar.number_input("월 생활비(부부합산, 원)", 0, 20_000_000, 3_000_000, 100_000)
    single_ratio = st.sidebar.slider("단독생존 생활비 비율", 0.4, 1.0, 0.65, 0.05)
    assets = st.sidebar.number_input("금융자산(원)", 0, 5_000_000_000, 200_000_000, 10_000_000)
    invest = st.sidebar.slider("투자수익률(연,%)", 0.0, 10.0, 3.0, 0.5) / 100
    inflation = st.sidebar.slider("물가상승률(연,%)", 0.0, 6.0, 2.0, 0.5) / 100

    st.sidebar.header("🏠 주택연금")
    use_house = st.sidebar.checkbox("주택연금 사용", True)
    house_val = st.sidebar.number_input("주택가격(원)", 0, 5_000_000_000, 500_000_000, 10_000_000)
    house_monthly = st.sidebar.number_input("주택연금 기준월지급액(원)", 0, 10_000_000, 1_200_000, 50_000)

    st.sidebar.header("⚙️ 제도 파라미터(고급)")
    with st.sidebar.expander("국민연금 감액/가산/계수"):
        early = st.number_input("조기수령 월감액률(%)", 0.0, 2.0, 0.5, 0.05) / 100
        defer = st.number_input("연기수령 월가산률(%)", 0.0, 2.0, 0.6, 0.05) / 100
        surv = st.number_input("국민 유족연금 지급률(%)", 0.0, 100.0, 60.0, 5.0) / 100
        house_factor = st.number_input("주택연금 나이계수(1세당,%)", 0.0, 20.0, 6.0, 0.5) / 100
        discount = st.number_input("현재가치 할인율(%)", 0.0, 10.0, 2.0, 0.5) / 100
    with st.sidebar.expander("교직원연금(사학연금) 파라미터"):
        t_early = st.number_input("조기퇴직연금 연감액률(%)", 0.0, 10.0, 5.0, 0.5) / 100
        t_surv = st.number_input("교직원 유족연금 지급률(%)", 0.0, 100.0, 60.0, 5.0) / 100

    # --- 객체 조립 ---
    husband = Person("남편", h_birth, nps_monthly=h_nps, pension_type=h_ptype,
                     paid_principal=h_principal,
                     chunap_years=h_chunap_y, chunap_cost=h_chunap_c)
    wife = Person("아내", w_birth, nps_monthly=w_nps, pension_type=w_ptype,
                  paid_principal=w_principal,
                  chunap_years=w_chunap_y, chunap_cost=w_chunap_c)

    user = UserInput(
        husband=husband, wife=wife,
        living_expense_monthly=living, single_expense_ratio=single_ratio,
        financial_assets=assets, investment_return=invest, inflation_rate=inflation,
        husband_life_expectancy=h_life, wife_life_expectancy=w_life,
        house_value=house_val, housing_monthly_base=house_monthly,
        use_housing_pension=use_house, retirement_age=retire_age,
    )

    cfg = Config(
        nps=NpsPolicy(early_monthly_reduction=early, defer_monthly_increase=defer,
                      survivor_pension_rate=surv),
        teacher=TeacherPolicy(early_yearly_reduction=t_early, survivor_pension_rate=t_surv),
        housing=HousingPolicy(age_factor_per_year=house_factor),
        optimizer=OptimizerConfig(discount_rate=discount),
    )
    return user, cfg


# ---------------------------------------------------------------------------
# 결과 렌더링
# ---------------------------------------------------------------------------
def render_view(df, view: str, title: str):
    """한 관점의 상위 5개 조합 표 + 자동 장단점 설명."""
    st.subheader(title)
    top = opt.top_n(df, view, 5)
    for _, row in top.iterrows():
        housing_txt = f"{int(row['housing'])}세" if row["use_housing"] else "미사용"
        cols = st.columns([1, 3])
        with cols[0]:
            st.metric(f"연금 {int(row['h_claim'])}/{int(row['w_claim'])}세",
                      f"{row[f'score_{view}']:.3f} 점")
        with cols[1]:
            st.write(
                f"주택연금 {housing_txt} · "
                f"총수령(현가) {row['total_pv']/1e8:.2f}억 · "
                f"부족 {row['shortfall_months']:.0f}개월 · "
                f"상속 {row['bequest']/1e8:.2f}억"
            )
            st.caption(opt.explain(row, df))
    return top


def main():
    st.title("👴👵 부부 노후자금 통합 시뮬레이터")
    st.caption("국민연금·교직원연금·주택연금·추납·임의가입·물가·기대수명을 통합해 월 단위 현금흐름을 시뮬레이션합니다.")

    user, cfg = build_inputs()

    if not st.sidebar.button("🚀 시뮬레이션 실행", type="primary"):
        st.info("좌측에서 값을 입력하고 **시뮬레이션 실행**을 눌러주세요.")
        h_normal = pension.normal_start_age(user.husband, cfg)
        w_normal = pension.normal_start_age(user.wife, cfg)
        st.write(
            f"참고: 정상 수령개시연령 — "
            f"남편({pension.type_label(user.husband)}) **{h_normal}세**, "
            f"아내({pension.type_label(user.wife)}) **{w_normal}세**"
        )
        return

    # 1) 조합 전수 평가 + 점수화 --------------------------------------------
    # robust=True: 각 전략을 여러 물가에서 돌려 '최악 물가 부족액'까지 평가(물가 예측 불가 대비).
    with st.spinner("조합을 계산 중입니다(물가 스트레스 포함)..."):
        strategies = opt.generate_strategies(user, cfg)
        df = opt.evaluate_all(user, cfg, strategies, robust=True)
        df = opt.score(df, cfg)
        pareto = opt.pareto_front(df)

    st.success(f"총 {len(df):,}개 조합 평가 완료 "
               f"(물가 {', '.join(f'{x*100:.0f}%' for x in cfg.optimizer.robust_inflations)} 스트레스 반영).")

    # 2) 3가지 관점 상위 5개 -------------------------------------------------
    tabs = st.tabs(["🛡️ 안정형", "📈 총수령액 극대화형", "🎁 상속중시형"])
    tops = {}
    with tabs[0]:
        tops["stable"] = render_view(df, "stable", "생활비 부족을 최소화하는 안정형 상위 5")
    with tabs[1]:
        tops["maximize"] = render_view(df, "maximize", "총수령액을 극대화하는 상위 5")
    with tabs[2]:
        tops["bequest"] = render_view(df, "bequest", "상속(잔여자산)을 중시하는 상위 5")

    # 대표 추천(안정형 1위)을 상세 그래프 대상 시나리오로 사용.
    best_row = tops["stable"].iloc[0]
    best_strat = strategies[int(best_row["id"])]
    best_scenario = simulate(user, best_strat, cfg)

    # 물가 안전 마진: 추천(안정형 1위) 전략이 부족 없이 견디는 최대 물가상승률.
    st.subheader("🌡️ 추천 전략의 물가 안전 마진")
    margin = opt.inflation_safety_margin(user, cfg, best_strat)
    m1, m2, m3 = st.columns(3)
    if margin is None:
        m1.metric("물가 안전 마진", "0% 미만", "현재 가정에서도 부족 발생")
    elif margin >= cfg.optimizer.margin_max_inflation:
        m1.metric("물가 안전 마진", f"{margin*100:.1f}%+ 안전",
                  "매우 견고(테스트 상한까지 부족 없음)")
    else:
        m1.metric("물가 안전 마진", f"~{margin*100:.1f}%까지 안전",
                  f"물가 {margin*100:.1f}% 초과 시 부족 시작")
    m2.metric("현재 가정 물가", f"{user.inflation_rate*100:.1f}%")
    worst_infl_sf = best_row.get("worst_infl_shortfall", float("nan"))
    if worst_infl_sf == worst_infl_sf:  # NaN 체크
        m3.metric("최악 물가 부족액",
                  "없음" if worst_infl_sf <= 0 else f"{worst_infl_sf/1e8:.2f}억",
                  help=f"물가 {', '.join(f'{x*100:.0f}%' for x in cfg.optimizer.robust_inflations)} 중 최악")
    st.caption("물가는 예측이 불가하므로, 이 전략이 **물가가 얼마까지 올라도 부족이 없는지**로 안전성을 봅니다.")

    # 3) 그래프 8종 ----------------------------------------------------------
    st.header("📊 그래프")
    g1, g2 = st.columns(2)
    with g1:
        st.plotly_chart(viz.fig_monthly_cashflow(best_scenario), use_container_width=True)
    with g2:
        st.plotly_chart(viz.fig_cumulative_assets(best_scenario), use_container_width=True)

    # ③ 나이별 누적 수령액·원금확보 시점 — 남편/아내 각각(기대수명까지 그림).
    g3, g3b = st.columns(2)
    with g3:
        h_lbl = f"남편·{pension.type_label(user.husband)}"
        h_curves, h_prin, h_be, h_death, h_reps = opt.cumulative_receipts_curves(user, cfg, "husband")
        st.plotly_chart(
            viz.fig_cumulative_receipts(h_curves, h_prin, h_be, h_death, h_reps, h_lbl),
            use_container_width=True)
    with g3b:
        w_lbl = f"아내·{pension.type_label(user.wife)}"
        w_curves, w_prin, w_be, w_death, w_reps = opt.cumulative_receipts_curves(user, cfg, "wife")
        st.plotly_chart(
            viz.fig_cumulative_receipts(w_curves, w_prin, w_be, w_death, w_reps, w_lbl),
            use_container_width=True)

    g4, g5 = st.columns(2)
    with g4:
        if user.use_housing_pension:
            hdf = opt.shortfall_by_housing_age(user, cfg)
            st.plotly_chart(viz.fig_shortfall_by_housing(hdf), use_container_width=True)
        else:
            st.info("주택연금 미사용 — ④ 그래프 생략")
    with g5:
        st.plotly_chart(viz.fig_heatmap(df, "shortfall_total"), use_container_width=True)

    g6, g7 = st.columns(2)
    with g6:
        idf = opt.shortfall_by_inflation(user, cfg)
        st.plotly_chart(viz.fig_shortfall_by_inflation(idf), use_container_width=True)
    with g7:
        with st.spinner("기대수명별 최적 전략 탐색..."):
            ldf = opt.best_strategy_by_life(user, cfg, "stable")
        st.plotly_chart(viz.fig_best_by_life(ldf), use_container_width=True)

    g8, g9 = st.columns(2)
    with g8:
        st.plotly_chart(
            viz.fig_pareto(df, pareto, best_id=int(best_row["id"])),
            use_container_width=True,
        )
    with g9:
        st.plotly_chart(viz.fig_score_scatter(df, "stable"), use_container_width=True)

    # 4) 내보내기 ------------------------------------------------------------
    st.header("💾 내보내기")
    e1, e2 = st.columns(2)
    with e1:
        st.download_button("CSV 다운로드(전체 조합)", export.to_csv_bytes(df),
                           "nps_result.csv", "text/csv")
    with e2:
        st.download_button(
            "Excel 다운로드(요약+월별표)",
            export.to_excel_bytes(df, best_scenario),
            "nps_result.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


if __name__ == "__main__":
    main()
