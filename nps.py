"""
nps.py
======
국민연금(노령연금) 월수령액 계산 모듈.

계산식은 함수 단위로 분리한다.
- normal_start_age()        : 출생연도별 정상 지급개시연령
- claim_factor()            : 조기/연기 수령에 따른 감액/가산 배수
- chunap_gain() / voluntary_gain() : 추납·임의가입에 따른 연금 증가 배수
- monthly_pension()         : 위 요소를 합성한 최종 월수령액
- annual_pension_at()       : 특정 연차의 연간 수령액(물가연동 반영)

주의: 실제 국민연금액은 A값·B값·소득대체율·가입기간 등 복잡한 산식으로 결정된다.
이 모듈은 '사용자가 입력한 정상개시연령 기준 예상액'을 출발점으로 삼아,
조기/연기/추납/임의가입 효과를 배수로 근사한다. 세부 산식은 향후 확장 지점(TODO)으로 둔다.
"""

from __future__ import annotations

from config import NpsPolicy, Person


def normal_start_age(birth_year: int, policy: NpsPolicy) -> int:
    """
    출생연도에 해당하는 국민연금 정상 지급개시연령을 반환.

    policy.start_age_table 은 (하한출생연도, 개시연령) 오름차순 리스트.
    birth_year 이상인 마지막 구간의 개시연령을 적용한다.
    """
    age = policy.start_age_table[0][1]
    for lower_year, start_age in policy.start_age_table:
        if birth_year >= lower_year:
            age = start_age
        else:
            break
    return age


def claim_factor(claim_age: int, normal_age: int, policy: NpsPolicy) -> float:
    """
    수령개시나이에 따른 감액/가산 배수를 계산.

    - claim_age < normal_age : 조기수령. (normal-claim)개월*월감액률 만큼 감액.
    - claim_age > normal_age : 연기수령. (claim-normal)개월*월가산률 만큼 가산.
    - 조기/연기 모두 최대 연수(policy.max_early_years / max_defer_years)로 제한.

    반환: 정상연금 대비 배수(예: 0.70 = 30% 감액, 1.36 = 36% 가산).
    """
    diff_years = claim_age - normal_age

    if diff_years < 0:  # 조기수령
        early_years = min(-diff_years, policy.max_early_years)
        months = early_years * 12
        return 1.0 - months * policy.early_monthly_reduction

    if diff_years > 0:  # 연기수령
        defer_years = min(diff_years, policy.max_defer_years)
        months = defer_years * 12
        return 1.0 + months * policy.defer_monthly_increase

    return 1.0  # 정상 개시


def chunap_gain(chunap_years: int, policy: NpsPolicy) -> float:
    """추납 연수에 따른 연금 증가 배수(근사). TODO: 실제 가입기간 재산정으로 확장."""
    return 1.0 + chunap_years * policy.chunap_monthly_gain_per_year


def voluntary_gain(voluntary_years: int, policy: NpsPolicy) -> float:
    """임의가입 연수에 따른 연금 증가 배수(근사)."""
    return 1.0 + voluntary_years * policy.voluntary_monthly_gain_per_year


def monthly_pension(
    person: Person,
    claim_age: int,
    policy: NpsPolicy,
    use_chunap: bool = False,
    use_voluntary: bool = False,
) -> float:
    """
    한 사람의 국민연금 '개시 시점' 월수령액(명목, 물가연동 전)을 계산.

    최종 월수령액 = 정상예상액
                    × 조기/연기 배수
                    × (추납 배수)
                    × (임의가입 배수)
    """
    normal_age = normal_start_age(person.birth_year, policy)
    factor = claim_factor(claim_age, normal_age, policy)

    amount = person.nps_monthly * factor
    if use_chunap and person.chunap_years > 0:
        amount *= chunap_gain(person.chunap_years, policy)
    if use_voluntary and person.voluntary_years > 0:
        amount *= voluntary_gain(person.voluntary_years, policy)
    return amount


def indexed_monthly_pension(
    base_monthly: float,
    years_since_claim: int,
    inflation_rate: float,
    policy: NpsPolicy,
) -> float:
    """
    개시 후 경과 연수만큼 물가연동된 월수령액을 반환.

    국민연금은 매년 물가상승률만큼 인상되므로 개시액에 (1+물가)^경과연수 를 곱한다.
    policy.inflation_indexed 가 False 이면 물가연동을 하지 않는다(명목 고정).
    """
    if not policy.inflation_indexed:
        return base_monthly
    return base_monthly * ((1.0 + inflation_rate) ** years_since_claim)


def total_nominal_receipts(
    person: Person,
    claim_age: int,
    death_age: int,
    inflation_rate: float,
    policy: NpsPolicy,
    use_chunap: bool = False,
    use_voluntary: bool = False,
) -> float:
    """
    개시나이부터 사망나이까지 받는 국민연금 명목 총수령액.

    (물가연동을 반영한 각 연도 수령액의 단순 합)
    """
    base = monthly_pension(person, claim_age, policy, use_chunap, use_voluntary)
    total = 0.0
    for y in range(0, max(0, death_age - claim_age)):
        monthly = indexed_monthly_pension(base, y, inflation_rate, policy)
        total += monthly * 12
    return total
