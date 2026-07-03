"""
teacher_pension.py
==================
교직원연금(사립학교교직원연금 = 사학연금) 월수령액 계산 모듈.

nps.py 와 '동일한 함수 시그니처'를 제공하여 cashflow/optimizer 에서 연금 종류에 따라
모듈만 바꿔 끼울 수 있게 한다(덕 타이핑 기반 디스패치).

국민연금과의 차이(계산에 반영되는 부분)
- 조기퇴직연금 감액이 '연 5%' 단위(국민연금은 월 0.5%).
- 연기수령 가산은 기본 없음(정책 파라미터로 켤 수는 있음).
- 지급개시연령 60→65세 단계 상향.
- 추납/임의가입 없음 → 관련 인자는 받되 무시한다.
"""

from __future__ import annotations

from config import TeacherPolicy, Person


def normal_start_age(birth_year: int, policy: TeacherPolicy) -> int:
    """출생연도에 해당하는 사학연금 정상 지급개시연령(근사표 기반)."""
    age = policy.start_age_table[0][1]
    for lower_year, start_age in policy.start_age_table:
        if birth_year >= lower_year:
            age = start_age
        else:
            break
    return age


def claim_factor(claim_age: int, normal_age: int, policy: TeacherPolicy) -> float:
    """
    수령개시나이에 따른 감액/가산 배수.

    - 조기: (정상-개시)년 × 연 5% 감액(최대 5년).
    - 연기: (개시-정상)년 × defer_yearly_increase(기본 0 → 가산 없음, 최대 max_defer_years).
    """
    diff_years = claim_age - normal_age

    if diff_years < 0:  # 조기퇴직연금
        early_years = min(-diff_years, policy.max_early_years)
        return 1.0 - early_years * policy.early_yearly_reduction

    if diff_years > 0:  # 연기(사학연금은 기본 가산 없음)
        defer_years = min(diff_years, policy.max_defer_years)
        return 1.0 + defer_years * policy.defer_yearly_increase

    return 1.0


def monthly_pension(
    person: Person,
    claim_age: int,
    policy: TeacherPolicy,
    use_chunap: bool = False,      # 사학연금엔 없음. 시그니처 통일을 위해 받되 무시.
    use_voluntary: bool = False,   # 동일.
) -> float:
    """
    사학연금 '개시 시점' 월수령액(명목, 물가연동 전).

    최종 월수령액 = 정상개시 예상액 × 조기/연기 배수.
    (추납/임의가입 배수는 적용하지 않는다.)
    """
    normal_age = normal_start_age(person.birth_year, policy)
    factor = claim_factor(claim_age, normal_age, policy)
    return person.nps_monthly * factor


def indexed_monthly_pension(
    base_monthly: float,
    years_since_claim: int,
    inflation_rate: float,
    policy: TeacherPolicy,
) -> float:
    """개시 후 경과 연수만큼 물가연동된 월수령액."""
    if not policy.inflation_indexed:
        return base_monthly
    return base_monthly * ((1.0 + inflation_rate) ** years_since_claim)


def total_nominal_receipts(
    person: Person,
    claim_age: int,
    death_age: int,
    inflation_rate: float,
    policy: TeacherPolicy,
    use_chunap: bool = False,
    use_voluntary: bool = False,
) -> float:
    """개시나이부터 사망나이까지 받는 사학연금 명목 총수령액."""
    base = monthly_pension(person, claim_age, policy)
    total = 0.0
    for y in range(0, max(0, death_age - claim_age)):
        total += indexed_monthly_pension(base, y, inflation_rate, policy) * 12
    return total
