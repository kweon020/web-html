"""RSI 평균회귀 — 과매도에 사서 회복하면 판다."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..indicators import rsi, sma
from .base import Strategy


class RSIReversionStrategy(Strategy):
    """RSI가 oversold 아래로 내려가면 진입, exit_level 위로 올라오면 청산.

    주의: 평균회귀는 '떨어지는 칼날'을 잡는 구조다.
    추세 하락장에서는 계속 물릴 수 있으니 손절을 반드시 같이 쓰세요.
    """

    def __init__(
        self,
        period: int = 14,
        oversold: float = 30.0,
        exit_level: float = 55.0,
        trend_filter: int | None = 200,
    ):
        if not 0 < oversold < exit_level < 100:
            raise ValueError(
                f"0 < oversold({oversold}) < exit_level({exit_level}) < 100 이어야 합니다."
            )

        self.period = period
        self.oversold = oversold
        self.exit_level = exit_level
        # 장기 상승추세일 때만 저가매수 — 하락장 물타기를 막는다
        self.trend_filter = trend_filter

        self.warmup = max(period, trend_filter or 0) + 1

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        self._validate(df)
        close = df["close"]
        r = rsi(close, self.period)

        allowed = pd.Series(True, index=df.index)
        if self.trend_filter:
            allowed = close > sma(close, self.trend_filter)
            allowed = allowed.fillna(False)

        entry = (r < self.oversold) & allowed
        exit_ = r > self.exit_level

        # 진입/청산 신호를 상태로 바꾼다.
        # entry에서 1, exit에서 0, 그 사이는 직전 상태 유지.
        state = pd.Series(np.nan, index=df.index, dtype="float64")
        state[entry] = 1.0
        state[exit_] = 0.0
        # 같은 봉에 둘 다 켜지면 청산이 우선 (보수적)
        state[entry & exit_] = 0.0

        signal = state.ffill().fillna(0.0)
        signal[r.isna()] = 0.0
        return signal.rename("signal")
