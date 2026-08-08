"""볼린저 밴드 돌파 — 변동성 확장을 따라간다."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..indicators import bollinger
from .base import Strategy


class BBBreakoutStrategy(Strategy):
    """상단 밴드를 종가로 뚫으면 진입, 중심선 아래로 내려오면 청산."""

    def __init__(
        self,
        period: int = 20,
        num_std: float = 2.0,
        exit_on: str = "mid",
    ):
        if exit_on not in {"mid", "lower"}:
            raise ValueError(f"exit_on은 'mid' 또는 'lower'여야 합니다: {exit_on}")

        self.period = period
        self.num_std = num_std
        self.exit_on = exit_on
        self.warmup = period + 1

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        self._validate(df)
        close = df["close"]
        bands = bollinger(close, self.period, self.num_std)

        entry = close > bands["upper"]
        exit_ = close < bands[self.exit_on]

        state = pd.Series(np.nan, index=df.index, dtype="float64")
        state[entry] = 1.0
        state[exit_] = 0.0

        signal = state.ffill().fillna(0.0)
        signal[bands["mid"].isna()] = 0.0
        return signal.rename("signal")


class BuyAndHoldStrategy(Strategy):
    """계속 들고 있기. 모든 전략의 기준선.

    당신의 전략이 이걸 못 이기면 그 전략은 존재 이유가 없다.
    수수료와 세금까지 감안하면 더 그렇다.
    """

    warmup = 1

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        self._validate(df)
        return pd.Series(1.0, index=df.index, name="signal")
