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
from typing import List, Optional

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

    # 추납/임의가입은 '사용자가 입력하면 항상 적용'(가입 결정은 사용자 몫).
    # → 모든 그래프·지표에서 일관되게 반영된다.
    chunap_opts = [True] if (user.husband.chunap_years or user.wife.chunap_years) else [False]
    vol_opts = [True] if (user.husband.voluntary_years or user.wife.voluntary_years) else [False]
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
def _worst_inflation_shortfall(user: UserInput, cfg: Config, strat: Strategy) -> float:
    """
    '최악 물가에서의 부족액총합'을 반환(물가 예측 불가 대비 로버스트 지표).

    생활비 부족액은 물가상승률이 높을수록 커진다(물가연동 연금보다 생활비·명목 주택연금
    영향이 커서 사실상 단조 증가). 따라서 스트레스 물가 중 '가장 높은 값' 하나만 평가하면
    최악값을 얻을 수 있어, 5회 시뮬레이션을 1회로 줄여 속도를 크게 개선한다.
    """
    worst_infl = max(cfg.optimizer.robust_inflations)
    stressed = Strategy(**{**strat.__dict__, "inflation_rate": worst_infl})
    return simulate(user, stressed, cfg, record=False).metrics["shortfall_total"]


def evaluate_all(
    user: UserInput, cfg: Config, strategies: List[Strategy], robust: bool = False
) -> pd.DataFrame:
    """
    모든 전략을 시뮬레이션하고 지표를 하나의 DataFrame 으로 모은다.
    각 행은 하나의 조합이며, scenario 객체 참조를 함께 보관한다.

    robust=True 이면 각 전략을 물가 스트레스 시나리오들에서도 돌려
    'worst_infl_shortfall'(최악 물가 부족액) 컬럼을 추가한다.
    """
    records = []
    for i, strat in enumerate(strategies):
        # 지표만 계산(record=False): 월별 표를 만들지 않아 메모리를 크게 절약.
        sc = simulate(user, strat, cfg, record=False)
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
            # 조합표에는 스칼라 지표만(연말자산 배열 등 무거운/MC 전용 키는 제외).
            **{k: v for k, v in sc.metrics.items()
               if k not in ("assets_yearly", "start_age_h", "house_bequest")},
        }
        if robust:
            rec["worst_infl_shortfall"] = _worst_inflation_shortfall(user, cfg, strat)
        records.append(rec)

    return pd.DataFrame(records)


def inflation_safety_margin(user: UserInput, cfg: Config, strat: Strategy) -> Optional[float]:
    """
    물가 안전 마진: 생활비 부족이 '처음 발생하기 직전'까지 견디는 최대 물가상승률.

    0% 부터 상한(margin_max_inflation)까지 step 간격으로 올리며 부족이 없는 마지막 물가를 찾는다.
    - 0% 에서도 이미 부족이면 None(현재도 안전하지 않음).
    - 상한까지 부족이 없으면 상한값 반환(그 이상도 안전 가능).
    """
    cfgo = cfg.optimizer
    last_safe: Optional[float] = None
    infl = 0.0
    while infl <= cfgo.margin_max_inflation + 1e-9:
        stressed = Strategy(**{**strat.__dict__, "inflation_rate": infl})
        sc = simulate(user, stressed, cfg, record=False)
        if sc.metrics["shortfall_total"] <= 0:
            last_safe = infl
        else:
            break  # 부족이 생기기 시작하면 더 높은 물가는 볼 필요 없음(단조 증가 가정)
        infl += cfgo.margin_step
    return last_safe


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
    # 로버스트 평가가 있으면(evaluate_all robust=True) 최악 물가 부족액도 정규화에 포함.
    if "worst_infl_shortfall" in out.columns:
        norm["worst_infl_shortfall"] = _normalize(out["worst_infl_shortfall"], higher_is_better=False)

    for view, weights in cfg.optimizer.weights.items():
        # 현재 존재하는 지표에 대해서만 가중치를 적용하고, 합이 1이 되도록 재정규화한다.
        avail = {k: w for k, w in weights.items() if k in norm.columns}
        total_w = sum(avail.values()) or 1.0
        out[f"score_{view}"] = sum(norm[k] * (w / total_w) for k, w in avail.items())

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

    # 물가 로버스트: 최악 물가에서도 부족이 없으면 큰 장점.
    if "worst_infl_shortfall" in row and not pd.isna(row.get("worst_infl_shortfall")):
        if row["worst_infl_shortfall"] <= 0:
            pros.append("최악 물가에서도 부족 없음(물가 안전)")
        elif row["worst_infl_shortfall"] >= df["worst_infl_shortfall"].quantile(0.75):
            cons.append("고물가에 취약")

    pro_txt = " / ".join(pros) if pros else "특별한 강점 없음"
    con_txt = " / ".join(cons) if cons else "뚜렷한 단점 없음"
    return f"👍 {pro_txt}  ｜  👎 {con_txt}"


# ---------------------------------------------------------------------------
# 6. 민감도 분석 헬퍼(그래프용)
# ---------------------------------------------------------------------------
def _breakeven_age(module, person, claim_age, policy, inflation, principal,
                   use_chunap=False, use_voluntary=False, max_age=110):
    """
    원금확보(손익분기) 나이 계산.

    개시나이부터 누적 연금수령액이 '납입원금(principal)'을 처음으로 넘어서는 나이를 반환.
    - 물가연동을 반영한 각 연도 수령액을 누적한다.
    - 납입원금이 0이거나 수명 내에 회수되지 않으면 None.
    """
    if principal <= 0:
        return None
    base = module.monthly_pension(person, claim_age, policy, use_chunap, use_voluntary)
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
    uc = person.chunap_years > 0       # 추납 반영
    uv = person.voluntary_years > 0    # 임의가입 반영
    ages = _claim_age_range(person, cfg)
    rows = []
    for age in ages:
        monthly = module.monthly_pension(person, age, policy, uc, uv)
        total = module.total_nominal_receipts(person, age, death, user.inflation_rate, policy, uc, uv)
        be_age = _breakeven_age(module, person, age, policy, user.inflation_rate, principal, uc, uv)
        rows.append({
            "claim_age": age,
            "monthly": monthly,
            "total_nominal": total,
            "principal": principal,
            "breakeven_age": be_age,
        })
    return pd.DataFrame(rows)


def cumulative_receipts_curves(user: UserInput, cfg: Config, which: str = "husband"):
    """
    수령개시나이별 '나이에 따른 누적 수령액' 곡선을 계산.
    그래프3(원금확보 시점 시각화)용. X축은 개시나이부터 '기대수명'까지 그린다.

    반환
    - curves : long DataFrame(claim_age, age, cumulative)
    - principal : 납입원금
    - breakevens : {claim_age: 원금확보 나이 or None}
    - death : 기대수명(그래프 우측 끝)
    - reps : 그린 대표 개시나이 목록(조기/정상/연기)
    - monthlies : {claim_age: 개시시점 월수령액} — 곡선 라벨에 '월 얼마' 표시용

    대표 개시나이만 그려 가독성을 확보한다(전체를 다 그리면 곡선이 겹쳐 알아보기 어려움).
    """
    person = user.husband if which == "husband" else user.wife
    death = user.husband_life_expectancy if which == "husband" else user.wife_life_expectancy
    module, policy = pension.resolve(person, cfg)
    principal = getattr(person, "paid_principal", 0.0)
    uc = person.chunap_years > 0       # 추납 반영
    uv = person.voluntary_years > 0    # 임의가입 반영

    ages = _claim_age_range(person, cfg)
    normal = module.normal_start_age(person.birth_year, policy)
    # 대표 개시나이: 조기 최대(가장 이른) · 정상 · 연기 최대(가장 늦은).
    reps = sorted({ages[0], normal, ages[-1]})

    rows = []
    breakevens = {}
    monthlies = {}
    for ca in reps:
        base = module.monthly_pension(person, ca, policy, uc, uv)
        monthlies[ca] = base  # 개시시점 월수령액(명목)
        cumulative = 0.0
        be = None
        rows.append({"claim_age": ca, "age": ca, "cumulative": 0.0})  # 시작점(0원)
        for y in range(0, death - ca):
            cumulative += module.indexed_monthly_pension(base, y, user.inflation_rate, policy) * 12
            age = ca + y + 1  # 해당 연차 말의 나이
            rows.append({"claim_age": ca, "age": age, "cumulative": cumulative})
            if be is None and principal > 0 and cumulative >= principal:
                be = age
        breakevens[ca] = be

    return pd.DataFrame(rows), principal, breakevens, death, reps, monthlies


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
        sc = simulate(user, strat, cfg, record=False)
        rows.append({"housing_age": age, "shortfall_total": sc.metrics["shortfall_total"]})
    return pd.DataFrame(rows)


def shortfall_by_inflation(user: UserInput, cfg: Config) -> pd.DataFrame:
    """
    물가상승률별 '부족액총합'(기본 전략 고정). 그래프6용.

    사용자가 입력한 물가상승률을 '중심'으로 ±2%p 범위를 잡아, 현재 가정값이 항상 그래프에
    포함되고 표시되도록 한다(is_current). 이렇게 해야 사이드바 물가 변경이 그래프에 반영된다.
    """
    from cashflow import build_strategy_from_user

    base = build_strategy_from_user(user, cfg)
    center = round(user.inflation_rate, 4)
    infls = sorted({max(0.0, round(center + d, 4)) for d in (-0.02, -0.01, 0.0, 0.01, 0.02)})
    rows = []
    for infl in infls:
        strat = Strategy(**{**base.__dict__, "inflation_rate": infl})
        sc = simulate(user, strat, cfg, record=False)
        rows.append({"inflation": infl, "shortfall_total": sc.metrics["shortfall_total"],
                     "is_current": abs(infl - center) < 1e-9})
    return pd.DataFrame(rows)


def best_strategy_by_life(user: UserInput, cfg: Config, view: str = "stable") -> pd.DataFrame:
    """
    기대수명 시나리오별로 최적 전략을 찾아 비교.
    그래프7(기대수명별 유리한 전략)용.
    """
    # 속도: 기대수명 민감도는 '수령나이' 중심 비교이므로 주택연금 개시나이는 대표 1개로 고정해
    # 조합 수를 줄인다(전체 격자 탐색은 메인 결과에서 이미 수행).
    rep_house = [max(cfg.housing.min_start_age, user.retirement_age)]
    rows = []
    for life in cfg.optimizer.life_expectancy_scenarios:
        # 부부 기대수명을 동일 시나리오로 두고(간이) 탐색.
        strategies = generate_strategies(user, cfg, housing_ages=rep_house,
                                         husband_life=life, wife_life=life + 4)
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
