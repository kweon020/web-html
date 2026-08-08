"""페이퍼 브로커 — 실제 주문 없이 장부만 관리한다.

실거래 전에 반드시 이걸로 충분히 돌려보세요.
백테스트가 통과해도 실시간에서는 데이터 지연, 재시작, 중복 주문 같은
전혀 다른 문제가 나옵니다. 그걸 잡는 단계입니다.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

from ..config import FeeModel
from .base import Broker, OrderResult, Position

logger = logging.getLogger(__name__)


class PaperBroker(Broker):
    """메모리 장부 + 선택적 파일 저장.

    state_path를 주면 재시작해도 포지션이 유지된다.
    실시간 봇에서 이건 필수다 — 재시작할 때마다 포지션을 잊으면
    이미 산 걸 또 사게 된다.
    """

    def __init__(
        self,
        initial_cash: float = 1_000_000.0,
        fees: FeeModel | None = None,
        state_path: str | Path | None = None,
        min_order_krw: float = 5_000.0,
    ):
        self.fees = fees or FeeModel()
        self.min_order_krw = min_order_krw
        self.state_path = Path(state_path) if state_path else None

        self._cash = initial_cash
        self._position = Position()
        self.history: list[OrderResult] = []

        if self.state_path and self.state_path.exists():
            self._load()

    # -- Broker 인터페이스 --------------------------------------------
    def get_cash(self) -> float:
        return self._cash

    def get_position(self) -> Position:
        return self._position

    def buy(self, price: float, krw_amount: float, ts: pd.Timestamp) -> OrderResult:
        if krw_amount < self.min_order_krw:
            return self._reject(
                "buy", price, ts,
                f"주문금액 {krw_amount:,.0f}원이 최소 {self.min_order_krw:,.0f}원 미만",
            )
        if krw_amount > self._cash:
            return self._reject(
                "buy", price, ts,
                f"현금 부족 (필요 {krw_amount:,.0f} / 보유 {self._cash:,.0f})",
            )

        fill_px = price * (1.0 + self.fees.slippage_rate)
        # krw_amount 안에 수수료까지 포함되도록 수량을 역산
        qty = krw_amount / (fill_px * (1.0 + self.fees.fee_rate))
        cost = fill_px * qty
        fee = cost * self.fees.fee_rate

        # 평단가 갱신 (분할매수 대비)
        total_qty = self._position.qty + qty
        self._position.avg_price = (
            (self._position.avg_price * self._position.qty + fill_px * qty) / total_qty
        )
        self._position.qty = total_qty
        self._cash -= cost + fee

        return self._record(
            OrderResult("buy", fill_px, qty, fee, ts, ok=True, message="체결")
        )

    def sell(self, price: float, qty: float, ts: pd.Timestamp) -> OrderResult:
        if qty <= 0:
            return self._reject("sell", price, ts, "수량이 0 이하")
        if qty > self._position.qty + 1e-12:
            return self._reject(
                "sell", price, ts,
                f"보유 수량 부족 (요청 {qty:.8f} / 보유 {self._position.qty:.8f})",
            )

        fill_px = price * (1.0 - self.fees.slippage_rate)
        proceeds = fill_px * qty
        fee = proceeds * self.fees.fee_rate

        self._cash += proceeds - fee
        self._position.qty -= qty
        if self._position.qty <= 1e-12:
            self._position = Position()

        return self._record(
            OrderResult("sell", fill_px, qty, fee, ts, ok=True, message="체결")
        )

    # -- 상태 저장 ------------------------------------------------------
    def save(self) -> None:
        if not self.state_path:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(
                {
                    "cash": self._cash,
                    "qty": self._position.qty,
                    "avg_price": self._position.avg_price,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def _load(self) -> None:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            self._cash = float(data["cash"])
            self._position = Position(
                qty=float(data["qty"]), avg_price=float(data["avg_price"])
            )
            logger.info(
                "이전 상태 복원: 현금 %,.0f원, 수량 %.8f", self._cash, self._position.qty
            )
        except (OSError, ValueError, KeyError) as exc:
            logger.warning("상태 파일을 읽지 못해 초기값으로 시작합니다: %s", exc)

    # -- 내부 ----------------------------------------------------------
    def _record(self, result: OrderResult) -> OrderResult:
        self.history.append(result)
        self.save()
        logger.info(
            "%s %s %.8f @ %,.0f (수수료 %,.0f)",
            result.timestamp, result.side.upper(), result.qty, result.price, result.fee,
        )
        return result

    def _reject(self, side: str, price: float, ts: pd.Timestamp, why: str) -> OrderResult:
        logger.warning("주문 거부 (%s): %s", side, why)
        return OrderResult(side, price, 0.0, 0.0, ts, ok=False, message=why)
