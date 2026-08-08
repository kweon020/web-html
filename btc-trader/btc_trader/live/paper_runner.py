"""실시간 페이퍼 트레이딩 루프.

업비트 실시간 시세를 받아 전략을 돌리되, 주문은 PaperBroker로만 나간다.
실제 돈은 1원도 움직이지 않는다.

백테스트와 다른, 실시간에서만 드러나는 문제들을 여기서 잡는다:
  - 봉이 아직 안 닫혔는데 시그널을 내는 문제
  - 재시작 시 포지션 유실
  - 네트워크 끊김
  - 같은 봉에서 중복 주문
"""

from __future__ import annotations

import logging
import time
from datetime import datetime

import pandas as pd

from ..broker.paper import PaperBroker
from ..config import RiskConfig
from ..data import upbit
from ..strategies.base import Strategy

logger = logging.getLogger(__name__)


class PaperRunner:
    """봉이 닫힐 때마다 전략을 돌리고 페이퍼 주문을 낸다."""

    def __init__(
        self,
        strategy: Strategy,
        broker: PaperBroker,
        market: str = "KRW-BTC",
        interval: str = "60m",
        risk: RiskConfig | None = None,
        poll_seconds: float = 30.0,
    ):
        self.strategy = strategy
        self.broker = broker
        self.market = market
        self.interval = interval
        self.risk = risk or RiskConfig()
        self.poll_seconds = poll_seconds

        # 마지막으로 '처리한' 봉의 시각. 같은 봉을 두 번 처리하지 않기 위한 방어.
        self._last_bar: pd.Timestamp | None = None
        # 지표 워밍업 + 여유
        self._lookback = max(strategy.warmup * 3, 200)

    def run_once(self) -> bool:
        """새로 닫힌 봉이 있으면 한 번 처리한다. 처리했으면 True."""
        try:
            df = upbit.fetch_candles(
                market=self.market, interval=self.interval, count=self._lookback
            )
        except upbit.UpbitDataError as exc:
            logger.error("시세 조회 실패, 이번 주기는 건너뜁니다: %s", exc)
            return False

        if len(df) < self.strategy.warmup + 2:
            logger.warning(
                "데이터가 부족합니다 (%d개, 최소 %d개 필요)",
                len(df), self.strategy.warmup + 2,
            )
            return False

        # 마지막 봉은 아직 진행 중일 수 있다 -> 버리고 '닫힌' 봉까지만 쓴다.
        # 이걸 안 하면 확정되지 않은 값으로 매매하게 된다.
        closed = df.iloc[:-1]
        bar_time = closed.index[-1]

        if self._last_bar is not None and bar_time <= self._last_bar:
            return False  # 아직 새 봉이 안 닫혔다

        signal = float(self.strategy.generate_signals(closed).iloc[-1])
        price = float(closed["close"].iloc[-1])
        self._act(signal, price, bar_time)

        self._last_bar = bar_time
        return True

    def _act(self, signal: float, price: float, ts: pd.Timestamp) -> None:
        pos = self.broker.get_position()
        equity = self.broker.equity(price)

        if signal > 0 and not pos.is_open:
            budget = self.broker.get_cash() * self.risk.position_pct
            result = self.broker.buy(price, budget, ts)
            if result.ok:
                logger.info("진입: %.8f BTC @ %,.0f원", result.qty, result.price)

        elif signal == 0 and pos.is_open:
            result = self.broker.sell(price, pos.qty, ts)
            if result.ok:
                pnl = (result.price - pos.avg_price) * result.qty - result.fee
                logger.info("청산: 손익 %+,.0f원", pnl)

        elif pos.is_open and self.risk.stop_loss_pct is not None:
            # 시그널과 무관하게 손절선 확인
            stop = pos.avg_price * (1.0 - self.risk.stop_loss_pct)
            if price <= stop:
                result = self.broker.sell(price, pos.qty, ts)
                if result.ok:
                    logger.warning("손절 발동 @ %,.0f원 (평단 %,.0f)", price, pos.avg_price)

        logger.info(
            "[%s] 시그널=%.0f 가격=%,.0f 평가액=%,.0f원",
            ts, signal, price, equity,
        )

    def run_forever(self, max_iterations: int | None = None) -> None:
        """Ctrl+C로 멈출 때까지 계속 돈다."""
        logger.info(
            "페이퍼 트레이딩 시작 — %s %s / %s",
            self.market, self.interval, self.strategy.describe(),
        )
        logger.info("실제 주문은 나가지 않습니다.")

        count = 0
        try:
            while max_iterations is None or count < max_iterations:
                self.run_once()
                count += 1
                time.sleep(self.poll_seconds)
        except KeyboardInterrupt:
            logger.info("중단 요청을 받았습니다.")
        finally:
            self.broker.save()
            pos = self.broker.get_position()
            logger.info(
                "종료 — 현금 %,.0f원, 보유 %.8f BTC", self.broker.get_cash(), pos.qty
            )
