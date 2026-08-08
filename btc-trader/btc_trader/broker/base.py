"""브로커 인터페이스.

페이퍼와 실거래가 같은 인터페이스를 쓰도록 해서,
전략/실행 로직을 한 줄도 안 고치고 갈아끼울 수 있게 한다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd


@dataclass
class Position:
    qty: float = 0.0
    avg_price: float = 0.0

    @property
    def is_open(self) -> bool:
        return self.qty > 0


@dataclass
class OrderResult:
    side: str  # buy / sell
    price: float
    qty: float
    fee: float
    timestamp: pd.Timestamp
    ok: bool = True
    message: str = ""


class Broker(ABC):
    """주문 실행 추상화."""

    @abstractmethod
    def get_cash(self) -> float:
        """주문 가능한 현금(원)."""

    @abstractmethod
    def get_position(self) -> Position:
        """현재 보유 포지션."""

    @abstractmethod
    def buy(self, price: float, krw_amount: float, ts: pd.Timestamp) -> OrderResult:
        """시장가 매수. krw_amount는 수수료 포함 총 지출 상한."""

    @abstractmethod
    def sell(self, price: float, qty: float, ts: pd.Timestamp) -> OrderResult:
        """시장가 매도."""

    def equity(self, mark_price: float) -> float:
        """현금 + 평가금액."""
        return self.get_cash() + self.get_position().qty * mark_price
