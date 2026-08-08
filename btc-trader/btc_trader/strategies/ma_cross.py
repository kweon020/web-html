"""이동평균 교차 — 가장 고전적인 추세추종."""

from __future__ import annotations

import pandas as pd

from ..indicators import ema, sma
from .base import Strategy


class MACrossStrategy(Strategy):
    """단기 이평이 장기 이평 위에 있으면 롱, 아래면 현금.

    추세장에서 벌고 횡보장에서 수수료로 잃는 전형적인 전략이다.
    두 구간 모두에서 백테스트해보고 판단하세요.
    """

    def __init__(
        self,
        fast: int = 10,
        slow: int = 30,
        use_ema: bool = False,
        trend_filter: int | None = None,
    ):
        if fast >= slow:
            raise ValueError(f"fast({fast})는 slow({slow})보다 작아야 합니다.")

        self.fast = fast
        self.slow = slow
        self.use_ema = use_ema
        # 장기 추세 필터: 종가가 이 이평 아래면 롱을 아예 안 잡는다.
        # 하락장에서 반복 손절되는 걸 크게 줄여준다.
        self.trend_filter = trend_filter

        self.warmup = max(slow, trend_filter or 0) + 1

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        self._validate(df)
        ma = ema if self.use_ema else sma
        close = df["close"]

        fast_ma = ma(close, self.fast)
        slow_ma = ma(close, self.slow)

        # 상태 기반: 교차 '시점'이 아니라 '위/아래 상태'를 본다.
        # 이러면 신호를 놓쳐도 포지션이 어긋나지 않는다.
        long = fast_ma > slow_ma

        if self.trend_filter:
            long &= close > ma(close, self.trend_filter)

        signal = long.astype("float64")
        # 워밍업 구간은 지표가 NaN이므로 무포지션
        signal[fast_ma.isna() | slow_ma.isna()] = 0.0
        return signal.rename("signal")
