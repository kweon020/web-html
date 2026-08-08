"""합성 OHLCV 생성기.

네트워크 없이 엔진을 테스트하고, 전략이 '아무 데이터에서나' 안 터지는지 확인하는 용도.
실제 시세가 아니므로 여기서 나온 수익률에는 아무 의미가 없다.
엔진이 올바르게 도는지만 본다.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def make_ohlcv(
    bars: int = 500,
    start: str = "2023-01-01",
    freq: str = "1D",
    start_price: float = 50_000_000.0,
    drift: float = 0.0003,
    volatility: float = 0.025,
    seed: int = 42,
) -> pd.DataFrame:
    """기하 브라운 운동으로 그럴듯한 OHLCV를 만든다.

    drift/volatility는 봉 단위 기준이다.
    """
    rng = np.random.default_rng(seed)

    # 종가 경로: 로그수익률 누적
    log_returns = rng.normal(loc=drift, scale=volatility, size=bars)
    close = start_price * np.exp(np.cumsum(log_returns))

    # 시가는 직전 종가에서 약간 갭
    open_ = np.empty(bars)
    open_[0] = start_price
    open_[1:] = close[:-1] * (1.0 + rng.normal(0.0, volatility * 0.15, bars - 1))

    # 고가/저가는 시가·종가를 감싸도록 만든다
    body_high = np.maximum(open_, close)
    body_low = np.minimum(open_, close)
    high = body_high * (1.0 + np.abs(rng.normal(0.0, volatility * 0.4, bars)))
    low = body_low * (1.0 - np.abs(rng.normal(0.0, volatility * 0.4, bars)))

    volume = rng.lognormal(mean=3.0, sigma=0.6, size=bars)

    index = pd.date_range(start=start, periods=bars, freq=freq, name="timestamp")
    df = pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=index,
    )

    # OHLC 정합성은 반드시 지켜져야 한다 (백테스트 체결 로직이 이걸 신뢰한다)
    df["high"] = df[["open", "high", "low", "close"]].max(axis=1)
    df["low"] = df[["open", "high", "low", "close"]].min(axis=1)
    return df


def make_trending(bars: int = 300, seed: int = 7, **kwargs) -> pd.DataFrame:
    """뚜렷한 상승 추세. 추세추종 전략이 돈을 벌어야 정상인 구간."""
    return make_ohlcv(bars=bars, drift=0.004, volatility=0.015, seed=seed, **kwargs)


def make_choppy(bars: int = 300, seed: int = 11, **kwargs) -> pd.DataFrame:
    """방향 없이 흔들리는 구간. 추세추종이 수수료로 갉아먹혀야 정상."""
    return make_ohlcv(bars=bars, drift=0.0, volatility=0.03, seed=seed, **kwargs)
