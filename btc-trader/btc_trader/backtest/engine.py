"""이벤트 기반 백테스트 엔진.

설계 원칙 (여기가 백테스트의 신뢰도를 결정한다):

1. Look-ahead 금지
   봉 t의 종가로 만든 시그널은 봉 t+1의 '시가'에 체결된다.
   종가를 보고 그 종가에 사는 건 현실에서 불가능하다.

2. 비용 반영
   매수/매도 양쪽에 수수료와 슬리피지를 모두 물린다.
   이걸 빼면 단타 전략의 성과가 완전히 거짓이 된다.

3. 리스크 규칙은 봉 내부에서 검사
   손절/익절은 시그널과 무관하게 봉의 고가/저가로 판정한다.
   같은 봉에 손절과 익절이 모두 닿으면 손절을 우선한다(보수적 가정).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..config import BacktestConfig
from ..strategies.base import Strategy


@dataclass
class Trade:
    """체결된 한 번의 왕복 거래."""

    entry_time: pd.Timestamp
    entry_price: float
    exit_time: pd.Timestamp
    exit_price: float
    qty: float
    fees: float
    reason: str  # signal / stop_loss / take_profit / end_of_data

    @property
    def pnl(self) -> float:
        """수수료까지 반영한 순손익(원)."""
        return (self.exit_price - self.entry_price) * self.qty - self.fees

    @property
    def return_pct(self) -> float:
        cost = self.entry_price * self.qty
        return self.pnl / cost if cost else 0.0


@dataclass
class BacktestResult:
    equity: pd.Series
    trades: list[Trade] = field(default_factory=list)
    signals: pd.Series | None = None
    strategy_name: str = ""

    @property
    def returns(self) -> pd.Series:
        return self.equity.pct_change().fillna(0.0)


class BacktestEngine:
    """단일 종목 롱온리 백테스터."""

    def __init__(self, config: BacktestConfig | None = None):
        self.config = config or BacktestConfig()

    def run(self, df: pd.DataFrame, strategy: Strategy) -> BacktestResult:
        self._validate(df)

        cfg = self.config
        risk = cfg.risk
        fees = cfg.fees

        signals = strategy.generate_signals(df)
        if len(signals) != len(df):
            raise ValueError("시그널 길이가 데이터와 다릅니다.")

        # 체결 지연: 봉 t의 시그널 -> 봉 t+1에 실행
        target = signals.shift(1).fillna(0.0).to_numpy()

        open_ = df["open"].to_numpy(dtype="float64")
        high = df["high"].to_numpy(dtype="float64")
        low = df["low"].to_numpy(dtype="float64")
        close = df["close"].to_numpy(dtype="float64")
        index = df.index

        cash = cfg.initial_capital
        qty = 0.0
        entry_price = 0.0
        entry_time: pd.Timestamp | None = None
        entry_fee = 0.0

        equity_curve = np.empty(len(df), dtype="float64")
        trades: list[Trade] = []

        # 일일 손실 한도 추적
        day_start_equity = cfg.initial_capital
        current_day = index[0].date()
        halted_today = False

        for i in range(len(df)):
            # ---- 날짜가 바뀌면 일일 한도 리셋 ----
            bar_day = index[i].date()
            if bar_day != current_day:
                current_day = bar_day
                day_start_equity = cash + qty * open_[i]
                halted_today = False

            # ---- 1) 보유 중이면 손절/익절 먼저 검사 ----
            if qty > 0:
                stop_px = self._stop_price(entry_price, risk)
                take_px = self._take_price(entry_price, risk)

                hit_stop = stop_px is not None and low[i] <= stop_px
                hit_take = take_px is not None and high[i] >= take_px

                if hit_stop or hit_take:
                    # 같은 봉에 둘 다 닿으면 손절 우선 (보수적)
                    if hit_stop:
                        raw_px, reason = stop_px, "stop_loss"
                    else:
                        raw_px, reason = take_px, "take_profit"

                    exit_px = self._apply_slippage(raw_px, side="sell", fees=fees)
                    proceeds = exit_px * qty
                    fee = proceeds * fees.fee_rate
                    cash += proceeds - fee

                    trades.append(
                        Trade(
                            entry_time=entry_time,
                            entry_price=entry_price,
                            exit_time=index[i],
                            exit_price=exit_px,
                            qty=qty,
                            fees=entry_fee + fee,
                            reason=reason,
                        )
                    )
                    qty = 0.0
                    entry_price = 0.0
                    entry_time = None
                    entry_fee = 0.0

            # ---- 2) 목표 포지션에 맞춰 진입/청산 ----
            want = target[i]

            if qty > 0 and want == 0.0:
                exit_px = self._apply_slippage(open_[i], side="sell", fees=fees)
                proceeds = exit_px * qty
                fee = proceeds * fees.fee_rate
                cash += proceeds - fee

                trades.append(
                    Trade(
                        entry_time=entry_time,
                        entry_price=entry_price,
                        exit_time=index[i],
                        exit_price=exit_px,
                        qty=qty,
                        fees=entry_fee + fee,
                        reason="signal",
                    )
                )
                qty = 0.0
                entry_price = 0.0
                entry_time = None
                entry_fee = 0.0

            elif qty == 0.0 and want > 0.0 and not halted_today:
                budget = cash * risk.position_pct
                if budget >= risk.min_order_krw:
                    buy_px = self._apply_slippage(open_[i], side="buy", fees=fees)
                    # 수수료를 포함해 예산을 넘지 않도록 수량 계산
                    buy_qty = budget / (buy_px * (1.0 + fees.fee_rate))
                    cost = buy_px * buy_qty
                    fee = cost * fees.fee_rate

                    cash -= cost + fee
                    qty = buy_qty
                    entry_price = buy_px
                    entry_time = index[i]
                    entry_fee = fee

            # ---- 3) 평가금액 기록 ----
            equity_curve[i] = cash + qty * close[i]

            # ---- 4) 일일 손실 한도 확인 ----
            if risk.daily_loss_limit_pct is not None and day_start_equity > 0:
                drawdown = 1.0 - equity_curve[i] / day_start_equity
                if drawdown >= risk.daily_loss_limit_pct:
                    halted_today = True

        # ---- 데이터 끝에 포지션이 남아 있으면 종가로 청산 ----
        if qty > 0:
            exit_px = self._apply_slippage(close[-1], side="sell", fees=fees)
            proceeds = exit_px * qty
            fee = proceeds * fees.fee_rate
            cash += proceeds - fee
            trades.append(
                Trade(
                    entry_time=entry_time,
                    entry_price=entry_price,
                    exit_time=index[-1],
                    exit_price=exit_px,
                    qty=qty,
                    fees=entry_fee + fee,
                    reason="end_of_data",
                )
            )
            equity_curve[-1] = cash

        return BacktestResult(
            equity=pd.Series(equity_curve, index=index, name="equity"),
            trades=trades,
            signals=signals,
            strategy_name=strategy.describe(),
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _apply_slippage(price: float, *, side: str, fees) -> float:
        """체결가를 불리한 쪽으로 민다."""
        if side == "buy":
            return price * (1.0 + fees.slippage_rate)
        return price * (1.0 - fees.slippage_rate)

    @staticmethod
    def _stop_price(entry_price: float, risk) -> float | None:
        if risk.stop_loss_pct is None:
            return None
        return entry_price * (1.0 - risk.stop_loss_pct)

    @staticmethod
    def _take_price(entry_price: float, risk) -> float | None:
        if risk.take_profit_pct is None:
            return None
        return entry_price * (1.0 + risk.take_profit_pct)

    @staticmethod
    def _validate(df: pd.DataFrame) -> None:
        if df.empty:
            raise ValueError("데이터가 비어 있습니다.")
        required = {"open", "high", "low", "close"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"필수 컬럼 없음: {sorted(missing)}")
        if df[sorted(required)].isna().any().any():
            raise ValueError("OHLC에 결측치가 있습니다. 먼저 정제하세요.")
        if not df.index.is_monotonic_increasing:
            raise ValueError("인덱스가 시간 오름차순이 아닙니다.")
