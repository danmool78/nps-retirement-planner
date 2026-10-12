"""
app.py
======
부부 노후자금 계획 시뮬레이터 — Streamlit 진입점.

실행
- 브라우저(서버 불필요): index.html 을 정적 호스팅(GitHub Pages 등)하면 stlite(Pyodide)가
  이 앱을 사용자 브라우저 안에서 그대로 실행한다. 계산은 전부 사용자 기기에서 이뤄진다.
- 로컬 개발:  streamlit run app.py

구성
- 좌측 사이드바 : 부부 정보(남편/아내 탭) · 생활·자산 · 주택연금 · 제도 파라미터
                  → UserInput / Config 생성. 제도 기본값은 policy.json(시행일별)에서 자동 선택.
- 본문         : [시뮬레이션 실행] 시점의 입력을 스냅샷으로 고정 → 조합 전수 평가
                  → 핵심 요약 카드 → 탭(추천 전략 · 월수입·안전성 · 현금흐름 · 연금 수령 · 전략 비교 · 내보내기)
"""

from __future__ import annotations

import html as _html

import streamlit as st

import pension
import policy
import housing_pension as hp
import optimizer as opt
import montecarlo as mc
import visualization as viz
import export
import ui
from cashflow import simulate
from config import (
    Config, NpsPolicy, TeacherPolicy, GovPolicy, HousingPolicy,
    TaxPolicy, BasicPensionPolicy, OptimizerConfig,
    Person, UserInput,
)

st.set_page_config(page_title="부부 노후자금 계획", layout="wide")


# ---------------------------------------------------------------------------
# 그래프별 '읽는 법' 설명서
# ---------------------------------------------------------------------------
GRAPH_GUIDES = {
    "cashflow": """
**① 연령별 월 현금흐름** — 추천 전략에서 나이에 따라 매월 들어오고 나가는 돈.
- 파란선=**수입(실수령)**, 빨간선=**생활비 지출**, 초록점선=**순현금흐름(수입-지출)**.
- 수입은 **세금·건강보험료를 뺀 실수령**이며, 65세부터 **기초연금**이 더해집니다.
- 초록선이 **0 아래로 내려가면** 그 시기에 매달 적자 → 금융자산에서 메꿔야 함.
- 수입선이 계단식으로 오르는 구간 = 연금이 새로 개시되는 시점.
- **세로 점선 = 사망 시점**(남편/아내). 회색 음영 = **홀로 생존 구간**으로,
  이때 생활비가 줄고(단독생활) 유족연금 조정이 일어나 그래프가 급변합니다.
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
- **주의:** 이 그래프는 **순수 국민연금(내가 낸 보험료)의 손익분기**만 봅니다. 내가 보험료를 안 낸
  **기초연금·주택연금**과 **세금**은 제외됩니다(넣으면 원금회수가 왜곡됨). 그것들을 포함한
  실제 실수령은 **①현금흐름·월수입 구성표**에서 확인하세요.
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
- 회색 점은 무시. 주황 별 = 추천 균형점.
- 선을 따라 **오른쪽으로 갈수록 많이 받지만 부족 위험↑**, **왼쪽 아래일수록 안전**.
""",
    "scatter": """
**⑨ 조합별 점수 산점도** — 점 하나 = 하나의 전략 조합.
- 가로(→) = 평생 총수령액, 세로(↑) = 상속(잔여자산). 오른쪽 위일수록 많이 받고 많이 남김.
- 점 색 = 선택한 관점의 종합점수(밝을수록 좋음).
- **주황 별 = 그 관점의 추천 조합**. 별표 옆 라벨에 **수령개시 조건(국민연금·주택연금 나이)**이 표시됩니다.
- 점에 마우스를 올리면 그 조합의 국민연금·주택연금 개시나이가 나옵니다.
- 위 색 기준 드롭다운으로 안정형/총수령액/상속 관점을 바꿔볼 수 있습니다.
""",
    "views": """
**3가지 관점 상위 5개 표 읽는 법** — 성향에 따라 최적 전략이 달라지므로 관점별로 나눠 보여줍니다.
- **안정형**: 생활비 부족을 최소화(+물가에 견고)하는 것을 최우선. 안전 지향.
- **총수령액 극대화형**: 평생 받는 총액(현재가치)을 최대화. 많이 받는 것 우선.
- **상속중시형**: 사망 시 남기는 잔여자산을 최대화. 물려주는 것 우선.

각 줄의 의미
- **연금 63/64세** = 남편/아내의 연금 수령개시나이, 옆의 **점수**는 해당 관점 종합점수(높을수록 좋음).
- **주택연금 개시·총수령(현가)·부족 개월·상속** = 그 전략의 핵심 결과 요약.
- **초록/빨강 태그** = 다른 조합 대비 자동으로 뽑은 장점/단점.
- 맨 위(1위)가 그 관점의 추천안이며, 아래 그래프는 **안정형 1위**를 기준으로 그려집니다.
""",
    "breakdown": """
**월수입 구성표 읽는 법** — 추천 전략에서 나이별로 매달 실제 손에 쥐는 돈의 구성.
- **공적연금(세전)** = 국민·교직원·공무원+유족연금 합(세금 떼기 전).
- **− 세금·건보** = 연금소득세+건강보험료로 빠지는 금액.
- **실수령 연금** = 세전에서 세금·건보를 뺀 실제 받는 연금.
- **+ 기초연금** = 65세부터 추가(부부 동시 수급 시 각 감액).
- **+ 주택연금** = 주택연금 월지급액(비과세).
- **= 월 실수령 합계** = 그 나이에 매달 실제 들어오는 총액. 생활비와 비교하면 됩니다.
""",
    "montecarlo": """
**투자 변동성 스트레스(몬테카를로)** — 수익률을 매년 무작위로 흔들어 수백 번 시뮬레이션.
- **성공확률** = 부족 없이 끝까지 버틴 경로 비율. 높을수록 안전(보통 80%+ 목표).
- **팬차트**: 파란 밴드 = 하위10%~상위10% 자산 범위, 진한 선 = 중앙값(p50).
- **하위10%(p10) 선이 0에 닿으면** 운 나쁜 경우(초반 폭락 등) 그 나이에 자산 고갈.
- 밴드가 넓을수록 변동성 위험이 큽니다. 변동성(%)을 올려보면 위험이 커지는 걸 확인할 수 있어요.
""",
    "margin": """
**물가 안전 마진 읽는 법** — 물가는 예측이 불가하므로, 추천 전략이 "물가가 얼마까지 올라도
생활비 부족이 없는지"로 안전성을 봅니다.
- **~X%까지 안전** = 물가가 X%를 넘어서면 부족이 시작됨. 숫자가 클수록 견고한 전략.
- **0% 미만** = 현재 가정에서도 이미 부족 발생(재검토 필요).
- **최악 물가 부족액** = 스트레스 물가(1~5%) 중 가장 나쁜 경우의 부족액. '없음'이면 매우 안전.
""",
}



def guide(key: str, target=st):
    """그래프 아래에 접이식 '읽는 법' 설명을 렌더링."""
    with target.expander("이 그래프 읽는 법"):
        st.markdown(GRAPH_GUIDES[key])


def chart(fig, guide_key: str | None = None, target=st):
    """그래프 + (선택) 읽는 법을 한 묶음으로 렌더링."""
    with target.container():
        ui.chart(fig)
        if guide_key:
            guide(guide_key)


# ---------------------------------------------------------------------------
# 무거운 계산은 캐싱(같은 입력이면 재계산하지 않음). 모든 계산은 브라우저(Pyodide) 안에서 실행된다.
# UserInput/Config 는 dataclass 이므로 repr 로 해시 키를 만든다.
# ---------------------------------------------------------------------------
@st.cache_data(hash_funcs={UserInput: repr, Config: repr}, show_spinner=False, max_entries=2)
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
        "montecarlo": mc.run(user, best_strat, cfg, user.investment_volatility,
                             n_sims=cfg.optimizer.mc_sims),
        "life_df": opt.best_strategy_by_life(user, cfg, "stable"),
        "housing_df": opt.shortfall_by_housing_age(user, cfg) if user.use_housing_pension else None,
        "inflation_df": opt.shortfall_by_inflation(user, cfg),
        "husband_curves": opt.cumulative_receipts_curves(user, cfg, "husband"),
        "wife_curves": opt.cumulative_receipts_curves(user, cfg, "wife"),
    }


# ---------------------------------------------------------------------------
# 사이드바 입력 → UserInput / Config
# ---------------------------------------------------------------------------
PENSION_TYPES = {
    "국민연금": "nps",
    "교직원연금(사학연금)": "teacher",
    "공무원연금": "gov",
}
# 국민연금 월액 → 월소득 역산 근사(소득대체율 약 33% 가정 → 소득 ≈ 연금월액 × 3).
NPS_TO_INCOME_MULT = 3.0


def person_inputs(key: str, defaults: dict, P: dict):
    """남편/아내 한 사람의 입력 위젯. 반환: (Person 생성 인자 dict, 기대수명)."""
    income_cap = P.get("nps_income_cap", 6_170_000)
    premium_rate = P.get("nps_premium_rate", 0.09)

    ptype = PENSION_TYPES[st.selectbox("연금 종류", list(PENSION_TYPES), key=f"{key}pt")]
    c1, c2 = st.columns(2)
    birth = c1.number_input("출생연도", 1940, 2000, defaults["birth"], key=f"{key}b")
    life = c2.number_input("기대수명(세)", 70, 110, defaults["life"], key=f"{key}l")
    monthly = st.number_input("정상개시 기준 연금 월액(원)", 0, 5_000_000, defaults["monthly"], 50_000,
                              key=f"{key}n", help="연금공단 예상연금 조회의 '정상 수령나이 기준 월액'")
    principal = st.number_input("지금까지 낸 보험료 총액(만원)", 0, 100_000, defaults["principal"], 100,
                                key=f"{key}pp", help="원금확보(손익분기) 시점 계산에 사용") * 10_000

    # 추납은 국민연금 전용 → 직역연금(교직원·공무원)이면 비활성화.
    db_type = ptype != "nps"
    c3, c4 = st.columns(2)
    chunap_y = c3.number_input("추납 기간(년)", 0, 20, 0, key=f"{key}cy", disabled=db_type,
                               help="추납으로 메우는 가입연수(연금 증가를 결정). 국민연금만 해당")
    income = c4.number_input("월 소득(만원)", 0, 1_000,
                             int(min(monthly * NPS_TO_INCOME_MULT, income_cap) / 10_000), 10,
                             key=f"{key}inc", disabled=db_type,
                             help=f"연금 월액에서 역산한 기본값. 월보험료 = 소득(상한 {income_cap/1e4:,.0f}만) × "
                                  f"보험료율 {premium_rate*100:g}%") * 10_000
    if db_type:  # 비활성 위젯도 이전 값을 유지하므로 직역연금이면 추납을 확실히 0으로.
        chunap_y = 0
    premium = min(income, income_cap) * premium_rate   # 월 연금보험료
    chunap_cost = chunap_y * 12 * premium               # 추납 총비용 자동 계산
    if chunap_y > 0 and not db_type:
        st.caption(f"월보험료 약 {premium/1e4:,.1f}만원 × {chunap_y*12}개월 = 추납비용 약 {chunap_cost/1e4:,.0f}만원")

    return dict(birth_year=birth, nps_monthly=monthly, pension_type=ptype, paid_principal=principal,
                chunap_years=chunap_y, chunap_cost=chunap_cost), life


def build_inputs(P: dict):
    """사이드바 위젯을 그려 UserInput 과 Config 를 반환. P = 오늘 시행 중인 제도값."""
    sb = st.sidebar

    # --- 부부 정보 -------------------------------------------------------------
    ui.side_header("couple", "부부 정보")
    t_h, t_w = sb.tabs(["남편", "아내"])
    with t_h:
        h_args, h_life = person_inputs("h", dict(birth=1965, life=86, monthly=1_100_000, principal=10_000), P)
    with t_w:
        w_args, w_life = person_inputs("w", dict(birth=1967, life=90, monthly=700_000, principal=8_000), P)

    # --- 생활·자산 -------------------------------------------------------------
    sb.divider()
    ui.side_header("wallet", "생활·자산")
    c1, c2 = sb.columns(2)
    retire_age = c1.number_input("은퇴나이(남편)", 50, 75, 60)
    living = c2.number_input("월 생활비(만원)", 0, 2_000, 300, 10, help="부부 합산, 현재가치") * 10_000
    assets = c1.number_input("금융자산(억원)", 0.0, 500.0, 2.0, 0.1) * 100_000_000
    invest = c2.number_input("투자수익률(%)", 0.0, 10.0, 3.0, 0.5) / 100
    inflation = c1.number_input("물가상승률(%)", 0.0, 6.0, 2.0, 0.5) / 100
    volatility = c2.number_input("투자 변동성(%)", 0.0, 40.0, 10.0, 1.0,
                                 help="수익률의 연 표준편차. 클수록 폭락 위험이 큼(몬테카를로에 사용)") / 100

    with sb.expander("기타 소득·재산"):
        other_income = st.number_input("기타 월소득(만원)", 0, 2_000, 0, 10,
                                       help="연금 외 근로·임대·이자·개인/퇴직연금 등. 현금흐름과 기초연금 판정에 반영") * 10_000
        other_income_end = st.number_input("기타소득 유지나이", 55, 110, 100,
                                           help="근로소득처럼 끝나면 낮게, 임대·연금이면 높게(평생=100)")
        other_property = st.number_input("기타 재산(억원)", 0.0, 500.0, 0.0, 0.1,
                                         help="주택·금융자산 외 다른 부동산·자동차 등. 기초연금 판정·상속에 반영") * 100_000_000
        single_ratio = st.number_input("홀로 생존 시 생활비 비율", 0.4, 1.0, 0.65, 0.05,
                                       help="1인 가구 생활비 / 부부 생활비")

    with sb.expander("유족연금·기초연금 처리"):
        SURV_MODES = {
            "자동(유리한 쪽 선택)": "auto",
            "본인연금 + 유족 일부": "own_plus",
            "유족연금 전액(본인 포기)": "survivor_full",
        }
        survivor_mode = SURV_MODES[st.selectbox(
            "배우자 사망 시 유족연금", list(SURV_MODES),
            help="본인 노령연금+유족연금 일부 vs 유족연금 전액 중 무엇을 받을지. 자동은 유리한 쪽을 택합니다.")]
        BASIC_MODES = {
            "자동 판정(소득인정액 기준)": "auto",
            "무조건 수급": "on",
            "무조건 미수급": "off",
        }
        basic_mode = BASIC_MODES[st.selectbox(
            "기초연금", list(BASIC_MODES),
            help="자동 판정: 입력한 연금·주택·자산으로 소득인정액을 계산해 대상이면 반영, 아니면 제외합니다.")]

    # --- 주택연금 --------------------------------------------------------------
    sb.divider()
    ui.side_header("home", "주택연금")
    use_house = sb.toggle("주택연금 사용", True)
    house_val = sb.number_input("주택가격(억원)", 0.0, 500.0, 5.0, 0.1) * 100_000_000
    auto_house = sb.toggle("주택가격으로 월지급액 자동 산정", True,
                           help="HF 종신·정액형 표 기준. 가입 상한(공시가격 기준) 자동 적용.")
    house_cap = P.get("housing_price_cap", 1_200_000_000)
    hp_kwargs = dict(house_price_cap=house_cap)
    if "housing_monthly_per_100m" in P:
        hp_kwargs["monthly_per_100m"] = [tuple(x) for x in P["housing_monthly_per_100m"]]
    _hpol = HousingPolicy(**hp_kwargs)
    if auto_house:
        # 내부 기준월지급액은 60세 기준으로 저장(시뮬레이션이 개시나이별로 환산).
        house_monthly = int(hp.estimate_base_monthly(house_val, _hpol))
        # HF 계산기와 직접 비교되도록 '개시 예정나이(연소자 기준)'의 월지급액을 미리보기로 표시.
        preview_age = sb.slider("미리보기 개시나이(부부 중 연소자)", 55, 90, 70,
                                help="HF 계산기는 부부 중 연소자 나이 기준입니다.")
        preview = hp.monthly_payment(house_monthly, preview_age, _hpol)
        ui.note("info", f"{preview_age}세 개시 시 예상 월지급액 <b>{preview:,.0f}원</b>"
                        f"<br><span style='font-size:.8em'>60세 환산 기준액 {house_monthly:,.0f}원</span>",
                target=sb)
        if house_val > house_cap:
            ui.note("warn", f"주택가격이 가입 상한({house_cap/1e8:g}억)을 넘어 상한 기준으로 산정합니다.",
                    target=sb)
    else:
        house_monthly = sb.number_input("주택연금 기준월지급액(만원)", 0, 1_000, 120, 5) * 10_000

    # --- 제도 파라미터 ---------------------------------------------------------
    sb.divider()
    ui.side_header("sliders", "제도 파라미터")
    sb.caption(f"기본값은 policy.json 의 시행일별 기준에서 오늘 날짜에 맞게 자동 선택됩니다"
               f"(데이터 갱신일 {policy.as_of() or '-'}). 필요하면 직접 바꿔 보세요.")
    with sb.expander("적용 중인 제도 기준"):
        rows = "".join(
            f"<tr><th>{_html.escape(lab)}</th><td>{_html.escape(val)}"
            f"<div class='sm'>{frm} 시행{(' · ' + _html.escape(nxt)) if nxt else ''}</div></td></tr>"
            for lab, val, frm, nxt in policy.describe())
        st.markdown(f"<table class='pol'>{rows}</table>", unsafe_allow_html=True)
    with sb.expander("국민연금 감액·가산·유족"):
        early = st.number_input("조기수령 월감액률(%)", 0.0, 2.0,
                                P.get("nps_early_monthly_reduction", 0.005) * 100, 0.05) / 100
        defer = st.number_input("연기수령 월가산률(%)", 0.0, 2.0,
                                P.get("nps_defer_monthly_increase", 0.006) * 100, 0.05) / 100
        surv = st.number_input("국민 유족연금 지급률(%)", 0.0, 100.0,
                               P.get("nps_survivor_rate", 0.60) * 100, 5.0) / 100
        dup = st.number_input("유족연금 중복조정률(%)", 0.0, 100.0,
                              P.get("survivor_dup_rate", 0.30) * 100, 5.0,
                              help="본인 노령연금 선택 시 함께 받는 유족연금 비율") / 100
        discount = st.number_input("현재가치 할인율(%)", 0.0, 10.0, 2.0, 0.5) / 100
    with sb.expander("교직원·공무원연금"):
        t_early = st.number_input("교직원 조기퇴직 연감액률(%)", 0.0, 10.0, 5.0, 0.5, key="te") / 100
        t_surv = st.number_input("교직원 유족연금 지급률(%)", 0.0, 100.0, 60.0, 5.0, key="ts") / 100
        g_early = st.number_input("공무원 조기퇴직 연감액률(%)", 0.0, 10.0, 5.0, 0.5, key="ge") / 100
        g_surv = st.number_input("공무원 유족연금 지급률(%)", 0.0, 100.0, 60.0, 5.0, key="gs") / 100
    with sb.expander("세금·건보·기초연금"):
        tax_rate = st.number_input("연금소득 실효세율(%)", 0.0, 30.0, 4.0, 0.5,
                                   help="국민·직역·유족연금에 적용(주택연금·기초연금 제외)") / 100
        health_rate = st.number_input("건강보험료율(연금 대비, %)", 0.0, 20.0, 4.0, 0.5,
                                      help="은퇴 후 지역가입 근사") / 100
        basic_amt = st.number_input("기초연금 단독 월액(원)", 0, 1_000_000,
                                    int(P.get("basic_single_amount", 340_000)), 1_000) 
        basic_couple_red = st.number_input("부부 동시수급 감액률(%)", 0.0, 50.0,
                                           P.get("basic_couple_reduction", 0.20) * 100, 5.0) / 100
        basic_crit = st.number_input("기초연금 부부 선정기준액(원)", 0, 20_000_000,
                                     int(P.get("basic_criteria_couple", 3_650_000)), 10_000,
                                     help="월 소득인정액이 이 값 이하면 수급 대상")
        basic_prop_ded = st.number_input("기본재산공제(만원)", 0, 100_000,
                                         int(P.get("basic_property_deduction", 135_000_000) / 10_000), 500,
                                         help="대도시 기준. 소득인정액 계산 시 일반재산에서 공제") * 10_000

    # --- 객체 조립 -------------------------------------------------------------
    husband = Person("남편", **h_args)
    wife = Person("아내", **w_args)

    user = UserInput(
        husband=husband, wife=wife,
        living_expense_monthly=living, single_expense_ratio=single_ratio,
        survivor_mode=survivor_mode, basic_pension_eligible=True,  # 아래에서 모드에 따라 확정
        financial_assets=assets, investment_return=invest, inflation_rate=inflation,
        investment_volatility=volatility,
        other_income_monthly=other_income, other_income_end_age=other_income_end,
        other_property=other_property,
        husband_life_expectancy=h_life, wife_life_expectancy=w_life,
        house_value=house_val, housing_monthly_base=house_monthly,
        use_housing_pension=use_house, retirement_age=retire_age,
    )

    cfg = Config(
        nps=NpsPolicy(early_monthly_reduction=early, defer_monthly_increase=defer,
                      survivor_pension_rate=surv, survivor_dup_rate=dup),
        teacher=TeacherPolicy(early_yearly_reduction=t_early, survivor_pension_rate=t_surv,
                              survivor_dup_rate=dup),
        gov=GovPolicy(early_yearly_reduction=g_early, survivor_pension_rate=g_surv,
                      survivor_dup_rate=dup),
        housing=_hpol,
        tax=TaxPolicy(pension_tax_rate=tax_rate, health_insurance_rate=health_rate),
        basic=BasicPensionPolicy(
            single_amount=basic_amt, couple_reduction=basic_couple_red,
            selection_criteria_couple=basic_crit, property_basic_deduction=basic_prop_ded,
            financial_deduction=P.get("basic_financial_deduction", 20_000_000),
            property_conversion_rate=P.get("basic_conversion_rate", 0.04)),
        optimizer=OptimizerConfig(discount_rate=discount),
    )

    # 기초연금 처리 확정: 자동 판정이면 소득인정액으로 대상 여부를 계산해 반영/제외.
    if basic_mode == "auto":
        _, _, elig = estimate_basic_eligibility(user, cfg)
        user.basic_pension_eligible = elig
    else:
        user.basic_pension_eligible = basic_mode == "on"
    return user, cfg, basic_mode


# ---------------------------------------------------------------------------
# 계산 보조
# ---------------------------------------------------------------------------
def estimate_basic_eligibility(user, cfg):
    """
    현재 입력값으로 기초연금 '소득인정액'을 근사 계산해 대상 여부를 판정.

    소득인정액 = 공적연금소득 + 재산의 소득환산액
    재산환산 = [(주택가격 + 기타재산 − 기본재산공제) + (금융자산 − 금융공제)] × 환산율 ÷ 12
    반환: (소득인정액, 선정기준액, 대상여부)
    """
    bp = cfg.basic
    # 소득평가액(월): 공적연금 + 연금 외 기타소득(근로·임대·이자 등).
    pension_income = user.husband.nps_monthly + user.wife.nps_monthly + user.other_income_monthly
    general = max(0.0, user.house_value + user.other_property - bp.property_basic_deduction)
    financial = max(0.0, user.financial_assets - bp.financial_deduction)
    property_income = (general + financial) * bp.property_conversion_rate / 12.0
    income_recognition = pension_income + property_income
    return income_recognition, bp.selection_criteria_couple, income_recognition <= bp.selection_criteria_couple


BREAKDOWN_ROWS = ["공적연금(세전)", "− 세금·건보", "실수령 연금",
                  "+ 기초연금", "+ 주택연금", "+ 기타소득", "= 월 실수령 합계"]


def income_breakdown(frame, ages=(65, 70, 75, 80)):
    """
    추천 시나리오의 '월수입 구성'을 나이별로 분해. 반환: {"65세": [값 7개], ...} 또는 None.
    항목: 공적연금(세전) → −세금·건보 → 실수령 연금 → +기초연금 → +주택연금 → +기타소득 → =합계.
    """
    if frame.empty:
        return None
    lo, hi = frame["husband_age"].min(), frame["husband_age"].max()
    cols = {}
    for age in ages:
        if age < lo - 0.5 or age > hi:
            continue
        row = frame.iloc[(frame["husband_age"] - age).abs().idxmin()]
        gross = row["h_pension"] + row["w_pension"] + row["survivor_pension"]  # 세전 공적연금
        tax = gross - row["net_taxable"]                                       # 세금·건보 차감액
        cols[f"{age}세"] = [gross, -tax, row["net_taxable"], row["basic_pension"],
                           row["house_income"], row.get("other_income", 0.0), row["income"]]
    return cols or None


def breakdown_html(cols) -> str:
    """월수입 구성표를 반응형 HTML 표로(가로 스크롤 허용, 합계행 강조)."""
    head = "".join(f"<th>{a}</th>" for a in cols)
    body = []
    for i, name in enumerate(BREAKDOWN_ROWS):
        cls = ' class="total"' if i == len(BREAKDOWN_ROWS) - 1 else ""
        cells = "".join(f"<td>{vals[i]/1e4:,.0f}만</td>" for vals in cols.values())
        body.append(f"<tr{cls}><th>{name}</th>{cells}</tr>")
    return ('<div class="tbl-wrap"><table class="bd"><thead><tr><th>항목</th>'
            f'{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>')


def fmt_eok(v: float) -> str:
    """원 → '1.23억' 또는 '4,500만' 표기."""
    return f"{v/1e8:,.2f}억" if abs(v) >= 1e8 else f"{v/1e4:,.0f}만"


def housing_text(row) -> str:
    return f"{int(row['housing'])}세" if row["use_housing"] else "미사용"


def render_view(top, view: str, df):
    """한 관점의 상위 5개 조합을 순위 카드로."""
    cards = []
    for i, (_, row) in enumerate(top.iterrows(), 1):
        pros, cons = opt.explain_parts(row, df)
        facts = [("주택연금", housing_text(row)),
                 ("총수령(현가)", fmt_eok(row["total_pv"])),
                 ("부족", f"{row['shortfall_months']:.0f}개월"),
                 ("상속", fmt_eok(row["bequest"]))]
        cards.append(ui.rank_card(i, f"연금 개시 남편 {int(row['h_claim'])}세 · 아내 {int(row['w_claim'])}세",
                                  f"점수 {row[f'score_{view}']:.3f}", facts, pros, cons))
    st.markdown("".join(cards), unsafe_allow_html=True)


def margin_text(margin, cfg, user) -> tuple[str, str, str]:
    """물가 안전 마진 → (카드 값, 카드 보조문구, 리포트 문장)."""
    if margin is None:
        return ("0% 미만", "현재 가정에서도 부족 발생",
                "현재 가정에서도 생활비 부족 발생 (0% 미만) — 전략 재검토 필요")
    if margin >= cfg.optimizer.margin_max_inflation:
        return (f"{margin*100:.1f}%+", "테스트 상한까지 부족 없음",
                f"물가 {margin*100:.1f}%+ 까지도 부족 없이 매우 견고")
    return (f"~{margin*100:.1f}%", f"물가 {margin*100:.1f}% 초과 시 부족 시작",
            f"물가 ~{margin*100:.1f}% 까지 부족 없이 안전 (현재 가정 물가 {user.inflation_rate*100:.1f}%)")


# ---------------------------------------------------------------------------
# 화면
# ---------------------------------------------------------------------------
def render_landing(user, cfg):
    ui.steps([
        ("couple", "부부 정보 입력", "왼쪽 입력창에서 남편·아내의 연금 종류, 예상 월액, 기대수명을 입력합니다. "
                                  "모바일에서는 왼쪽 위 화살표로 입력창을 엽니다."),
        ("wallet", "생활비·자산·주택", "월 생활비, 금융자산, 주택가격과 주택연금 사용 여부를 정합니다."),
        ("target", "시뮬레이션 실행", "수령나이·주택연금 개시나이의 모든 조합을 물가 스트레스까지 포함해 평가하고 "
                                   "성향별 최적 전략을 추천합니다."),
    ])
    h_normal = pension.normal_start_age(user.husband, cfg)
    w_normal = pension.normal_start_age(user.wife, cfg)
    ui.note("info", f"정상 수령개시연령 — 남편({pension.type_label(user.husband)}) <b>{h_normal}세</b>, "
                    f"아내({pension.type_label(user.wife)}) <b>{w_normal}세</b>")
    ui.note("good", "모든 계산은 <b>이 브라우저 안에서</b> 실행됩니다. 입력한 정보는 서버로 전송되지 않습니다.")


def render_basic_note(user, cfg, mode):
    ir, crit, elig = estimate_basic_eligibility(user, cfg)
    applied = user.basic_pension_eligible
    judge = (f"소득인정액 약 <b>{ir/1e4:,.0f}만원</b> / 부부 선정기준액 {crit/1e4:,.0f}만원 → "
             f"{'대상 가능' if elig else '대상 아님'}")
    if mode == "auto":
        if applied:
            ui.note("good", f"기초연금 자동 판정: <b>수급 반영</b>. {judge}")
        else:
            ui.note("warn", f"기초연금 자동 판정: <b>미수급(제외)</b>. {judge} — 자산·연금이 기준을 넘어 제외했습니다.")
    elif mode == "on":
        extra = "(자격 충족)" if elig else " — 자격 미충족인데 강제 반영(과대평가 주의)"
        ui.note("info" if elig else "warn", f"기초연금 수동 설정: <b>수급</b>{extra}. {judge}")
    else:
        ui.note("info", f"기초연금 수동 설정: <b>미수급</b>{' (자격은 충족)' if elig else ''}. {judge}")


def main():
    ui.inject_css()
    ui.hero("부부 노후자금 통합 시뮬레이터",
            "국민·교직원·공무원연금, 주택연금, 추납, 물가, 기대수명을 통합한 월 단위 현금흐름 시뮬레이션")

    pol_data = policy.load()
    P = policy.current(pol_data)
    run_slot = st.sidebar.container()  # 실행 버튼을 입력창 맨 위에 두기 위한 자리
    user, cfg, basic_mode = build_inputs(P)

    late = policy.overdue(pol_data)
    if late:
        ui.note("warn", "다음 제도값은 정기 갱신 시기가 지났지만 새 값이 아직 반영되지 않았습니다(직전 값 사용): "
                        + ", ".join(_html.escape(x) for x in late), target=st.sidebar)

    # 실행 버튼을 누른 시점의 입력을 스냅샷으로 고정 → 이후 입력을 바꿔도 결과는 그대로 유지되고,
    # 입력을 바꿀 때마다 무거운 계산이 다시 돌지 않는다(브라우저 계산이라 특히 중요).
    def run():
        st.session_state["snap"] = (user, cfg, basic_mode)
        st.session_state.pop("exports", None)

    run_slot.button("시뮬레이션 실행", type="primary", width="stretch", on_click=run, key="run_side")

    snap = st.session_state.get("snap")
    if snap is None:
        render_landing(user, cfg)
        st.button("시뮬레이션 실행", type="primary", on_click=run, key="run_main")
        return
    if repr(snap[:2]) != repr((user, cfg)):
        ui.note("warn", "입력값이 바뀌었습니다. 아래 결과는 이전 입력 기준입니다.")
        st.button("새 입력으로 다시 계산", type="primary", on_click=run, key="run_again")
    user, cfg, basic_mode = snap

    # 1) 계산(같은 입력이면 캐시 재사용) ---------------------------------------
    status = st.empty()
    ui.note("info", "조합을 계산 중입니다(물가 스트레스·몬테카를로 포함). 기기 성능에 따라 수 초~수십 초 걸립니다.",
            target=status)
    R = compute_pipeline(user, cfg)
    status.empty()

    if R["best_scenario"].frame.empty:
        ui.note("bad", "시뮬레이션 기간이 없습니다. 기대수명이 은퇴나이(아내는 그 시점 나이)보다 커야 합니다.")
        return

    df, pareto, tops = R["df"], R["pareto"], R["tops"]
    best_row = tops["stable"].iloc[0]
    best_scenario = R["best_scenario"]
    MC = R["montecarlo"]
    m_val, m_sub, m_report = margin_text(R["margin"], cfg, user)
    infl_list = ", ".join(f"{x*100:.0f}%" for x in cfg.optimizer.robust_inflations)

    # 2) 핵심 요약 --------------------------------------------------------------
    ui.section("target", "핵심 요약",
               f"{R['n']:,}개 조합 평가 · 물가 {infl_list} 스트레스 반영 · 안정형 1위 기준")
    sr = MC["success_rate"] * 100
    sf_months = float(best_row["shortfall_months"])
    ui.kpi_grid([
        ui.kpi("calendar", "추천 연금 개시",
               f"{int(best_row['h_claim'])}세 / {int(best_row['w_claim'])}세", "남편 / 아내", highlight=True),
        ui.kpi("home", "주택연금 개시", housing_text(best_row),
               "부부 중 남편 나이 기준" if best_row["use_housing"] else "주택연금 미사용"),
        ui.kpi("coins", "평생 총수령(현재가치)", fmt_eok(best_row["total_pv"]), "할인율 반영"),
        ui.kpi("check" if sf_months == 0 else "alert", "생활비 부족",
               "없음" if sf_months == 0 else f"{sf_months:.0f}개월",
               "기대수명까지" if sf_months == 0 else f"총 {fmt_eok(best_row['shortfall_total'])}",
               tone="good" if sf_months == 0 else "bad"),
        ui.kpi("gift", "예상 상속(잔여자산)", fmt_eok(best_row["bequest"]), "사망 시점 기준"),
        ui.kpi("thermo", "물가 안전 마진", m_val, m_sub,
               tone="bad" if R["margin"] is None else "good"),
        ui.kpi("pulse", "투자 변동성 성공확률", f"{sr:.0f}%",
               f"변동성 {MC['volatility']*100:.0f}% · {MC['n_sims']}회",
               tone="good" if sr >= 80 else ("warn" if sr >= 60 else "bad")),
    ])
    render_basic_note(user, cfg, basic_mode)

    # 3) 탭 ---------------------------------------------------------------------
    tabs = st.tabs(["추천 전략", "월수입·안전성", "현금흐름·자산", "연금 수령 시점", "전략 비교", "내보내기"])
    report_figs = []  # [(제목, fig)] — HTML 리포트에 담을 그래프 모음

    with tabs[0]:
        ui.section("trophy", "성향별 추천 전략", "관점마다 상위 5개 조합과 자동 장단점")
        guide("views")
        v1, v2, v3 = st.tabs(["안정형", "총수령액 극대화형", "상속중시형"])
        with v1:
            ui.section("shield", "안정형", "생활비 부족 최소화 + 물가에 견고")
            render_view(tops["stable"], "stable", df)
        with v2:
            ui.section("trend", "총수령액 극대화형", "평생 받는 총액(현재가치) 최대화")
            render_view(tops["maximize"], "maximize", df)
        with v3:
            ui.section("gift", "상속중시형", "사망 시 남기는 잔여자산 최대화")
            render_view(tops["bequest"], "bequest", df)

    with tabs[1]:
        ui.section("coins", "추천 전략 월수입 구성", "세전 연금 → 세금·건보 차감 → 기초·주택연금 가산 (명목 금액)")
        bd = income_breakdown(best_scenario.frame)
        if bd:
            st.markdown(breakdown_html(bd), unsafe_allow_html=True)
        guide("breakdown")

        ui.section("thermo", "물가 안전 마진", "물가가 얼마까지 올라도 부족이 없는지")
        worst = best_row.get("worst_infl_shortfall", float("nan"))
        cards = [ui.kpi("thermo", "안전 마진", m_val, m_sub, tone="bad" if R["margin"] is None else "good"),
                 ui.kpi("info", "현재 가정 물가", f"{user.inflation_rate*100:.1f}%")]
        if worst == worst:  # NaN 체크
            cards.append(ui.kpi("alert", "최악 물가 부족액", "없음" if worst <= 0 else fmt_eok(worst),
                                f"물가 {infl_list} 중 최악", tone="good" if worst <= 0 else "bad"))
        ui.kpi_grid(cards)
        guide("margin")

        ui.section("pulse", "투자 변동성 스트레스", "수익률을 매년 무작위로 흔든 몬테카를로 시뮬레이션")
        ui.kpi_grid([
            ui.kpi("check", "성공확률", f"{sr:.0f}%", "부족 없이 끝까지 버팀",
                   tone="good" if sr >= 80 else "warn"),
            ui.kpi("alert", "자산 고갈 확률", f"{MC['depletion_rate']*100:.0f}%", tone="bad"),
            ui.kpi("gift", "상속 자산 중앙값", fmt_eok(MC["bequest_p50"]),
                   f"하위10% {fmt_eok(MC['bequest_p10'])} ~ 상위10% {fmt_eok(MC['bequest_p90'])}"),
        ])
        fig_mc = viz.fig_montecarlo_fan(MC)
        chart(fig_mc, "montecarlo")

    with tabs[2]:
        ui.section("chart", "현금흐름과 자산", "추천 전략(안정형 1위)의 나이별 흐름")
        # 사망 시점(남편 나이축)을 계산해 현금흐름 그래프에 표시.
        wife_start = user.retirement_age - (user.wife.birth_year - user.husband.birth_year)
        h_death_age = float(best_row["h_life"])
        w_death_age = user.retirement_age + (float(best_row["w_life"]) - wife_start)
        deaths = sorted([("남편 사망", h_death_age), ("아내 사망", w_death_age)], key=lambda t: t[1])
        fig_cf = viz.fig_monthly_cashflow(best_scenario, deaths=deaths)
        fig_as = viz.fig_cumulative_assets(best_scenario)
        g1, g2 = st.columns(2)
        chart(fig_cf, "cashflow", g1)
        chart(fig_as, "assets", g2)

    with tabs[3]:
        ui.section("calendar", "나이별 누적 수령액과 원금확보 시점", "언제부터 받으면 몇 세에 낸 보험료를 회수하는지")
        h_lbl = f"남편·{pension.type_label(user.husband)}"
        w_lbl = f"아내·{pension.type_label(user.wife)}"
        fig_h = viz.fig_cumulative_receipts(*R["husband_curves"], h_lbl)
        fig_w = viz.fig_cumulative_receipts(*R["wife_curves"], w_lbl)
        g3, g4 = st.columns(2)
        chart(fig_h, "receipts", g3)
        chart(fig_w, "receipts", g4)

    with tabs[4]:
        ui.section("scale", "전략 비교·민감도", "주택연금 개시나이, 물가, 기대수명에 따라 결과가 어떻게 달라지는지")
        fig_hz = viz.fig_heatmap(df, "shortfall_total")
        g5, g6 = st.columns(2)
        fig_ho = None
        if R["housing_df"] is not None:
            fig_ho = viz.fig_shortfall_by_housing(R["housing_df"])
            chart(fig_ho, "housing", g5)
        else:
            ui.note("info", "주택연금 미사용 — 주택연금 개시시점 그래프는 생략합니다.", target=g5)
        chart(fig_hz, "heatmap", g6)

        fig_in = viz.fig_shortfall_by_inflation(R["inflation_df"])
        fig_li = viz.fig_best_by_life(R["life_df"])
        g7, g8 = st.columns(2)
        chart(fig_in, "inflation", g7)
        chart(fig_li, "life", g8)

        fig_pa = viz.fig_pareto(df, pareto, best_id=R["best_id"])
        g9, g10 = st.columns(2)
        chart(fig_pa, "pareto", g9)
        with g10:
            SCATTER_VIEWS = {"안정형": "stable", "총수령액 극대화형": "maximize", "상속중시형": "bequest"}
            sview = SCATTER_VIEWS[st.segmented_control("색 기준(관점)", list(SCATTER_VIEWS),
                                                       default="안정형", key="scatterview") or "안정형"]
            fig_sc = viz.fig_score_scatter(df, sview, best_id=int(tops[sview].iloc[0]["id"]))
            chart(fig_sc, "scatter")

    report_figs += [("① 연령별 월 현금흐름", fig_cf), ("② 연령별 누적자산", fig_as),
                    (f"③ 누적 수령액·원금확보 ({h_lbl})", fig_h),
                    (f"③ 누적 수령액·원금확보 ({w_lbl})", fig_w)]
    if fig_ho is not None:
        report_figs.append(("④ 주택연금 개시별 부족액", fig_ho))
    report_figs += [("⑤ 국민×주택 히트맵", fig_hz), ("⑥ 물가상승률별 부족액", fig_in),
                    ("⑦ 기대수명별 전략", fig_li), ("⑧ Pareto Frontier", fig_pa),
                    ("⑨ 조합별 점수 산점도", fig_sc), ("⑩ 투자 변동성 스트레스(몬테카를로)", fig_mc)]

    with tabs[5]:
        ui.section("download", "내보내기", "리포트·표를 파일로 저장 (파일도 브라우저 안에서 생성됩니다)")
        summary = {
            "n_combos": R["n"],
            "normal_ages": (f"정상개시 남편({pension.type_label(user.husband)}) "
                            f"{pension.normal_start_age(user.husband, cfg)}세 / "
                            f"아내({pension.type_label(user.wife)}) "
                            f"{pension.normal_start_age(user.wife, cfg)}세"),
            "margin": m_report,
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
                ("세금·건보 / 기초연금",
                 f"연금소득 실효 {(cfg.tax.pension_tax_rate+cfg.tax.health_insurance_rate)*100:.0f}% 차감 · "
                 f"기초연금 {'수급' if user.basic_pension_eligible else '비대상'}"),
            ],
        }
        # 파일 생성(특히 plotly.js 를 통째로 넣는 HTML 리포트)은 무거우므로 한 번 만든 결과를 재사용.
        key = (repr(snap[:2]), sview)
        ex = st.session_state.get("exports")
        if not ex or ex["key"] != key:
            ex = {"key": key,
                  "report": export.build_html_report(report_figs, tops, summary),
                  "csv": export.to_csv_bytes(df),
                  "xlsx": export.to_excel_bytes(df, best_scenario)}
            st.session_state["exports"] = ex
        e1, e2, e3 = st.columns(3)
        e1.download_button("전체 리포트 (HTML · PDF 저장용)", ex["report"], "노후자금리포트.html", "text/html",
                           type="primary", width="stretch")
        e2.download_button("CSV (전체 조합)", ex["csv"], "nps_result.csv", "text/csv",
                           width="stretch")
        e3.download_button("Excel (요약 + 월별)", ex["xlsx"], "nps_result.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           width="stretch")
        st.caption("리포트 파일을 열고 Ctrl+P → '대상: PDF로 저장' 하면 한글·그래프 그대로 PDF가 됩니다.")

    st.caption("본 도구의 연금·주택연금 금액은 근사 계산이며 실제 수급액과 다를 수 있습니다. "
               "정확한 금액은 국민연금공단·한국주택금융공사·복지로의 공식 계산기로 확인하세요.")


if __name__ == "__main__":
    main()
