"""백테스트 성과 지표.

수익률만 보면 안 된다. MDD와 거래 횟수를 반드시 같이 보세요.
"수익률 300%, MDD -85%"는 실전에서 못 버티는 전략이다.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .engine import BacktestResult


@dataclass
class Metrics:
    initial_capital: float
    final_equity: float
    total_return_pct: float
    cagr_pct: float
    max_drawdown_pct: float
    sharpe: float
    sortino: float
    calmar: float
    volatility_pct: float
    num_trades: int
    win_rate_pct: float
    avg_win_pct: float
    avg_loss_pct: float
    profit_factor: float
    total_fees: float
    exposure_pct: float

    def to_dict(self) -> dict:
        return asdict(self)

    def format(self) -> str:
        """콘솔 출력용."""
        rows = [
            ("초기 자본", f"{self.initial_capital:,.0f} 원"),
            ("최종 평가액", f"{self.final_equity:,.0f} 원"),
            ("총 수익률", f"{self.total_return_pct:+.2f} %"),
            ("연복리(CAGR)", f"{self.cagr_pct:+.2f} %"),
            ("최대낙폭(MDD)", f"{self.max_drawdown_pct:.2f} %"),
            ("변동성(연율)", f"{self.volatility_pct:.2f} %"),
            ("샤프", f"{self.sharpe:.2f}"),
            ("소르티노", f"{self.sortino:.2f}"),
            ("칼마", f"{self.calmar:.2f}"),
            ("거래 횟수", f"{self.num_trades} 회"),
            ("승률", f"{self.win_rate_pct:.1f} %"),
            ("평균 수익", f"{self.avg_win_pct:+.2f} %"),
            ("평균 손실", f"{self.avg_loss_pct:+.2f} %"),
            ("손익비(PF)", f"{self.profit_factor:.2f}"),
            ("총 수수료", f"{self.total_fees:,.0f} 원"),
            ("시장 노출", f"{self.exposure_pct:.1f} %"),
        ]
        width = max(len(k) for k, _ in rows)
        return "\n".join(f"  {k:<{width}}  {v:>18}" for k, v in rows)


def max_drawdown(equity: pd.Series) -> float:
    """최대 낙폭을 음수 비율로 돌려준다 (-0.35 = -35%)."""
    if equity.empty:
        return 0.0
    running_max = equity.cummax()
    dd = equity / running_max - 1.0
    return float(dd.min())


def compute(
    result: BacktestResult,
    initial_capital: float,
    bars_per_year: float = 365.0,
    risk_free_rate: float = 0.0,
) -> Metrics:
    """BacktestResult에서 지표를 계산한다."""
    equity = result.equity
    final = float(equity.iloc[-1]) if len(equity) else initial_capital
    total_return = final / initial_capital - 1.0

    returns = equity.pct_change().dropna()
    n_bars = len(equity)

    # --- 연복리 ---
    if n_bars > 1 and initial_capital > 0 and final > 0:
        years = n_bars / bars_per_year
        cagr = (final / initial_capital) ** (1.0 / years) - 1.0 if years > 0 else 0.0
    else:
        cagr = 0.0

    # --- 위험조정 지표 ---
    ann = np.sqrt(bars_per_year)
    std = float(returns.std(ddof=1)) if len(returns) > 1 else 0.0
    mean = float(returns.mean()) if len(returns) else 0.0
    volatility = std * ann

    excess = mean - risk_free_rate / bars_per_year
    sharpe = (excess / std * ann) if std > 0 else 0.0

    downside = returns[returns < 0]
    dstd = float(downside.std(ddof=1)) if len(downside) > 1 else 0.0
    sortino = (excess / dstd * ann) if dstd > 0 else 0.0

    mdd = max_drawdown(equity)
    calmar = (cagr / abs(mdd)) if mdd < 0 else 0.0

    # --- 거래 통계 ---
    trades = result.trades
    pnls = [t.pnl for t in trades]
    rets = [t.return_pct for t in trades]
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]

    gross_profit = sum(p for p in pnls if p > 0)
    gross_loss = abs(sum(p for p in pnls if p < 0))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (
        float("inf") if gross_profit > 0 else 0.0
    )

    # --- 시장 노출 비율 ---
    if result.signals is not None and len(result.signals):
        exposure = float((result.signals.shift(1).fillna(0.0) > 0).mean())
    else:
        exposure = 0.0

    return Metrics(
        initial_capital=initial_capital,
        final_equity=final,
        total_return_pct=total_return * 100.0,
        cagr_pct=cagr * 100.0,
        max_drawdown_pct=mdd * 100.0,
        sharpe=sharpe,
        sortino=sortino,
        calmar=calmar,
        volatility_pct=volatility * 100.0,
        num_trades=len(trades),
        win_rate_pct=(len(wins) / len(rets) * 100.0) if rets else 0.0,
        avg_win_pct=(float(np.mean(wins)) * 100.0) if wins else 0.0,
        avg_loss_pct=(float(np.mean(losses)) * 100.0) if losses else 0.0,
        profit_factor=profit_factor,
        total_fees=sum(t.fees for t in trades),
        exposure_pct=exposure * 100.0,
    )
