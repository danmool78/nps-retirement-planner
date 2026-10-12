"""
policy.py
=========
제도 파라미터(보험료율·기준소득월액 상한·기초연금액·선정기준액·주택연금 상한 등)를
policy.json 의 '시행일별 이력'에서 읽어, 오늘 날짜에 맞는 값을 자동으로 고른다.

자동 업데이트 구조
- policy.json 에 앞으로 시행될 값까지 미리 적어두면 시행일이 되는 순간 자동으로 바뀐다.
  (예: 국민연금 보험료율 2026 9.5% → 2027 10% … 2033 13%)
- 앱은 접속할 때마다 policy.json 을 새로 읽으므로, 이 파일만 갱신(push)하면
  모든 사용자 화면에 즉시 반영된다(재배포·코드 수정 불필요).
- 갱신 주기(revises)가 지났는데 새 값이 없는 항목은 overdue() 로 잡아내어
  화면에 '확인 필요'로 표시하고, GitHub Actions(.github/workflows/policy-check.yml)가
  매월 점검해 이슈를 자동으로 올린다.
"""

from __future__ import annotations

import json
import os
from datetime import date

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "policy.json")


def load(path: str = _PATH) -> dict:
    """policy.json 을 읽는다. 없거나 깨졌으면 빈 dict(→ config.py 기본값 사용)."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _d(s: str) -> date:
    return date.fromisoformat(s)


def _entry_at(param: dict, today: date):
    """이력 중 today 기준 시행 중인 항목(시행일이 today 이하인 것 중 가장 최근)."""
    hist = sorted(param.get("history", []), key=lambda e: e["from"])
    cur = None
    for e in hist:
        if _d(e["from"]) <= today:
            cur = e
    return cur


def current(data: dict | None = None, today: date | None = None) -> dict:
    """{키: 값} — 오늘 시행 중인 값. 이력이 없는 키는 빠진다(호출측이 기본값 사용)."""
    data = load() if data is None else data
    today = today or date.today()
    out = {}
    for key, param in data.get("params", {}).items():
        e = _entry_at(param, today)
        if e is not None:
            out[key] = e["value"]
    return out


def describe(data: dict | None = None, today: date | None = None) -> list:
    """화면 표시용: [(라벨, 값 문자열, 시행일, 다음 변경 문자열 또는 '')]"""
    data = load() if data is None else data
    today = today or date.today()
    rows = []
    for key, param in data.get("params", {}).items():
        e = _entry_at(param, today)
        if e is None or isinstance(e["value"], list):
            continue
        nxt = [x for x in sorted(param["history"], key=lambda x: x["from"]) if _d(x["from"]) > today]
        nxt_txt = f"{nxt[0]['from']}부터 {format_value(param, nxt[0]['value'])}" if nxt else ""
        rows.append((param.get("label", key), format_value(param, e["value"]), e["from"], nxt_txt))
    return rows


def format_value(param: dict, v) -> str:
    unit = param.get("unit", "")
    if unit == "%":
        return f"{v * 100:g}%"
    if unit == "원":
        return f"{v:,.0f}원"
    return f"{v}{unit}"


def _expected_since(revises: str, today: date):
    """갱신 주기상 '이 날짜 이후 시행 항목이 있어야 하는' 기준일. 주기가 없으면 None."""
    if revises == "annual-01":
        return date(today.year, 1, 1)
    if revises == "annual-04":
        return date(today.year if today.month >= 4 else today.year - 1, 4, 1)
    if revises == "annual-07":
        return date(today.year if today.month >= 7 else today.year - 1, 7, 1)
    return None


def overdue(data: dict | None = None, today: date | None = None) -> list:
    """갱신 주기가 지났는데 새 값이 들어오지 않은 항목 라벨 목록."""
    data = load() if data is None else data
    today = today or date.today()
    late = []
    for key, param in data.get("params", {}).items():
        since = _expected_since(param.get("revises", ""), today)
        if since is None:
            continue
        e = _entry_at(param, today)
        if e is None or _d(e["from"]) < since:
            late.append(param.get("label", key))
    return late


def as_of(data: dict | None = None) -> str:
    data = load() if data is None else data
    return data.get("updated", "")
