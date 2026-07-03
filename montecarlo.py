"""
montecarlo.py
=============
투자수익 변동성(시퀀스 리스크) 몬테카를로 스트레스 모듈.

고정 수익률 가정은 '은퇴 초반 폭락'의 위험(sequence-of-returns risk)을 못 본다.
여기서는 하나의 추천 전략에 대해 수백 개의 무작위 연수익률 경로를 생성해 시뮬레이션하고,
- 성공확률(부족 없이 버틸 확률)
- 자산 분위수(p10/p50/p90) 궤적(팬차트)
- 상속(잔여자산) 분포, 자산고갈 확률
을 산출한다. 전 조합이 아니라 '추천 전략 1개'에만 적용하므로 비용이 크지 않다.
"""

from __future__ import annotations

import numpy as np

from cashflow import Strategy, simulate
from config import Config, UserInput


def run(user: UserInput, strat: Strategy, cfg: Config,
        volatility: float, n_sims: int = 400, seed: int = 42) -> dict:
    """
    추천 전략에 대해 무작위 수익률 경로 n_sims 개를 시뮬레이션하고 통계를 반환.

    연수익률 ~ Normal(mean=user.investment_return, std=volatility), 연 단위로 독립 추출.
    (음수 수익률도 허용 → 폭락장 포함. 극단 방지를 위해 -90% 하한만 클립.)
    """
    rng = np.random.default_rng(seed)
    mean = user.investment_return

    # 시뮬레이션 총 연수(전략의 사망시점 기준)를 한 번 돌려 파악.
    base = simulate(user, strat, cfg, record=False)
    n_years = len(base.metrics["assets_yearly"])
    start_age_h = base.metrics["start_age_h"]

    shortfalls, bequests, depletions = [], [], []
    paths = np.empty((n_sims, n_years), dtype=float)

    for i in range(n_sims):
        ann = np.clip(rng.normal(mean, volatility, size=n_years), -0.9, None)
        m = simulate(user, strat, cfg, record=False, annual_returns=ann).metrics
        shortfalls.append(m["shortfall_total"])
        bequests.append(m["bequest"])
        depletions.append(m["depletion_age"] is not None)
        ay = m["assets_yearly"]
        # 길이 보정(사망시점 동일하므로 대개 일치하지만 안전하게 맞춘다).
        paths[i, :len(ay)] = ay[:n_years]
        if len(ay) < n_years:
            paths[i, len(ay):] = ay[-1] if ay else 0.0

    shortfalls = np.array(shortfalls)
    bequests = np.array(bequests)
    ages = [start_age_h + (k + 1) for k in range(n_years)]

    return {
        "n_sims": n_sims,
        "volatility": volatility,
        "success_rate": float(np.mean(shortfalls <= 0)),        # 부족 없이 버틸 확률
        "depletion_rate": float(np.mean(depletions)),           # 자산 고갈 확률
        "ages": ages,
        "assets_p10": np.percentile(paths, 10, axis=0).tolist(),
        "assets_p50": np.percentile(paths, 50, axis=0).tolist(),
        "assets_p90": np.percentile(paths, 90, axis=0).tolist(),
        "bequest_p10": float(np.percentile(bequests, 10)),
        "bequest_p50": float(np.percentile(bequests, 50)),
        "bequest_p90": float(np.percentile(bequests, 90)),
        "worst_shortfall_total": float(shortfalls.max()),       # 최악 경로 부족액
    }
