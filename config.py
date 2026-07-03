"""
config.py
=========
부부 노후자금 계획 시뮬레이터의 '제도 파라미터'와 '사용자 입력값'을 정의하는 모듈.

설계 원칙
---------
- 감액률, 가산률, 물가상승률, 지급개시연령, 보험료율 등 '제도 기준'은 향후 법령 개정으로
  얼마든지 바뀔 수 있다. 따라서 코드에 하드코딩하지 않고 모두 이 파일의 dataclass 기본값으로
  모아 둔다. Streamlit 화면(app.py)에서 사용자가 이 값들을 실시간으로 덮어쓸 수 있다.
- dataclass 를 사용해 (1) 기본값 제공, (2) 타입 명시, (3) 손쉬운 복제/수정을 가능하게 한다.

용어
----
- 국민연금(NPS)          : National Pension Service. 노령연금.
- 조기(노령)연금          : 최대 5년 앞당겨 수령. 1년당 6%(월 0.5%) 감액.
- 연기(노령)연금          : 최대 5년 늦춰 수령. 1년당 7.2%(월 0.6%) 가산.
- 추납(추후납부)          : 과거 미납/납부예외 기간을 나중에 납부하여 가입기간을 늘림.
- 임의가입                : 의무가입 대상이 아닌 사람이 자발적으로 가입.
- 주택연금                : 주택을 담보로 매월 연금을 받는 역모기지(한국주택금융공사).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, List


# ---------------------------------------------------------------------------
# 1. 제도(국민연금) 파라미터
# ---------------------------------------------------------------------------
@dataclass
class NpsPolicy:
    """국민연금 관련 제도 파라미터. 전부 화면에서 수정 가능."""

    # 조기수령 감액률(월 기준). 연 6% == 월 0.5%.
    early_monthly_reduction: float = 0.005
    # 연기수령 가산률(월 기준). 연 7.2% == 월 0.6%.
    defer_monthly_increase: float = 0.006
    # 조기/연기 허용 최대 연수(제도상 각각 5년).
    max_early_years: int = 5
    max_defer_years: int = 5

    # 출생연도 -> 정상 지급개시연령 구간표.
    # (하한 출생연도, 개시연령) 형태의 리스트. birth_year 가 크거나 같은 마지막 구간을 적용.
    # 2033년 이후 65세로 단계적 상향된 현행 기준.
    start_age_table: List[tuple] = field(
        default_factory=lambda: [
            (0, 60),      # ~1952년생
            (1953, 61),   # 1953~1956
            (1957, 62),   # 1957~1960
            (1961, 63),   # 1961~1964
            (1965, 64),   # 1965~1968
            (1969, 65),   # 1969년생 이후
        ]
    )

    # 추납: 추납 1년(12개월)당 월연금이 증가하는 비율(가입기간 증가 근사치).
    # 실제로는 소득대체율·가입기간에 따라 달라지므로 근사 파라미터로 두고 수정 가능하게 함.
    chunap_monthly_gain_per_year: float = 0.05
    # 임의가입: 가입 연수 1년당 월연금 증가 비율(근사치).
    voluntary_monthly_gain_per_year: float = 0.05

    # 국민연금은 매년 전년도 전국소비자물가변동률만큼 연금액이 인상(물가연동)된다.
    # True 이면 시뮬레이션에서 물가상승률을 연금액에 반영한다.
    inflation_indexed: bool = True

    # 유족연금 지급률(사망 배우자 기본연금액 대비). 가입기간에 따라 40~60%.
    survivor_pension_rate: float = 0.60


# ---------------------------------------------------------------------------
# 2. 제도(주택연금) 파라미터
# ---------------------------------------------------------------------------
@dataclass
class HousingPolicy:
    """주택연금(역모기지) 관련 제도 파라미터."""

    # 주택연금은 '가입 시점 연령'이 높을수록 월지급금이 커진다.
    # 사용자가 입력하는 '기준 월지급액'은 base_age 기준이라고 가정하고,
    # 개시나이가 base_age 에서 1세 달라질 때마다 age_factor_per_year 만큼 조정한다.
    base_age: int = 60
    age_factor_per_year: float = 0.06  # 1세 늦출수록 월지급액 약 +6% (근사, 수정 가능)

    # 주택연금 개시 가능 최소 연령(현행 55세).
    min_start_age: int = 55

    # 주택연금(종신 정액형)은 명목상 정액. 물가에 연동되지 않음(기본 False).
    inflation_indexed: bool = False

    # 주택가격은 연 house_growth_rate 로 상승한다고 가정(잔여자산·상속 계산용).
    house_growth_rate: float = 0.01


# ---------------------------------------------------------------------------
# 2-b. 제도(교직원연금 = 사립학교교직원연금/사학연금) 파라미터
# ---------------------------------------------------------------------------
@dataclass
class TeacherPolicy:
    """
    교직원연금(사학연금) 관련 제도 파라미터.

    국민연금과의 주요 차이
    - 조기(조기퇴직)연금 감액이 '연 5%' 단위(국민연금은 월 0.5%).
    - 연기수령 가산 제도가 사실상 없음(기본 max_defer_years=0).
    - 지급개시연령이 60→65세로 단계 상향 중(공무원연금과 동일 스케줄).
    - 추납/임의가입 개념은 국민연금 전용이므로 여기서는 사용하지 않음.
    실제 사학연금액은 기준소득월액·재직기간으로 산정되며, 여기서는 국민연금과 동일하게
    '정상개시 예상 월액'을 입력받아 조기감액 배수를 적용하는 근사 모델을 쓴다(모두 수정 가능).
    """

    # 조기퇴직연금 감액률(연 기준). 1년 앞당길 때마다 5% 감액(최대 5년 25%).
    early_yearly_reduction: float = 0.05
    max_early_years: int = 5

    # 연기수령 가산(사학연금은 기본 없음). 필요 시 화면에서 켤 수 있도록 파라미터만 둔다.
    defer_yearly_increase: float = 0.0
    max_defer_years: int = 0

    # 출생연도 -> 정상 지급개시연령 근사표(60→65 단계 상향을 출생연도로 근사).
    # 사학연금 개시연령은 원래 '퇴직연도' 기준이나, 앱 모델 일관성을 위해 출생연도로 근사한다.
    start_age_table: List[tuple] = field(
        default_factory=lambda: [
            (0, 60),
            (1958, 61),
            (1960, 62),
            (1963, 63),
            (1966, 64),
            (1969, 65),
        ]
    )

    # 사학연금도 매년 물가변동률만큼 연금액이 조정된다(물가연동).
    inflation_indexed: bool = True

    # 유족연금 지급률(퇴직연금 대비). 통상 60%.
    survivor_pension_rate: float = 0.60


# ---------------------------------------------------------------------------
# 3. 최적화 파라미터
# ---------------------------------------------------------------------------
@dataclass
class OptimizerConfig:
    """조합 탐색 및 점수화 파라미터."""

    # 현재가치 환산에 쓰는 할인율(실질 시간선호). 물가상승률과 별개로 둔다.
    discount_rate: float = 0.02

    # 탐색할 물가상승률 시나리오(민감도 분석용).
    inflation_scenarios: List[float] = field(default_factory=lambda: [0.01, 0.02, 0.03])

    # 탐색할 기대수명 시나리오.
    life_expectancy_scenarios: List[int] = field(default_factory=lambda: [83, 88, 93])

    # 세 가지 관점별 점수 가중치.
    # 각 관점은 [부족액총합, 부족개월수, 최악부족액, 총수령액PV, 잔여자산] 5개 지표에 대한 가중치.
    # 부족 관련 지표는 '작을수록 좋음'이므로 정규화 시 부호를 반전한다(optimizer.py 참고).
    weights: Dict[str, Dict[str, float]] = field(
        default_factory=lambda: {
            "stable": {       # 안정형: 현금흐름 부족 최소화 우선
                "shortfall_total": 0.35,
                "shortfall_months": 0.25,
                "worst_shortfall": 0.20,
                "total_pv": 0.10,
                "bequest": 0.10,
            },
            "maximize": {     # 총수령액 극대화형
                "shortfall_total": 0.15,
                "shortfall_months": 0.10,
                "worst_shortfall": 0.10,
                "total_pv": 0.50,
                "bequest": 0.15,
            },
            "bequest": {      # 상속중시형
                "shortfall_total": 0.15,
                "shortfall_months": 0.10,
                "worst_shortfall": 0.10,
                "total_pv": 0.15,
                "bequest": 0.50,
            },
        }
    )


# ---------------------------------------------------------------------------
# 4. 사용자(부부) 입력값
# ---------------------------------------------------------------------------
@dataclass
class Person:
    """부부 중 한 사람의 입력 정보."""

    label: str                 # '남편' / '아내' 등 표시용 라벨
    birth_year: int            # 출생연도
    birth_month: int = 1       # 출생월(월 단위 시뮬레이션 정밀도용)
    nps_monthly: float = 0.0   # 정상개시연령 기준 연금 예상 월수령액(원)

    # 연금 종류: "nps"(국민연금) 또는 "teacher"(교직원연금/사학연금).
    # 부부가 서로 다른 제도일 수 있으므로 사람 단위로 지정한다.
    pension_type: str = "nps"

    # 지금까지 납입한 총 보험료(원). '원금확보(손익분기) 시점' 계산에 사용.
    # 누적 연금수령액이 이 금액을 넘어서는 나이가 원금 회수 시점이 된다.
    paid_principal: float = 0.0

    # 연금 수령개시나이(사용자 지정). None 이면 optimizer 가 탐색.
    nps_claim_age: int | None = None

    # 추납 가능기간(년)과 추납 총비용(원). 추납을 선택하면 비용을 금융자산에서 차감.
    chunap_years: int = 0
    chunap_cost: float = 0.0

    # 임의가입 연수와 총비용(원).
    voluntary_years: int = 0
    voluntary_cost: float = 0.0


@dataclass
class UserInput:
    """시뮬레이션 전체 입력값(부부 공통 항목 포함)."""

    husband: Person
    wife: Person

    # 은퇴 후 부부 합산 월 생활비(현재가치, 원).
    living_expense_monthly: float = 3_000_000

    # 배우자 단독 생존 시 생활비 비율(1인 가구는 보통 부부의 60~70%).
    single_expense_ratio: float = 0.65

    # 금융자산(현재 보유, 원)과 기대 연 투자수익률.
    financial_assets: float = 200_000_000
    investment_return: float = 0.03

    # 물가상승률(기본 시나리오). 민감도 분석은 OptimizerConfig 에서 별도 탐색.
    inflation_rate: float = 0.02

    # 기대수명(부부 각자). 시뮬레이션 종료 시점 결정.
    husband_life_expectancy: int = 86
    wife_life_expectancy: int = 90

    # 주택 관련.
    house_value: float = 500_000_000          # 현재 주택가격(원)
    housing_monthly_base: float = 1_200_000    # HousingPolicy.base_age 기준 월지급액
    housing_start_age: int | None = None       # 주택연금 개시나이(남편 기준). None 이면 탐색.
    use_housing_pension: bool = True           # 주택연금 사용 여부

    # 상속 선호도(0=현금흐름 우선 ~ 1=상속 우선). 관점 선택과 별개로 미세조정에 사용.
    bequest_preference: float = 0.3

    # 시뮬레이션 시작 나이(남편 기준 은퇴 나이).
    retirement_age: int = 60


@dataclass
class Config:
    """모든 파라미터 묶음. app.py 에서 이 객체 하나만 주고받는다."""

    nps: NpsPolicy = field(default_factory=NpsPolicy)
    teacher: TeacherPolicy = field(default_factory=TeacherPolicy)
    housing: HousingPolicy = field(default_factory=HousingPolicy)
    optimizer: OptimizerConfig = field(default_factory=OptimizerConfig)


def default_config() -> Config:
    """기본 제도 파라미터 묶음을 생성."""
    return Config()


def default_user_input() -> UserInput:
    """데모/초기 화면용 기본 사용자 입력값."""
    return UserInput(
        husband=Person(label="남편", birth_year=1965, nps_monthly=1_100_000),
        wife=Person(label="아내", birth_year=1967, nps_monthly=700_000),
    )


def clone_with(obj, **changes):
    """dataclass 를 불변처럼 다루기 위한 헬퍼(부분 수정 복제)."""
    return replace(obj, **changes)
