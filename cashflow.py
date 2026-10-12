"""
cashflow.py
===========
부부의 은퇴 후 현금흐름을 '월 단위'로 시뮬레이션하는 핵심 모듈.

한 번의 시뮬레이션(=하나의 전략 조합)은 다음을 입력으로 받는다.
- 부부 각자의 국민연금 수령개시나이
- 주택연금 개시나이 / 사용 여부
- 추납·임의가입 사용 여부
- 물가상승률, 기대수명(부부 각자)

그리고 다음을 출력한다(Scenario 객체).
- 월별 현금흐름 표(DataFrame)
- 요약 지표(총수령액, 현재가치, 부족액, 부족개월수, 최악부족액, 자산고갈시점, 잔여자산 등)

계산식은 아래 함수들로 분리되어 있고, simulate() 가 이를 월 루프로 합성한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

import nps
import pension
import housing_pension as hp
from config import Config, UserInput, Person


# ---------------------------------------------------------------------------
# 전략 조합 정의
# ---------------------------------------------------------------------------
@dataclass
class Strategy:
    """하나의 노후 전략 조합(탐색 대상)."""

    husband_claim_age: int
    wife_claim_age: int
    housing_start_age: int
    use_housing: bool
    use_chunap: bool
    use_voluntary: bool
    inflation_rate: float
    husband_life: int
    wife_life: int


@dataclass
class Scenario:
    """시뮬레이션 결과(월별 표 + 요약 지표)."""

    strategy: Strategy
    frame: pd.DataFrame
    metrics: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 보조 계산 함수
# ---------------------------------------------------------------------------
def monthly_rate(annual_rate: float) -> float:
    """연이율 -> 월복리 환산 이율."""
    return (1.0 + annual_rate) ** (1.0 / 12.0) - 1.0


def _wife_age_at_start(user: UserInput) -> int:
    """시뮬레이션 시작 시점(남편 은퇴나이)에서 아내의 나이."""
    age_gap = user.wife.birth_year - user.husband.birth_year  # 아내가 어리면 양수
    return user.retirement_age - age_gap


def housing_age_gap(user: UserInput) -> int:
    """
    주택연금 월지급액은 '부부 중 연소자' 나이로 산정된다(HF 기준).
    남편 나이축의 개시나이에서 이 값을 빼면 연소자 나이가 된다(아내가 어리면 양수, 아니면 0).
    """
    return max(0, user.wife.birth_year - user.husband.birth_year)


def housing_min_start(user: UserInput, cfg: Config) -> int:
    """
    주택연금 탐색 시작나이(남편 나이축).
    - 시뮬레이션이 은퇴나이에서 시작하므로 그 이전 개시는 의미가 없다.
    - 가입요건: 부부 중 1명(연장자)이 min_start_age 이상.
    """
    older_gap = max(0, user.husband.birth_year - user.wife.birth_year)  # 아내가 연상이면 양수
    return max(user.retirement_age, cfg.housing.min_start_age - older_gap)


def _person_base_pension(
    person: Person, claim_age: int, cfg: Config, use_chunap: bool, use_voluntary: bool
) -> float:
    """개시시점 월연금(명목). 사람의 연금 종류(국민연금/교직원연금)에 맞춰 계산."""
    module, policy = pension.resolve(person, cfg)
    return module.monthly_pension(person, claim_age, policy, use_chunap, use_voluntary)


def _survivor_total(own_pension: float, deceased_pension: float, dead_policy, mode: str) -> float:
    """
    배우자 사망 시 생존자가 받는 '총 월연금'(중복급여 조정).

    - 유족연금 = 사망자 연금 × 유족지급률(dead_policy.survivor_pension_rate, 예:60%)
    - 선택지 A(본인연금 우선) : 본인 노령연금 + 유족연금 × 중복조정률(예:30%)
    - 선택지 B(유족연금 전액) : 유족연금 전액(본인 노령연금 포기)
    - mode: "own_plus"=A, "survivor_full"=B, "auto"=둘 중 큰 값(유리한 쪽)

    반환값은 '본인연금+유족조정'을 포함한 생존자 총 수령액이다.
    """
    survivor = deceased_pension * dead_policy.survivor_pension_rate
    opt_a = own_pension + survivor * getattr(dead_policy, "survivor_dup_rate", 0.30)
    opt_b = survivor
    if mode == "own_plus":
        return opt_a
    if mode == "survivor_full":
        return opt_b
    return max(opt_a, opt_b)  # auto


# ---------------------------------------------------------------------------
# 메인 시뮬레이션
# ---------------------------------------------------------------------------
def simulate(user: UserInput, strat: Strategy, cfg: Config, record: bool = True,
             annual_returns=None) -> Scenario:
    """
    하나의 전략에 대해 월 단위 현금흐름을 시뮬레이션한다.

    타임라인
    - 기준: 남편 은퇴나이(user.retirement_age)를 month 0 으로 둔다.
    - 종료: 부부 중 나중에 사망하는 사람의 사망시점까지.

    성능/메모리
    - record=True  : 월별 상세 표(DataFrame)를 만들어 그래프에 사용(추천 시나리오 1개 등).
    - record=False : 표를 만들지 않고 누적값으로 지표만 계산(수천 개 조합 탐색용).
      수백~수천 조합을 평가할 때 DataFrame 생성을 생략해 메모리·속도를 크게 절약한다.
    """
    start_age_h = user.retirement_age
    start_age_w = _wife_age_at_start(user)

    # 각자의 사망까지 남은 개월 수(시작 기준).
    h_end_month = max(0, (strat.husband_life - start_age_h) * 12)
    w_end_month = max(0, (strat.wife_life - start_age_w) * 12)
    total_months = max(h_end_month, w_end_month)

    # 월 이율. annual_returns(연도별 수익률 배열)가 주어지면 그 해의 수익률을 사용(변동성 시뮬).
    if annual_returns is not None and len(annual_returns) > 0:
        n_yr = total_months // 12 + 1
        monthly_rates = [monthly_rate(annual_returns[min(y, len(annual_returns) - 1)])
                         for y in range(n_yr)]
        r_invest = None
    else:
        r_invest = monthly_rate(user.investment_return)
        monthly_rates = None
    r_disc = monthly_rate(cfg.optimizer.discount_rate)
    disc_base = 1.0 + r_disc

    # 세금·건보 실효율(공적연금 실수령 계수)과 기초연금 정책.
    tx = cfg.tax

    # 개인·퇴직연금: 수령 시작까지 투자수익률로 불리고, 수령기간 동안 원리금 균등 수령.
    pp_bal = user.private_pension_balance
    pp_r = monthly_rate(user.investment_return)
    pp_start_m = max(0, int(round((user.private_pension_start_age - start_age_h) * 12)))
    pp_n = max(1, user.private_pension_years * 12)
    pp_pmt = 0.0
    if pp_bal > 0:
        bal_at_start = pp_bal * (1.0 + pp_r) ** pp_start_m
        pp_pmt = bal_at_start * pp_r / (1.0 - (1.0 + pp_r) ** (-pp_n)) if pp_r > 0 else bal_at_start / pp_n
    pp_annual = pp_pmt * 12
    flat_health = tx.health_mode == "flat"
    tax_rate = tx.pension_tax_rate + (tx.health_insurance_rate if flat_health else 0.0)
    # 재산세 과세표준(근사, 시작 시점). 이후 주택가격 상승률로 키운다.
    prop_base0 = user.house_value * tx.house_tax_base_ratio + user.other_property * tx.other_tax_base_ratio
    health_total = 0.0
    dep_lost_age: Optional[float] = None    # 피부양자 자격을 처음 잃는 나이(남편 나이축)
    dep_lost_premium = 0.0                  # 그때의 월 건보료
    bp = cfg.basic

    # 부부 각자의 연금 계산 모듈/정책(국민연금 vs 교직원연금)을 미리 확정.
    h_mod, h_pol = pension.resolve(user.husband, cfg)
    w_mod, w_pol = pension.resolve(user.wife, cfg)

    # 개시시점 월연금(명목).
    h_base = _person_base_pension(
        user.husband, strat.husband_claim_age, cfg, strat.use_chunap, strat.use_voluntary
    )
    w_base = _person_base_pension(
        user.wife, strat.wife_claim_age, cfg, strat.use_chunap, strat.use_voluntary
    )

    # 주택연금 개시시점 월지급액(명목).
    house_base = (
        hp.monthly_payment(user.housing_monthly_base,
                           strat.housing_start_age - housing_age_gap(user), cfg.housing)
        if strat.use_housing and user.house_value > 0
        else 0.0
    )

    # 유족연금 산정 기준액(사망자 쪽).
    # - 국민연금: 법상 유족연금은 '기본연금액'(조기감액·연기가산 전) 기준 → 정상개시 기준 월액.
    # - 직역연금: 받고 있던 퇴직연금 기준. 개시 전에 사망하면 정상개시 기준 월액.
    def _survivor_base(person, claimed_base, claim_age, death_age):
        if person.pension_type != "nps" and death_age >= claim_age:
            return claimed_base
        normal = pension.normal_start_age(person, cfg)
        return _person_base_pension(person, normal, cfg, strat.use_chunap, strat.use_voluntary)

    h_surv_base = _survivor_base(user.husband, h_base, strat.husband_claim_age, strat.husband_life)
    w_surv_base = _survivor_base(user.wife, w_base, strat.wife_claim_age, strat.wife_life)

    # 초기 금융자산에서 추납/임의가입 비용 차감.
    assets = user.financial_assets
    if strat.use_chunap:
        assets -= user.husband.chunap_cost + user.wife.chunap_cost
    if strat.use_voluntary:
        assets -= user.husband.voluntary_cost + user.wife.voluntary_cost

    # 누적 지표(표 없이 계산).
    total_nominal = 0.0
    total_pv = 0.0
    shortfall_total = 0.0
    shortfall_months = 0
    worst_shortfall = 0.0
    survivor_min_net = 0.0
    has_single = False
    depletion_age: Optional[float] = None
    assets_yearly = []  # 연말 자산 스냅샷(팬차트/몬테카를로용)

    rows = [] if record else None

    for m in range(total_months):
        year_idx = m // 12  # 시작 후 경과 연차(물가연동/성장 계산용)

        h_age = start_age_h + m / 12.0
        w_age = start_age_w + m / 12.0

        h_alive = m < h_end_month
        w_alive = m < w_end_month

        # --- 1) 연금 수입 계산 ---
        # 남편 연금
        h_pension = 0.0
        # 입력 월액은 '현재가치'이므로 생활비와 똑같이 시작 시점부터 물가를 반영한다
        # (개시 전 기간의 물가를 빼먹으면 연기수령이 실질적으로 불리하게 왜곡됨).
        if h_alive and h_age >= strat.husband_claim_age:
            h_pension = h_mod.indexed_monthly_pension(
                h_base, year_idx, strat.inflation_rate, h_pol
            )
        # 아내 연금
        w_pension = 0.0
        if w_alive and w_age >= strat.wife_claim_age:
            w_pension = w_mod.indexed_monthly_pension(
                w_base, year_idx, strat.inflation_rate, w_pol
            )

        # --- 2) 유족연금(한쪽 사망 시, 중복급여 조정) ---
        # 생존자는 '본인 노령연금 + 유족연금 일부' vs '유족연금 전액' 중 선택(user.survivor_mode).
        # survivor_extra = 본인연금 위에 '추가로' 받는 금액(선택 총액 - 본인연금).
        survivor_extra = 0.0
        if h_alive and not w_alive and w_surv_base > 0:
            dead_pension = w_mod.indexed_monthly_pension(
                w_surv_base, year_idx, strat.inflation_rate, w_pol
            )
            survivor_extra = _survivor_total(h_pension, dead_pension, w_pol, user.survivor_mode) - h_pension
        elif w_alive and not h_alive and h_surv_base > 0:
            dead_pension = h_mod.indexed_monthly_pension(
                h_surv_base, year_idx, strat.inflation_rate, h_pol
            )
            survivor_extra = _survivor_total(w_pension, dead_pension, h_pol, user.survivor_mode) - w_pension

        # --- 3) 주택연금(종신: 마지막 생존자까지 지급) ---
        house_income = 0.0
        if house_base > 0 and (h_alive or w_alive) and h_age >= strat.housing_start_age:
            years_since = int(h_age - strat.housing_start_age)
            house_income = hp.indexed_monthly_payment(
                house_base, years_since, strat.inflation_rate, cfg.housing
            )

        # --- 3-b) 연금소득세(공적연금·유족연금에만, 주택연금 제외) ---
        taxable = h_pension + w_pension + survivor_extra
        net_taxable = taxable * (1.0 - tax_rate)          # 세후(건보료는 아래 3-e 에서 차감)

        # --- 3-c) 기초연금(65세 이상, 비과세). 부부 동시 수급 시 각 감액 ---
        basic_pension = 0.0
        if user.basic_pension_eligible:
            bp_amt = bp.single_amount * ((1.0 + strat.inflation_rate) ** year_idx
                                         if bp.inflation_indexed else 1.0)
            h_gets = h_alive and h_age >= bp.start_age
            w_gets = w_alive and w_age >= bp.start_age
            both_gets = h_gets and w_gets
            if h_gets:
                basic_pension += bp_amt * (1.0 - bp.couple_reduction if both_gets else 1.0)
            if w_gets:
                basic_pension += bp_amt * (1.0 - bp.couple_reduction if both_gets else 1.0)

        # --- 3-d) 연금 외 기타소득(근로·임대·이자 등). 물가연동, 지정 나이까지만 ---
        other_income = 0.0
        if (h_alive or w_alive) and user.other_income_monthly > 0 and h_age < user.other_income_end_age:
            other_income = user.other_income_monthly * ((1.0 + strat.inflation_rate) ** year_idx)

        # --- 3-e) 건강보험료: 피부양자면 0, 아니면 지역가입자(소득분+재산분)×(1+장기요양) ---
        health = 0.0
        if not flat_health and (h_alive or w_alive):
            h_inc = (h_pension + (survivor_extra if not w_alive else 0.0) + other_income) * 12 if h_alive else 0.0
            w_inc = (w_pension + (survivor_extra if not h_alive else 0.0)) * 12 if w_alive else 0.0
            incomes = [x for x, alive in ((h_inc, h_alive), (w_inc, w_alive)) if alive]
            prop_base = prop_base0 * ((1.0 + cfg.housing.house_growth_rate) ** year_idx)
            income_ok = all(x <= tx.dependent_income_limit for x in incomes)   # 부부 중 한 명이라도 넘으면 둘 다 탈락
            prop_ok = (prop_base <= tx.dependent_property_limit or
                       (prop_base <= tx.dependent_property_limit_high and
                        all(x <= tx.dependent_income_limit_mid for x in incomes)))
            if not (user.health_dependent_possible and income_ok and prop_ok):
                income_part = (taxable * tx.local_pension_ratio + other_income) * tx.health_rate
                prop_part = max(0.0, prop_base - tx.property_deduction) / 100_000_000 * tx.property_premium_per_100m
                health = (income_part + prop_part) * (1.0 + tx.ltc_ratio)
                if dep_lost_age is None:
                    dep_lost_age = round(h_age, 1)
                    dep_lost_premium = health
            net_taxable -= health
            health_total += health

        # --- 3-f) 개인·퇴직연금(부부 공동 자산: 마지막 생존자까지). 건보 산정에서는 제외 ---
        private_pension = 0.0
        if pp_bal > 0:
            pp_bal *= (1.0 + pp_r)
            if (h_alive or w_alive) and pp_start_m <= m < pp_start_m + pp_n:
                if pp_annual <= tx.private_separate_limit:
                    pr = (tx.private_tax_under70 if h_age < 70 else
                          tx.private_tax_70s if h_age < 80 else tx.private_tax_80plus)
                else:
                    pr = tx.private_tax_over_limit
                pay = min(pp_pmt, pp_bal)
                pp_bal -= pay
                private_pension = pay * (1.0 - pr)

        # 실제 손에 쥐는 총수입(실수령 연금 + 기초연금 + 주택연금 + 기타소득 + 개인·퇴직연금).
        income = net_taxable + basic_pension + house_income + other_income + private_pension

        # --- 4) 생활비(물가상승 반영) ---
        both_alive = h_alive and w_alive
        base_expense = user.living_expense_monthly * ((1.0 + strat.inflation_rate) ** year_idx)
        expense = base_expense if both_alive else base_expense * user.single_expense_ratio

        # --- 5) 순현금흐름과 자산 갱신 ---
        net = income - expense
        rm = r_invest if r_invest is not None else monthly_rates[year_idx]
        assets = assets * (1.0 + rm) + net  # 월 투자수익 반영 후 순현금 반영

        shortfall = 0.0
        if assets < 0:
            shortfall = -assets
            assets = 0.0
            if depletion_age is None:
                depletion_age = round(h_age, 1)

        # 연말 자산 스냅샷(몬테카를로 팬차트용, 표 생성과 무관하게 항상 수집).
        if (m + 1) % 12 == 0:
            assets_yearly.append(assets)

        # --- 지표 누적 (실수령 기준) ---
        total_nominal += income
        total_pv += income * (disc_base ** (-m))
        if shortfall > 0:
            shortfall_total += shortfall
            shortfall_months += 1
            if shortfall > worst_shortfall:
                worst_shortfall = shortfall
        if not both_alive:
            if not has_single or net < survivor_min_net:
                survivor_min_net = net
                has_single = True

        if record:
            rows.append({
                "month": m,
                "husband_age": round(h_age, 2), "wife_age": round(w_age, 2),
                "h_pension": h_pension, "w_pension": w_pension,
                "survivor_pension": survivor_extra, "basic_pension": basic_pension,
                "net_taxable": net_taxable, "house_income": house_income, "health": health,
                "other_income": other_income, "private_pension": private_pension,
                "income": income, "expense": expense, "net": net,
                "assets": assets, "shortfall": shortfall, "both_alive": both_alive,
            })

    # 사망시점 예상 잔여자산(=최종 금융자산 + 주택가치).
    # 주택연금을 쓰면 주택은 대출상환에 소진된다고 가정하여 상속가치에서 제외.
    sim_years = total_months // 12
    house_bequest = 0.0 if strat.use_housing else hp.house_value_at(user.house_value, sim_years, cfg.housing)
    # 기타 재산도 상속에 포함(주택가격 상승률로 성장 가정).
    other_bequest = hp.house_value_at(user.other_property, sim_years, cfg.housing)

    metrics = {
        "total_nominal": total_nominal,
        "total_pv": total_pv,
        "shortfall_total": shortfall_total,
        "shortfall_months": shortfall_months,
        "worst_shortfall": worst_shortfall,
        "depletion_age": depletion_age,
        "bequest": assets + house_bequest + other_bequest + max(0.0, pp_bal),   # 남은 개인연금 적립금도 상속
        "survivor_min_net": survivor_min_net,
        "final_assets": assets,
        "house_bequest": house_bequest,
        "assets_yearly": assets_yearly,
        "start_age_h": start_age_h,
        "health_total": health_total,
        "dep_lost_age": dep_lost_age,
        "dep_lost_premium": dep_lost_premium,
    }
    frame = pd.DataFrame(rows) if record else pd.DataFrame()
    return Scenario(strategy=strat, frame=frame, metrics=metrics)


def build_strategy_from_user(user: UserInput, cfg: Config) -> Strategy:
    """
    사용자가 명시적으로 값을 지정한 경우(수령나이 등) 그 값으로 단일 전략을 만든다.
    None 인 항목은 합리적 기본값으로 채운다(정상개시연령 등).
    """
    h_normal = pension.normal_start_age(user.husband, cfg)
    w_normal = pension.normal_start_age(user.wife, cfg)
    return Strategy(
        husband_claim_age=user.husband.nps_claim_age or h_normal,
        wife_claim_age=user.wife.nps_claim_age or w_normal,
        housing_start_age=user.housing_start_age or housing_min_start(user, cfg),
        use_housing=user.use_housing_pension,
        use_chunap=(user.husband.chunap_years > 0 or user.wife.chunap_years > 0),
        use_voluntary=(user.husband.voluntary_years > 0 or user.wife.voluntary_years > 0),
        inflation_rate=user.inflation_rate,
        husband_life=user.husband_life_expectancy,
        wife_life=user.wife_life_expectancy,
    )
