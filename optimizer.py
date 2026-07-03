"""
optimizer.py
============
전략 조합을 전수 생성하고, 각 조합의 지표를 계산·정규화하여 점수를 매기는 모듈.

흐름
1. generate_strategies() : 국민연금 수령나이 × 주택연금 개시나이 × 추납/임의가입 조합 생성
2. evaluate_all()        : 각 조합을 cashflow.simulate() 로 평가하여 DataFrame 으로 수집
3. score()               : 지표를 0~1 로 정규화하고 관점별 가중합으로 점수 산출
4. pareto_front()        : 다목적 최적점(파레토 경계) 추출

점수 방향
- '작을수록 좋은' 지표(부족액총합, 부족개월수, 최악부족액)는 정규화 시 (max-x)/(max-min) 로 반전.
- '클수록 좋은' 지표(총수령액PV, 잔여자산)는 (x-min)/(max-min) 로 정규화.
"""

from __future__ import annotations

import itertools
from typing import List

import numpy as np
import pandas as pd

import nps
import pension
from cashflow import Strategy, Scenario, simulate
from config import Config, UserInput, Person


# ---------------------------------------------------------------------------
# 1. 조합 생성
# ---------------------------------------------------------------------------
def _claim_age_range(person: Person, cfg: Config) -> List[int]:
    """
    한 사람의 탐색 대상 연금 수령개시나이 목록(정상 ±조기/연기 한도).
    연금 종류(국민연금/교직원연금)에 따라 조기/연기 허용 연수가 다르므로 제도별로 계산한다.
    """
    module, policy = pension.resolve(person, cfg)
    normal = module.normal_start_age(person.birth_year, policy)
    low = normal - policy.max_early_years
    high = normal + policy.max_defer_years
    return list(range(low, high + 1))


def generate_strategies(
    user: UserInput,
    cfg: Config,
    housing_ages: List[int] | None = None,
    inflation_rate: float | None = None,
    husband_life: int | None = None,
    wife_life: int | None = None,
) -> List[Strategy]:
    """
    탐색할 전략 조합을 생성.

    조합 축
    - 남편 국민연금 수령나이
    - 아내 국민연금 수령나이
    - 주택연금 개시나이(및 미사용)
    - 추납 사용 여부(추납가능기간이 있을 때만)
    - 임의가입 사용 여부(임의가입연수가 있을 때만)

    물가/기대수명은 기본값을 쓰되, 민감도 분석용으로 인자로 덮어쓸 수 있다.
    """
    infl = inflation_rate if inflation_rate is not None else user.inflation_rate
    h_life = husband_life if husband_life is not None else user.husband_life_expectancy
    w_life = wife_life if wife_life is not None else user.wife_life_expectancy

    h_ages = _claim_age_range(user.husband, cfg)
    w_ages = _claim_age_range(user.wife, cfg)

    if housing_ages is None:
        # 55세부터 남편 은퇴+15년까지 3년 간격으로 탐색.
        start = cfg.housing.min_start_age
        housing_ages = list(range(start, user.retirement_age + 16, 3))

    # 추납/임의가입은 '입력이 있을 때만' on/off 두 경우를 탐색.
    chunap_opts = [False, True] if (user.husband.chunap_years or user.wife.chunap_years) else [False]
    vol_opts = [False, True] if (user.husband.voluntary_years or user.wife.voluntary_years) else [False]
    housing_opts = [(False, 0)]  # 주택연금 미사용
    if user.use_housing_pension:
        housing_opts += [(True, a) for a in housing_ages]

    strategies: List[Strategy] = []
    for h_age, w_age, (use_h, h_start), uc, uv in itertools.product(
        h_ages, w_ages, housing_opts, chunap_opts, vol_opts
    ):
        strategies.append(
            Strategy(
                husband_claim_age=h_age,
                wife_claim_age=w_age,
                housing_start_age=h_start if use_h else 0,
                use_housing=use_h,
                use_chunap=uc,
                use_voluntary=uv,
                inflation_rate=infl,
                husband_life=h_life,
                wife_life=w_life,
            )
        )
    return strategies


# ---------------------------------------------------------------------------
# 2. 전수 평가
# ---------------------------------------------------------------------------
def evaluate_all(user: UserInput, cfg: Config, strategies: List[Strategy]) -> pd.DataFrame:
    """
    모든 전략을 시뮬레이션하고 지표를 하나의 DataFrame 으로 모은다.
    각 행은 하나의 조합이며, scenario 객체 참조를 함께 보관한다.
    """
    records = []
    scenarios: List[Scenario] = []
    for i, strat in enumerate(strategies):
        sc = simulate(user, strat, cfg)
        scenarios.append(sc)
        rec = {
            "id": i,
            "h_claim": strat.husband_claim_age,
            "w_claim": strat.wife_claim_age,
            "housing": strat.housing_start_age if strat.use_housing else None,
            "use_housing": strat.use_housing,
            "use_chunap": strat.use_chunap,
            "use_voluntary": strat.use_voluntary,
            "inflation": strat.inflation_rate,
            "h_life": strat.husband_life,
            "w_life": strat.wife_life,
            **sc.metrics,
        }
        records.append(rec)

    df = pd.DataFrame(records)
    df.attrs["scenarios"] = scenarios  # 시나리오 객체를 DataFrame 에 부착(그래프에서 재사용)
    return df


# ---------------------------------------------------------------------------
# 3. 정규화 및 점수화
# ---------------------------------------------------------------------------
def _normalize(series: pd.Series, higher_is_better: bool) -> pd.Series:
    """0~1 정규화. 방향에 따라 반전. 분모가 0이면 중립값 0.5."""
    lo, hi = series.min(), series.max()
    if hi == lo:
        return pd.Series(0.5, index=series.index)
    norm = (series - lo) / (hi - lo)
    return norm if higher_is_better else (1.0 - norm)


def score(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """
    각 관점(안정형/총수령액극대화형/상속중시형)별 점수 컬럼을 추가.

    지표 정규화
    - shortfall_total, shortfall_months, worst_shortfall : 작을수록 좋음
    - total_pv, bequest                                   : 클수록 좋음
    """
    out = df.copy()

    norm = pd.DataFrame(index=out.index)
    norm["shortfall_total"] = _normalize(out["shortfall_total"], higher_is_better=False)
    norm["shortfall_months"] = _normalize(out["shortfall_months"], higher_is_better=False)
    norm["worst_shortfall"] = _normalize(out["worst_shortfall"], higher_is_better=False)
    norm["total_pv"] = _normalize(out["total_pv"], higher_is_better=True)
    norm["bequest"] = _normalize(out["bequest"], higher_is_better=True)

    for view, weights in cfg.optimizer.weights.items():
        out[f"score_{view}"] = sum(norm[k] * w for k, w in weights.items())

    return out


def top_n(df: pd.DataFrame, view: str, n: int = 5) -> pd.DataFrame:
    """특정 관점 점수 상위 n개 조합."""
    col = f"score_{view}"
    return df.sort_values(col, ascending=False).head(n).reset_index(drop=True)


# ---------------------------------------------------------------------------
# 4. 파레토 경계
# ---------------------------------------------------------------------------
def pareto_front(df: pd.DataFrame) -> pd.DataFrame:
    """
    2목적(총수령액PV ↑, 부족액총합 ↓) 기준 파레토 경계 조합을 추출.

    한 점이 다른 점보다 두 목적 모두에서 나쁘지 않고 하나 이상에서 더 나으면 지배당함.
    지배당하지 않는 점들만 남긴다.
    """
    pts = df[["total_pv", "shortfall_total"]].values
    n = len(pts)
    is_pareto = np.ones(n, dtype=bool)
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            # j 가 i 를 지배하는가? (PV 는 클수록, shortfall 은 작을수록 좋음)
            if pts[j, 0] >= pts[i, 0] and pts[j, 1] <= pts[i, 1] and (
                pts[j, 0] > pts[i, 0] or pts[j, 1] < pts[i, 1]
            ):
                is_pareto[i] = False
                break
    return df[is_pareto].sort_values("total_pv", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# 5. 자동 장단점 설명
# ---------------------------------------------------------------------------
def explain(row: pd.Series, df: pd.DataFrame) -> str:
    """
    한 조합의 장단점을 다른 조합 대비 상대적으로 자동 서술.
    상위 조합 표에 함께 보여줄 한 줄 설명을 생성한다.
    """
    pros, cons = [], []

    # 부족액이 전혀 없으면 큰 장점.
    if row["shortfall_total"] <= 0:
        pros.append("생활비 부족이 전혀 없음")
    else:
        cons.append(f"생활비 부족 {row['shortfall_months']:.0f}개월 발생")

    # 총수령액이 상위 25% 이면 장점.
    if row["total_pv"] >= df["total_pv"].quantile(0.75):
        pros.append("총수령액(현재가치)이 상위권")
    elif row["total_pv"] <= df["total_pv"].quantile(0.25):
        cons.append("총수령액이 낮은 편")

    # 잔여자산(상속) 평가.
    if row["bequest"] >= df["bequest"].quantile(0.75):
        pros.append("사망시 잔여자산 많음(상속 유리)")
    elif row["bequest"] <= df["bequest"].quantile(0.25):
        cons.append("상속 잔여자산 적음")

    # 자산 고갈 여부.
    if row.get("depletion_age") is not None and not pd.isna(row.get("depletion_age")):
        cons.append(f"{row['depletion_age']:.0f}세경 금융자산 고갈")

    pro_txt = " / ".join(pros) if pros else "특별한 강점 없음"
    con_txt = " / ".join(cons) if cons else "뚜렷한 단점 없음"
    return f"👍 {pro_txt}  ｜  👎 {con_txt}"


# ---------------------------------------------------------------------------
# 6. 민감도 분석 헬퍼(그래프용)
# ---------------------------------------------------------------------------
def _breakeven_age(module, person, claim_age, policy, inflation, principal, max_age=110):
    """
    원금확보(손익분기) 나이 계산.

    개시나이부터 누적 연금수령액이 '납입원금(principal)'을 처음으로 넘어서는 나이를 반환.
    - 물가연동을 반영한 각 연도 수령액을 누적한다.
    - 납입원금이 0이거나 수명 내에 회수되지 않으면 None.
    """
    if principal <= 0:
        return None
    base = module.monthly_pension(person, claim_age, policy)
    cumulative = 0.0
    for y in range(0, max_age - claim_age):
        cumulative += module.indexed_monthly_pension(base, y, inflation, policy) * 12
        if cumulative >= principal:
            return claim_age + y + 1  # 해당 연차 말 기준 나이
    return None


def nps_receipts_by_claim_age(user: UserInput, cfg: Config, which: str = "husband") -> pd.DataFrame:
    """
    연금 수령개시나이별 '명목 총수령액', '개시시점 월수령액', '납입원금', '원금확보 나이'를 계산.
    그래프3(수령시점별 총수령액 비교)용. 대상자의 연금 제도(국민/교직원)에 맞춰 계산한다.

    - principal(납입원금)과 breakeven_age(원금확보 나이)를 함께 반환하여
      "언제부터 받으면 몇 세에 원금을 회수하는지"를 시각화할 수 있게 한다.
    """
    person = user.husband if which == "husband" else user.wife
    death = user.husband_life_expectancy if which == "husband" else user.wife_life_expectancy
    module, policy = pension.resolve(person, cfg)
    principal = getattr(person, "paid_principal", 0.0)
    ages = _claim_age_range(person, cfg)
    rows = []
    for age in ages:
        monthly = module.monthly_pension(person, age, policy)
        total = module.total_nominal_receipts(person, age, death, user.inflation_rate, policy)
        be_age = _breakeven_age(module, person, age, policy, user.inflation_rate, principal)
        rows.append({
            "claim_age": age,
            "monthly": monthly,
            "total_nominal": total,
            "principal": principal,
            "breakeven_age": be_age,
        })
    return pd.DataFrame(rows)


def shortfall_by_housing_age(user: UserInput, cfg: Config) -> pd.DataFrame:
    """
    주택연금 개시나이별 '부족액총합'을 계산(다른 조건은 기본 전략 고정).
    그래프4(주택연금 개시시점별 부족액 비교)용.
    """
    from cashflow import build_strategy_from_user

    base = build_strategy_from_user(user, cfg)
    start = cfg.housing.min_start_age
    ages = list(range(start, user.retirement_age + 16))
    rows = []
    for age in ages:
        strat = Strategy(
            husband_claim_age=base.husband_claim_age,
            wife_claim_age=base.wife_claim_age,
            housing_start_age=age,
            use_housing=True,
            use_chunap=base.use_chunap,
            use_voluntary=base.use_voluntary,
            inflation_rate=base.inflation_rate,
            husband_life=base.husband_life,
            wife_life=base.wife_life,
        )
        sc = simulate(user, strat, cfg)
        rows.append({"housing_age": age, "shortfall_total": sc.metrics["shortfall_total"]})
    return pd.DataFrame(rows)


def shortfall_by_inflation(user: UserInput, cfg: Config) -> pd.DataFrame:
    """
    물가상승률 시나리오별 '부족액총합'(기본 전략 고정).
    그래프6(물가상승률별 부족액)용.
    """
    from cashflow import build_strategy_from_user

    base = build_strategy_from_user(user, cfg)
    rows = []
    for infl in cfg.optimizer.inflation_scenarios:
        strat = Strategy(**{**base.__dict__, "inflation_rate": infl})
        sc = simulate(user, strat, cfg)
        rows.append({"inflation": infl, "shortfall_total": sc.metrics["shortfall_total"]})
    return pd.DataFrame(rows)


def best_strategy_by_life(user: UserInput, cfg: Config, view: str = "stable") -> pd.DataFrame:
    """
    기대수명 시나리오별로 최적 전략을 찾아 비교.
    그래프7(기대수명별 유리한 전략)용.
    """
    rows = []
    for life in cfg.optimizer.life_expectancy_scenarios:
        # 부부 기대수명을 동일 시나리오로 두고(간이) 탐색.
        strategies = generate_strategies(user, cfg, husband_life=life, wife_life=life + 4)
        df = evaluate_all(user, cfg, strategies)
        df = score(df, cfg)
        best = df.sort_values(f"score_{view}", ascending=False).iloc[0]
        rows.append(
            {
                "life": life,
                "h_claim": best["h_claim"],
                "w_claim": best["w_claim"],
                "housing": best["housing"],
                "total_pv": best["total_pv"],
                "shortfall_total": best["shortfall_total"],
                "bequest": best["bequest"],
            }
        )
    return pd.DataFrame(rows)
