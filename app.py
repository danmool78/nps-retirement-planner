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

import gc

import streamlit as st

import nps
import pension
import optimizer as opt
import visualization as viz
import export
from cashflow import simulate, build_strategy_from_user
from config import (
    Config, NpsPolicy, TeacherPolicy, GovPolicy, HousingPolicy, OptimizerConfig,
    Person, UserInput,
)

st.set_page_config(page_title="부부 노후자금 계획", layout="wide")


# ---------------------------------------------------------------------------
# 그래프별 '읽는 법' 설명서
# ---------------------------------------------------------------------------
GRAPH_GUIDES = {
    "cashflow": """
**① 연령별 월 현금흐름** — 추천 전략에서 나이에 따라 매월 들어오고 나가는 돈.
- 파란선=연금 등 **수입**, 빨간선=**생활비 지출**, 초록점선=**순현금흐름(수입-지출)**.
- 초록선이 **0 아래로 내려가면** 그 시기에 매달 적자 → 금융자산에서 메꿔야 함.
- 수입선이 계단식으로 오르는 구간 = 연금이 새로 개시되는 시점.
""",
    "assets": """
**② 연령별 누적자산** — 금융자산 잔액이 나이에 따라 어떻게 변하는지.
- 선이 **우상향**이면 자산이 불어나는 중, **우하향**이면 헐어 쓰는 중.
- 선이 **0에 닿는 나이 = 자산 고갈 시점**. 이후에는 생활비 부족이 발생.
- 사망 시점에 남는 높이 = 상속 가능한 잔여 금융자산.
""",
    "receipts": """
**③ 나이별 누적 수령액·원금확보 시점** — 연금을 언제부터 받느냐에 따른 누적 수령액.
- 색선 = 개시나이별(조기/정상/연기) 누적 수령액. 위로 갈수록 많이 받은 것.
- **범례에 개시나이별 '월 수령액'**(월에 얼마 받는지)이 함께 표시됩니다.
- 빨간 점선 = **납입원금**. 색선이 이 선을 넘는 점(●)이 **원금확보(손익분기)**.
- 회색 점선 = **기대수명**. 원금확보 지점부터 기대수명까지가 **이득 구간**.
- 원금확보가 **일찍(중간쯤 이전)** 올수록 이득 기간이 길어 유리.
""",
    "housing": """
**④ 주택연금 개시시점별 부족액** — 주택연금을 몇 세에 시작하느냐에 따른 생활비 부족액총합.
- **낮을수록 좋음**(부족이 적음). 보통 늦게 개시할수록 월지급액이 커져 부족이 줄어듦.
- 단, 너무 늦추면 그 전까지 부족을 자산으로 버텨야 하니 곡선의 **최저점 부근**이 균형점.
""",
    "heatmap": """
**⑤ 국민연금×주택연금 히트맵** — 두 개시나이 조합별 부족액을 색으로.
- 세로=국민연금 수령나이, 가로=주택연금 개시나이. **초록=부족 적음(좋음), 빨강=부족 많음**.
- 초록이 몰린 영역이 안전한 조합대. 칸의 숫자는 부족액(만원).
""",
    "inflation": """
**⑥ 물가상승률별 부족액** — 물가가 1%·2%·3%일 때 각각의 생활비 부족액.
- 물가는 예측 불가하므로 "물가가 오르면 부족이 얼마나 커지나"의 **민감도**를 봄.
- 막대가 급격히 커지면 그 전략은 **고물가에 취약**. 완만하면 물가에 견고.
""",
    "life": """
**⑦ 기대수명별 유리한 전략** — 기대수명(83·88·93세)마다 최적 전략의 총수령액·상속.
- 오래 살 것으로 볼수록 **연기수령**이 유리해지는 경향(막대 위 채택 나이 참고).
- 자신의 건강·가족력에 맞는 기대수명 시나리오의 막대를 보면 됨.
""",
    "pareto": """
**⑧ Pareto Frontier** — 총수령액(→클수록 좋음)과 부족액(↑작을수록 좋음)의 트레이드오프.
- **빨간 선 위의 점들만이 후보**(다른 조합에 지배당하지 않는 최선의 집합).
- 회색 점은 무시. ⭐노란 별 = 추천 균형점.
- 선을 따라 **오른쪽으로 갈수록 많이 받지만 부족 위험↑**, **왼쪽 아래일수록 안전**.
""",
    "scatter": """
**⑨ 조합별 점수 산점도** — 점 하나 = 하나의 전략 조합.
- 가로(→) = 평생 총수령액, 세로(↑) = 상속(잔여자산). 오른쪽 위일수록 많이 받고 많이 남김.
- 점 색 = 선택한 관점의 종합점수(밝을수록 좋음).
- **⭐별표 = 그 관점의 추천 조합**. 별표 옆 라벨에 **수령개시 조건(국민연금·주택연금 나이)**이 표시됩니다.
- 점에 마우스를 올리면 그 조합의 국민연금·주택연금 개시나이가 나옵니다.
- 위 색 기준 드롭다운으로 안정형/총수령액/상속 관점을 바꿔볼 수 있습니다.
""",
    "views": """
**3가지 관점 상위 5개 표 읽는 법** — 성향에 따라 최적 전략이 달라지므로 관점별로 나눠 보여줍니다.
- 🛡️ **안정형**: 생활비 부족을 최소화(+물가에 견고)하는 것을 최우선. 안전 지향.
- 📈 **총수령액 극대화형**: 평생 받는 총액(현재가치)을 최대화. 많이 받는 것 우선.
- 🎁 **상속중시형**: 사망 시 남기는 잔여자산을 최대화. 물려주는 것 우선.

각 줄의 의미
- **연금 63/64세** = 남편/아내의 연금 수령개시나이, 옆의 **점수**는 해당 관점 종합점수(높을수록 좋음).
- **주택연금 개시·총수령(현가)·부족 개월·상속** = 그 전략의 핵심 결과 요약.
- **👍/👎** = 다른 조합 대비 자동으로 뽑은 장단점.
- 맨 위(1위)가 그 관점의 추천안이며, 아래 그래프는 **안정형 1위**를 기준으로 그려집니다.
""",
    "margin": """
**물가 안전 마진 읽는 법** — 물가는 예측이 불가하므로, 추천 전략이 "물가가 얼마까지 올라도
생활비 부족이 없는지"로 안전성을 봅니다.
- **~X%까지 안전** = 물가가 X%를 넘어서면 부족이 시작됨. 숫자가 클수록 견고한 전략.
- **0% 미만** = 현재 가정에서도 이미 부족 발생(재검토 필요).
- **최악 물가 부족액** = 스트레스 물가(1~5%) 중 가장 나쁜 경우의 부족액. '없음'이면 매우 안전.
""",
}


def guide(key: str):
    """그래프 아래에 접이식 '읽는 법' 설명을 렌더링."""
    with st.expander("📖 이 그래프 읽는 법"):
        st.markdown(GRAPH_GUIDES[key])


# ---------------------------------------------------------------------------
# 무거운 계산은 캐싱하여 위젯 조작 시 재계산을 방지(메모리·속도 절약)
# UserInput/Config 는 dataclass 이므로 repr 로 해시 키를 만든다.
# ---------------------------------------------------------------------------
# max_entries=1: 직전 결과 1개만 캐시에 유지(메모리 누적 방지).
# ttl=3600: 1시간 지나면 캐시 자동 만료로 메모리 회수.
@st.cache_data(hash_funcs={UserInput: repr, Config: repr},
               show_spinner=False, max_entries=1, ttl=3600)
def compute_pipeline(user: UserInput, cfg: Config) -> dict:
    """전 조합 평가·점수·파레토·민감도·추천 시나리오를 한 번에 계산하고 캐싱한다."""
    strategies = opt.generate_strategies(user, cfg)
    df = opt.score(opt.evaluate_all(user, cfg, strategies, robust=True), cfg)
    pareto = opt.pareto_front(df)

    tops = {v: opt.top_n(df, v, 5) for v in ("stable", "maximize", "bequest")}
    best_id = int(tops["stable"].iloc[0]["id"])
    best_strat = strategies[best_id]

    return {
        "n": len(df),
        "df": df,
        "pareto": pareto,
        "tops": tops,
        "best_id": best_id,
        "best_scenario": simulate(user, best_strat, cfg, record=True),
        "margin": opt.inflation_safety_margin(user, cfg, best_strat),
        "life_df": opt.best_strategy_by_life(user, cfg, "stable"),
        "housing_df": opt.shortfall_by_housing_age(user, cfg) if user.use_housing_pension else None,
        "inflation_df": opt.shortfall_by_inflation(user, cfg),
        "husband_curves": opt.cumulative_receipts_curves(user, cfg, "husband"),
        "wife_curves": opt.cumulative_receipts_curves(user, cfg, "wife"),
    }


# ---------------------------------------------------------------------------
# 사이드바 입력 → UserInput / Config
# ---------------------------------------------------------------------------
def build_inputs():
    """사이드바 위젯을 그려 UserInput 과 Config 를 반환."""
    st.sidebar.header("👫 부부 기본정보")

    # 연금 종류 라벨 <-> 내부 코드 매핑.
    PENSION_TYPES = {
        "국민연금": "nps",
        "교직원연금(사학연금)": "teacher",
        "공무원연금": "gov",
    }

    c1, c2 = st.sidebar.columns(2)
    with c1:
        st.caption("남편")
        h_ptype = PENSION_TYPES[st.selectbox("남편 연금종류", list(PENSION_TYPES), key="hpt")]
        h_birth = st.number_input("남편 출생연도", 1940, 2000, 1965, key="hb")
        h_nps = st.number_input("남편 연금 월액(원)", 0, 5_000_000, 1_100_000, 50_000, key="hn")
        h_principal = st.number_input("남편 총 납입원금(원)", 0, 1_000_000_000,
                                      100_000_000, 5_000_000, key="hpp")
        h_life = st.number_input("남편 기대수명", 70, 110, 86, key="hl")
        # 추납/임의가입은 국민연금 전용 → 직역연금(교직원·공무원)이면 비활성화.
        h_dbtype = h_ptype != "nps"
        h_chunap_y = st.number_input("남편 추납기간(년)", 0, 20, 0, key="hcy", disabled=h_dbtype)
        h_chunap_c = st.number_input("남편 추납비용(원)", 0, 200_000_000, 0, 1_000_000,
                                     key="hcc", disabled=h_dbtype)
    with c2:
        st.caption("아내")
        w_ptype = PENSION_TYPES[st.selectbox("아내 연금종류", list(PENSION_TYPES),
                                             index=0, key="wpt")]
        w_birth = st.number_input("아내 출생연도", 1940, 2000, 1967, key="wb")
        w_nps = st.number_input("아내 연금 월액(원)", 0, 5_000_000, 700_000, 50_000, key="wn")
        w_principal = st.number_input("아내 총 납입원금(원)", 0, 1_000_000_000,
                                      80_000_000, 5_000_000, key="wpp")
        w_life = st.number_input("아내 기대수명", 70, 110, 90, key="wl")
        w_dbtype = w_ptype != "nps"
        w_chunap_y = st.number_input("아내 추납기간(년)", 0, 20, 0, key="wcy", disabled=w_dbtype)
        w_chunap_c = st.number_input("아내 추납비용(원)", 0, 200_000_000, 0, 1_000_000,
                                     key="wcc", disabled=w_dbtype)

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
        t_early = st.number_input("조기퇴직연금 연감액률(%)", 0.0, 10.0, 5.0, 0.5,
                                  key="te") / 100
        t_surv = st.number_input("교직원 유족연금 지급률(%)", 0.0, 100.0, 60.0, 5.0,
                                 key="ts") / 100
    with st.sidebar.expander("공무원연금 파라미터"):
        g_early = st.number_input("조기퇴직연금 연감액률(%)", 0.0, 10.0, 5.0, 0.5,
                                  key="ge") / 100
        g_surv = st.number_input("공무원 유족연금 지급률(%)", 0.0, 100.0, 60.0, 5.0,
                                 key="gs") / 100

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
        gov=GovPolicy(early_yearly_reduction=g_early, survivor_pension_rate=g_surv),
        housing=HousingPolicy(age_factor_per_year=house_factor),
        optimizer=OptimizerConfig(discount_rate=discount),
    )
    return user, cfg


# ---------------------------------------------------------------------------
# 결과 렌더링
# ---------------------------------------------------------------------------
def render_view_table(top, view: str, df, title: str):
    """미리 계산된 상위 5개 조합 표 + 자동 장단점 설명을 렌더링."""
    st.subheader(title)
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


def main():
    st.title("👴👵 부부 노후자금 통합 시뮬레이터")
    st.caption("국민연금·교직원연금·공무원연금·주택연금·추납·임의가입·물가·기대수명을 통합해 월 단위 현금흐름을 시뮬레이션합니다.")

    user, cfg = build_inputs()

    # 실행 버튼을 누른 적이 있으면 세션에 기록 → 이후 위젯 조작에도 결과가 유지되도록 함.
    if st.sidebar.button("🚀 시뮬레이션 실행", type="primary"):
        st.session_state["ran"] = True

    # 메모리 수동 정리: 캐시 비우기 + 가비지 컬렉션(리소스 한도 방지용).
    if st.sidebar.button("🧹 캐시/메모리 비우기"):
        st.cache_data.clear()
        st.session_state.pop("ran", None)
        gc.collect()
        st.sidebar.success("캐시와 메모리를 비웠습니다.")
        st.stop()

    if not st.session_state.get("ran"):
        st.info("좌측에서 값을 입력하고 **시뮬레이션 실행**을 눌러주세요.")
        h_normal = pension.normal_start_age(user.husband, cfg)
        w_normal = pension.normal_start_age(user.wife, cfg)
        st.write(
            f"참고: 정상 수령개시연령 — "
            f"남편({pension.type_label(user.husband)}) **{h_normal}세**, "
            f"아내({pension.type_label(user.wife)}) **{w_normal}세**"
        )
        return

    # 1) 무거운 계산은 캐싱된 파이프라인으로(입력이 같으면 위젯 조작 시 재계산 안 함).
    with st.spinner("조합을 계산 중입니다(물가 스트레스 포함)..."):
        R = compute_pipeline(user, cfg)
    gc.collect()  # 계산 과정의 임시 객체를 즉시 회수하여 peak 메모리를 낮춤.
    df, pareto, tops = R["df"], R["pareto"], R["tops"]
    best_row = tops["stable"].iloc[0]
    best_scenario = R["best_scenario"]

    st.success(f"총 {R['n']:,}개 조합 평가 완료 "
               f"(물가 {', '.join(f'{x*100:.0f}%' for x in cfg.optimizer.robust_inflations)} 스트레스 반영).")

    # 2) 3가지 관점 상위 5개 -------------------------------------------------
    st.header("🏆 성향별 추천 전략 (상위 5)")
    guide("views")
    tabs = st.tabs(["🛡️ 안정형", "📈 총수령액 극대화형", "🎁 상속중시형"])
    with tabs[0]:
        render_view_table(tops["stable"], "stable", df, "생활비 부족을 최소화하는 안정형 상위 5")
    with tabs[1]:
        render_view_table(tops["maximize"], "maximize", df, "총수령액을 극대화하는 상위 5")
    with tabs[2]:
        render_view_table(tops["bequest"], "bequest", df, "상속(잔여자산)을 중시하는 상위 5")

    # 물가 안전 마진: 추천(안정형 1위) 전략이 부족 없이 견디는 최대 물가상승률.
    st.subheader("🌡️ 추천 전략의 물가 안전 마진")
    margin = R["margin"]
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
    guide("margin")

    # 3) 그래프 ---------------------------------------------------------------
    # 각 그래프를 변수로 만들어 화면 표시 + 리포트(report_figs) 수집에 함께 사용.
    st.header("📊 그래프")
    report_figs = []  # [(제목, fig)] — HTML 리포트에 담을 그래프 모음

    fig_cf = viz.fig_monthly_cashflow(best_scenario)
    fig_as = viz.fig_cumulative_assets(best_scenario)
    g1, g2 = st.columns(2)
    with g1:
        st.plotly_chart(fig_cf, use_container_width=True); guide("cashflow")
    with g2:
        st.plotly_chart(fig_as, use_container_width=True); guide("assets")
    report_figs += [("① 연령별 월 현금흐름", fig_cf), ("② 연령별 누적자산", fig_as)]

    # ③ 나이별 누적 수령액·원금확보 시점 — 남편/아내 각각.
    h_lbl = f"남편·{pension.type_label(user.husband)}"
    w_lbl = f"아내·{pension.type_label(user.wife)}"
    fig_h = viz.fig_cumulative_receipts(*R["husband_curves"], h_lbl)
    fig_w = viz.fig_cumulative_receipts(*R["wife_curves"], w_lbl)
    g3, g3b = st.columns(2)
    with g3:
        st.plotly_chart(fig_h, use_container_width=True); guide("receipts")
    with g3b:
        st.plotly_chart(fig_w, use_container_width=True); guide("receipts")
    report_figs += [(f"③ 누적 수령액·원금확보 ({h_lbl})", fig_h),
                    (f"③ 누적 수령액·원금확보 ({w_lbl})", fig_w)]

    fig_hz = viz.fig_heatmap(df, "shortfall_total")
    g4, g5 = st.columns(2)
    with g4:
        if R["housing_df"] is not None:
            fig_ho = viz.fig_shortfall_by_housing(R["housing_df"])
            st.plotly_chart(fig_ho, use_container_width=True); guide("housing")
            report_figs.append(("④ 주택연금 개시별 부족액", fig_ho))
        else:
            st.info("주택연금 미사용 — ④ 그래프 생략")
    with g5:
        st.plotly_chart(fig_hz, use_container_width=True); guide("heatmap")
    report_figs.append(("⑤ 국민×주택 히트맵", fig_hz))

    fig_in = viz.fig_shortfall_by_inflation(R["inflation_df"])
    fig_li = viz.fig_best_by_life(R["life_df"])
    g6, g7 = st.columns(2)
    with g6:
        st.plotly_chart(fig_in, use_container_width=True); guide("inflation")
    with g7:
        st.plotly_chart(fig_li, use_container_width=True); guide("life")
    report_figs += [("⑥ 물가상승률별 부족액", fig_in), ("⑦ 기대수명별 전략", fig_li)]

    fig_pa = viz.fig_pareto(df, pareto, best_id=R["best_id"])
    g8, g9 = st.columns(2)
    with g8:
        st.plotly_chart(fig_pa, use_container_width=True); guide("pareto")
    with g9:
        SCATTER_VIEWS = {"안정형": "stable", "총수령액 극대화형": "maximize", "상속중시형": "bequest"}
        sview = SCATTER_VIEWS[st.selectbox("산점도 색 기준(관점)", list(SCATTER_VIEWS),
                                           key="scatterview")]
        sview_best = int(tops[sview].iloc[0]["id"])
        fig_sc = viz.fig_score_scatter(df, sview, best_id=sview_best)
        try:
            st.plotly_chart(fig_sc, use_container_width=True)
        except Exception as e:  # 산점도 렌더 실패가 전체 앱을 멈추지 않도록.
            st.warning(f"산점도를 그리는 중 문제가 발생해 건너뜁니다: {e}")
        guide("scatter")
    report_figs += [("⑧ Pareto Frontier", fig_pa), ("⑨ 조합별 점수 산점도", fig_sc)]

    # 4) 내보내기 ------------------------------------------------------------
    st.header("💾 내보내기 / 리포트")

    # --- 전체 리포트(입력요약·표·그래프 전부)를 담은 HTML → 브라우저에서 PDF 저장 ---
    if margin is None:
        margin_text = "현재 가정에서도 생활비 부족 발생 (0% 미만) — 전략 재검토 필요"
    elif margin >= cfg.optimizer.margin_max_inflation:
        margin_text = f"물가 {margin*100:.1f}%+ 까지도 부족 없이 매우 견고"
    else:
        margin_text = (f"물가 ~{margin*100:.1f}% 까지 부족 없이 안전 "
                       f"(현재 가정 물가 {user.inflation_rate*100:.1f}%)")

    summary = {
        "n_combos": R["n"],
        "normal_ages": (f"정상개시 남편({pension.type_label(user.husband)}) "
                        f"{pension.normal_start_age(user.husband, cfg)}세 / "
                        f"아내({pension.type_label(user.wife)}) "
                        f"{pension.normal_start_age(user.wife, cfg)}세"),
        "margin": margin_text,
        "inputs": [
            ("남편", f"{pension.type_label(user.husband)} · {user.husband.birth_year}년생 · "
                     f"월 {user.husband.nps_monthly:,.0f}원 · 납입원금 {user.husband.paid_principal:,.0f}원 · "
                     f"기대수명 {user.husband_life_expectancy}세"),
            ("아내", f"{pension.type_label(user.wife)} · {user.wife.birth_year}년생 · "
                     f"월 {user.wife.nps_monthly:,.0f}원 · 납입원금 {user.wife.paid_principal:,.0f}원 · "
                     f"기대수명 {user.wife_life_expectancy}세"),
            ("은퇴나이 / 월 생활비", f"{user.retirement_age}세 / {user.living_expense_monthly:,.0f}원"),
            ("금융자산 / 투자수익률", f"{user.financial_assets:,.0f}원 / {user.investment_return*100:.1f}%"),
            ("물가상승률", f"{user.inflation_rate*100:.1f}%"),
            ("주택", (f"{user.house_value:,.0f}원 · 주택연금 월 {user.housing_monthly_base:,.0f}원"
                      if user.use_housing_pension else "주택연금 미사용")),
        ],
    }
    report_bytes = export.build_html_report(report_figs, tops, summary)
    st.download_button(
        "📄 전체 리포트 다운로드 (그래프·표 포함)",
        report_bytes, "노후자금리포트.html", "text/html", type="primary",
    )
    st.caption("내려받은 파일을 열고 **Ctrl+P → '대상: PDF로 저장'** 하면 한글·그래프 그대로 PDF가 됩니다.")

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
