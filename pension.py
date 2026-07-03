"""
pension.py
==========
연금 종류(국민연금 / 교직원연금)에 따라 알맞은 계산 모듈과 정책 객체를 골라주는
디스패처(dispatcher). nps.py 와 teacher_pension.py 는 동일한 함수 시그니처를 제공하므로,
호출부(cashflow/optimizer)는 이 헬퍼로 (모듈, 정책)을 받아 그대로 사용하면 된다.

새로운 연금 제도(예: 공무원연금, 군인연금)를 추가할 때도 여기 한 곳만 확장하면 된다.
"""

from __future__ import annotations

import nps
import teacher_pension
from config import Config, Person


def resolve(person: Person, cfg: Config):
    """
    사람의 pension_type 에 맞는 (계산모듈, 정책객체) 튜플을 반환.

    - "teacher" : 교직원연금(사학연금)
    - 그 외/기본 : 국민연금
    """
    if getattr(person, "pension_type", "nps") == "teacher":
        return teacher_pension, cfg.teacher
    return nps, cfg.nps


def normal_start_age(person: Person, cfg: Config) -> int:
    """사람의 연금 제도에 맞는 정상 지급개시연령."""
    module, policy = resolve(person, cfg)
    return module.normal_start_age(person.birth_year, policy)


def type_label(person: Person) -> str:
    """표시용 한글 라벨."""
    return "교직원연금" if getattr(person, "pension_type", "nps") == "teacher" else "국민연금"
