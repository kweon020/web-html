"""전략 인터페이스.

핵심 규약: generate_signals(df)는 df와 같은 인덱스의 Series를 돌려준다.
값은 목표 포지션이다.
    1.0  = 롱 진입/유지
    0.0  = 청산/현금

시점 t의 시그널은 t까지의 데이터만으로 만들어야 한다.
백테스트 엔진은 이 시그널을 t+1 봉의 시가에 체결한다 —
그래야 '종가를 보고 종가에 산다'는 불가능한 가정을 피할 수 있다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class Strategy(ABC):
    """모든 전략의 부모 클래스."""

    #: 지표 워밍업에 필요한 최소 봉 개수. 엔진이 이만큼은 건너뛴다.
    warmup: int = 0

    @property
    def name(self) -> str:
        return self.__class__.__name__

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """OHLCV를 받아 목표 포지션 Series를 돌려준다."""

    def describe(self) -> str:
        """설정값을 사람이 읽을 수 있게."""
        params = ", ".join(
            f"{k}={v}" for k, v in vars(self).items() if not k.startswith("_")
        )
        return f"{self.name}({params})"

    @staticmethod
    def _validate(df: pd.DataFrame) -> None:
        required = {"open", "high", "low", "close", "volume"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"OHLCV 컬럼이 없습니다: {sorted(missing)}")
        if not df.index.is_monotonic_increasing:
            raise ValueError("인덱스가 시간 오름차순이 아닙니다.")
