"""전략 레지스트리.

새 전략을 만들면 여기 STRATEGIES에 등록하면 CLI에서 바로 쓸 수 있다.
"""

from __future__ import annotations

from .base import Strategy
from .bb_breakout import BBBreakoutStrategy, BuyAndHoldStrategy
from .ma_cross import MACrossStrategy
from .rsi_reversion import RSIReversionStrategy

STRATEGIES: dict[str, type[Strategy]] = {
    "ma_cross": MACrossStrategy,
    "rsi": RSIReversionStrategy,
    "bb": BBBreakoutStrategy,
    "hold": BuyAndHoldStrategy,
}


def build(name: str, **params) -> Strategy:
    """이름으로 전략을 만든다."""
    if name not in STRATEGIES:
        raise ValueError(
            f"모르는 전략: {name}. 사용 가능: {sorted(STRATEGIES)}"
        )
    return STRATEGIES[name](**params)


__all__ = [
    "STRATEGIES",
    "Strategy",
    "build",
    "MACrossStrategy",
    "RSIReversionStrategy",
    "BBBreakoutStrategy",
    "BuyAndHoldStrategy",
]
