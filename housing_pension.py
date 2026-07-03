"""
housing_pension.py
==================
주택연금(역모기지) 월지급액 및 주택가치 계산 모듈.

핵심 함수
- monthly_payment()   : 개시나이·주택가격에 따른 월지급액
- house_value_at()    : 특정 나이 시점의 주택 평가액(상속/잔여자산 계산용)

주택연금(종신 정액형) 특징
- 가입 연령이 높을수록 월지급금이 커진다.
- 한 번 산정되면 명목상 정액(물가 미연동, 기본값)이다.
- 사용자가 입력한 '기준 월지급액'은 HousingPolicy.base_age 기준으로 가정하고,
  개시나이 차이에 age_factor_per_year 를 적용해 근사한다.

실제 월지급금은 주택가격·연령·기대이율·주택가격상승률을 반영한 공사(HF) 산식으로 정해진다.
정확한 값은 공사 계산기를 참고해야 하며, 여기서는 근사 모델을 쓰되 계수를 config 로 조정 가능하게 둔다.
"""

from __future__ import annotations

from config import HousingPolicy


def is_eligible(start_age: int, policy: HousingPolicy) -> bool:
    """주택연금 가입 가능 연령(최소 연령) 충족 여부."""
    return start_age >= policy.min_start_age


def monthly_payment(
    housing_monthly_base: float,
    start_age: int,
    policy: HousingPolicy,
) -> float:
    """
    주택연금 개시나이에 따른 월지급액(근사).

    월지급액 = 기준월지급액 × (1 + age_factor_per_year)^(개시나이 - 기준나이)

    - 개시나이가 기준나이보다 많으면 증액, 적으면 감액된다.
    - 최소 가입연령 미만이면 0 을 반환(수급 불가).
    """
    if not is_eligible(start_age, policy):
        return 0.0
    age_diff = start_age - policy.base_age
    return housing_monthly_base * ((1.0 + policy.age_factor_per_year) ** age_diff)


def indexed_monthly_payment(
    base_monthly: float,
    years_since_start: int,
    inflation_rate: float,
    policy: HousingPolicy,
) -> float:
    """
    주택연금 월지급액의 경과연수 반영값.

    종신 정액형은 명목 고정이 기본(policy.inflation_indexed=False).
    물가연동형 옵션을 켜면 물가상승률을 반영한다.
    """
    if not policy.inflation_indexed:
        return base_monthly
    return base_monthly * ((1.0 + inflation_rate) ** years_since_start)


def house_value_at(
    current_house_value: float,
    years_from_now: int,
    policy: HousingPolicy,
) -> float:
    """
    현재로부터 years_from_now 년 뒤 주택 평가액.

    상속/사망시점 잔여자산 계산에 사용. 연 house_growth_rate 로 복리 상승 가정.
    """
    return current_house_value * ((1.0 + policy.house_growth_rate) ** years_from_now)


def total_nominal_receipts(
    housing_monthly_base: float,
    start_age: int,
    end_age: int,
    inflation_rate: float,
    policy: HousingPolicy,
) -> float:
    """개시나이부터 end_age 까지 받는 주택연금 명목 총수령액."""
    base = monthly_payment(housing_monthly_base, start_age, policy)
    if base <= 0:
        return 0.0
    total = 0.0
    for y in range(0, max(0, end_age - start_age)):
        monthly = indexed_monthly_payment(base, y, inflation_rate, policy)
        total += monthly * 12
    return total
