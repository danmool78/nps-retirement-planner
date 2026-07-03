"""
gov_pension.py
==============
공무원연금 월수령액 계산 모듈.

공무원연금은 사학연금(교직원연금)과 산식이 동일하므로(사학연금이 공무원연금을 준용),
계산 로직은 teacher_pension.py 를 그대로 재사용한다. 정책 파라미터만 GovPolicy 로 분리하여
향후 두 제도가 갈라지면 이 모듈에서 독립적으로 오버라이드할 수 있다.

nps.py / teacher_pension.py 와 동일한 함수 시그니처를 제공하여 pension.py 디스패처가
모듈만 바꿔 끼울 수 있게 한다.
"""

from __future__ import annotations

import teacher_pension as _db  # 확정급여형(직역연금) 공통 계산 로직

# 계산식이 사학연금과 동일하므로 함수를 그대로 재노출한다.
# (인자로 받는 policy 는 GovPolicy 이며, TeacherPolicy 와 동일한 필드를 갖는다.)
normal_start_age = _db.normal_start_age
claim_factor = _db.claim_factor
monthly_pension = _db.monthly_pension
indexed_monthly_pension = _db.indexed_monthly_pension
total_nominal_receipts = _db.total_nominal_receipts
