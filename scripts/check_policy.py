"""
check_policy.py
===============
policy.json 점검 스크립트(GitHub Actions 에서 매월 실행, 로컬에서도 실행 가능).

1) 형식 검사: 모든 항목에 label·history 가 있고, 시행일(from)이 올바른 날짜인지.
2) 갱신 지연 검사: 정기 갱신 항목(매년 1월/7월)이 시기가 지났는데 새 값이 없으면 목록 출력.
3) 30일 내 시행 예정 항목 안내.

결과는 마크다운으로 stdout 에 출력하고, 갱신 지연이 있으면 종료코드 1
(워크플로가 이를 보고 '제도 파라미터 갱신 필요' 이슈를 만든다).
실행:  python scripts/check_policy.py
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import policy  # noqa: E402


def main() -> int:
    data = policy.load()
    if not data.get("params"):
        print("policy.json 을 읽을 수 없거나 params 가 비어 있습니다.")
        return 2

    errors = []
    for key, p in data["params"].items():
        if "label" not in p or not p.get("history"):
            errors.append(f"`{key}`: label 또는 history 누락")
            continue
        for e in p["history"]:
            try:
                date.fromisoformat(e["from"])
            except (KeyError, ValueError):
                errors.append(f"`{key}`: 잘못된 시행일 {e.get('from')!r}")
            if "value" not in e:
                errors.append(f"`{key}`: value 누락")
    if errors:
        print("## policy.json 형식 오류\n")
        print("\n".join(f"- {x}" for x in errors))
        return 2

    today = date.today()
    late = policy.overdue(data, today)
    soon = []
    for key, p in data["params"].items():
        for e in p["history"]:
            d = date.fromisoformat(e["from"])
            if today < d <= today + timedelta(days=30) and not isinstance(e["value"], list):
                soon.append(f"- {p['label']}: {d} 부터 {policy.format_value(p, e['value'])}")

    print(f"# 제도 파라미터 점검 ({today})\n")
    print(f"데이터 갱신일: {data.get('updated', '-')}\n")
    if late:
        print("## 갱신 필요\n")
        print("정기 갱신 시기가 지났지만 policy.json 에 새 시행값이 없습니다. "
              "보건복지부·국민연금공단 고시를 확인해 history 에 추가해 주세요.\n")
        print("\n".join(f"- {x}" for x in late))
        print()
    if soon:
        print("## 30일 내 자동 적용 예정\n")
        print("\n".join(soon))
        print()
    if not late:
        print("갱신이 필요한 항목이 없습니다.")
    return 1 if late else 0


if __name__ == "__main__":
    sys.exit(main())
