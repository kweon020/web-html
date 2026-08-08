"""백테스트 엔진 정확성 테스트.

여기가 가장 중요하다. 백테스터의 버그는 '수익이 나는 것처럼 보이게' 만들고,
그 결과 실제 돈을 잃게 한다.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from btc_trader.backtest import BacktestEngine, compute, max_drawdown
from btc_trader.config import BacktestConfig, FeeModel, RiskConfig
from btc_trader.data import synthetic
from btc_trader.strategies import build
from btc_trader.strategies.base import Strategy


class AlwaysLong(Strategy):
    warmup = 1

    def generate_signals(self, df):
        return pd.Series(1.0, index=df.index)


class NeverTrade(Strategy):
    warmup = 1

    def generate_signals(self, df):
        return pd.Series(0.0, index=df.index)


def flat_market(n=50, price=100.0):
    """가격이 전혀 안 움직이는 시장."""
    idx = pd.date_range("2024-01-01", periods=n, freq="1D", name="timestamp")
    return pd.DataFrame(
        {"open": price, "high": price, "low": price, "close": price, "volume": 1.0},
        index=idx,
    )


def rising_market(n=50, start=100.0, step=1.0):
    idx = pd.date_range("2024-01-01", periods=n, freq="1D", name="timestamp")
    close = start + np.arange(n) * step
    return pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": 1.0},
        index=idx,
    )


# ---------------------------------------------------------------- 기본 동작
def test_no_trades_means_capital_unchanged():
    cfg = BacktestConfig(initial_capital=1_000_000.0)
    result = BacktestEngine(cfg).run(flat_market(), NeverTrade())

    assert len(result.trades) == 0
    assert result.equity.iloc[-1] == pytest.approx(1_000_000.0)


def test_flat_market_with_fees_loses_money():
    """가격이 안 움직여도 매매하면 수수료만큼 반드시 손실이다.

    이 테스트가 실패하면 수수료가 반영되지 않는다는 뜻이다.
    """
    cfg = BacktestConfig(
        initial_capital=1_000_000.0,
        fees=FeeModel(fee_rate=0.0005, slippage_bp=5.0),
        risk=RiskConfig(position_pct=1.0, stop_loss_pct=None),
    )
    result = BacktestEngine(cfg).run(flat_market(), AlwaysLong())

    assert result.equity.iloc[-1] < 1_000_000.0
    assert sum(t.fees for t in result.trades) > 0


def test_zero_cost_flat_market_breaks_even():
    """비용이 0이면 횡보장에서 손익도 0이어야 한다."""
    cfg = BacktestConfig(
        initial_capital=1_000_000.0,
        fees=FeeModel(fee_rate=0.0, slippage_bp=0.0),
        risk=RiskConfig(position_pct=1.0, stop_loss_pct=None),
    )
    result = BacktestEngine(cfg).run(flat_market(), AlwaysLong())
    assert result.equity.iloc[-1] == pytest.approx(1_000_000.0, rel=1e-9)


# ------------------------------------------------------- look-ahead 방지
def test_signal_executes_on_next_bar_not_same_bar():
    """봉 t의 시그널은 봉 t+1의 시가에 체결되어야 한다."""
    idx = pd.date_range("2024-01-01", periods=4, freq="1D", name="timestamp")
    df = pd.DataFrame(
        {
            "open": [100.0, 200.0, 300.0, 400.0],
            "high": [100.0, 200.0, 300.0, 400.0],
            "low": [100.0, 200.0, 300.0, 400.0],
            "close": [100.0, 200.0, 300.0, 400.0],
            "volume": 1.0,
        },
        index=idx,
    )

    class LongOnFirstBar(Strategy):
        warmup = 0

        def generate_signals(self, d):
            return pd.Series([1.0, 1.0, 0.0, 0.0], index=d.index)

    cfg = BacktestConfig(
        initial_capital=1_000_000.0,
        fees=FeeModel(fee_rate=0.0, slippage_bp=0.0),
        risk=RiskConfig(position_pct=1.0, stop_loss_pct=None),
    )
    result = BacktestEngine(cfg).run(df, LongOnFirstBar())

    assert len(result.trades) == 1
    trade = result.trades[0]
    # 봉0에서 신호 -> 봉1 시가(200)에 매수. 봉0 시가(100)가 아니다.
    assert trade.entry_price == pytest.approx(200.0)
    # 봉2에서 청산 신호 -> 봉3 시가(400)에 매도
    assert trade.exit_price == pytest.approx(400.0)


def test_future_data_does_not_change_past_equity():
    """뒤에 데이터를 더 붙여도 앞부분 자산곡선은 그대로여야 한다.

    이 테스트가 깨지면 엔진이 미래를 훔쳐보고 있다는 뜻이다.

    단, 마지막 봉은 제외하고 비교한다. 짧게 자른 쪽은 그 봉에서
    남은 포지션을 강제 청산(end_of_data)하므로 원래 달라야 정상이다.
    """
    df = synthetic.make_ohlcv(bars=300, seed=5)
    cfg = BacktestConfig(initial_capital=1_000_000.0)
    engine = BacktestEngine(cfg)
    strategy = build("ma_cross", fast=5, slow=20)

    cut = 200
    full = engine.run(df, strategy).equity
    partial = engine.run(df.iloc[:cut], strategy).equity

    pd.testing.assert_series_equal(
        full.iloc[: cut - 1], partial.iloc[: cut - 1], check_names=False, rtol=1e-9
    )


def test_only_final_bar_differs_when_truncated():
    """위 테스트의 짝: 차이는 '마지막 봉 하나'에만 있어야 한다.

    더 앞에서 갈라진다면 그건 강제청산이 아니라 진짜 look-ahead다.
    """
    df = synthetic.make_ohlcv(bars=300, seed=5)
    engine = BacktestEngine(BacktestConfig(initial_capital=1_000_000.0))
    strategy = build("ma_cross", fast=5, slow=20)

    cut = 200
    full = engine.run(df, strategy).equity.iloc[:cut]
    partial = engine.run(df.iloc[:cut], strategy).equity

    diff = ~np.isclose(full.to_numpy(), partial.to_numpy(), rtol=1e-9)
    assert diff.sum() <= 1, f"{diff.sum()}개 봉이 다릅니다 — look-ahead 의심"
    if diff.any():
        assert diff[-1], "차이가 마지막 봉이 아닌 곳에서 발생했습니다"


# ------------------------------------------------------------ 리스크 규칙
def test_stop_loss_triggers_on_low():
    """봉의 저가가 손절선을 건드리면 청산되어야 한다."""
    idx = pd.date_range("2024-01-01", periods=4, freq="1D", name="timestamp")
    df = pd.DataFrame(
        {
            "open": [100.0, 100.0, 100.0, 100.0],
            "high": [100.0, 100.0, 100.0, 100.0],
            "low": [100.0, 100.0, 50.0, 100.0],  # 봉2에서 폭락
            "close": [100.0, 100.0, 100.0, 100.0],
            "volume": 1.0,
        },
        index=idx,
    )

    cfg = BacktestConfig(
        initial_capital=1_000_000.0,
        fees=FeeModel(fee_rate=0.0, slippage_bp=0.0),
        risk=RiskConfig(position_pct=1.0, stop_loss_pct=0.10, daily_loss_limit_pct=None),
    )
    result = BacktestEngine(cfg).run(df, AlwaysLong())

    stops = [t for t in result.trades if t.reason == "stop_loss"]
    assert len(stops) == 1
    assert stops[0].exit_price == pytest.approx(90.0)  # 100 * (1 - 0.10)


def test_take_profit_triggers_on_high():
    idx = pd.date_range("2024-01-01", periods=4, freq="1D", name="timestamp")
    df = pd.DataFrame(
        {
            "open": [100.0] * 4,
            "high": [100.0, 100.0, 150.0, 100.0],  # 봉2에서 급등
            "low": [100.0] * 4,
            "close": [100.0] * 4,
            "volume": 1.0,
        },
        index=idx,
    )

    cfg = BacktestConfig(
        initial_capital=1_000_000.0,
        fees=FeeModel(fee_rate=0.0, slippage_bp=0.0),
        risk=RiskConfig(
            position_pct=1.0, stop_loss_pct=None,
            take_profit_pct=0.20, daily_loss_limit_pct=None,
        ),
    )
    result = BacktestEngine(cfg).run(df, AlwaysLong())

    takes = [t for t in result.trades if t.reason == "take_profit"]
    assert len(takes) == 1
    assert takes[0].exit_price == pytest.approx(120.0)


def test_stop_loss_wins_when_both_hit_same_bar():
    """같은 봉에 손절·익절이 모두 닿으면 손절이 우선(보수적)."""
    idx = pd.date_range("2024-01-01", periods=3, freq="1D", name="timestamp")
    df = pd.DataFrame(
        {
            "open": [100.0] * 3,
            "high": [100.0, 100.0, 150.0],
            "low": [100.0, 100.0, 50.0],  # 같은 봉에서 둘 다 터치
            "close": [100.0] * 3,
            "volume": 1.0,
        },
        index=idx,
    )

    cfg = BacktestConfig(
        initial_capital=1_000_000.0,
        fees=FeeModel(fee_rate=0.0, slippage_bp=0.0),
        risk=RiskConfig(
            position_pct=1.0, stop_loss_pct=0.10,
            take_profit_pct=0.20, daily_loss_limit_pct=None,
        ),
    )
    result = BacktestEngine(cfg).run(df, AlwaysLong())
    assert result.trades[0].reason == "stop_loss"


def test_position_sizing_respected():
    """position_pct만큼만 투입해야 한다."""
    cfg = BacktestConfig(
        initial_capital=1_000_000.0,
        fees=FeeModel(fee_rate=0.0, slippage_bp=0.0),
        risk=RiskConfig(position_pct=0.25, stop_loss_pct=None),
    )
    result = BacktestEngine(cfg).run(rising_market(), AlwaysLong())

    trade = result.trades[0]
    invested = trade.entry_price * trade.qty
    assert invested == pytest.approx(250_000.0, rel=1e-6)


def test_min_order_size_blocks_tiny_orders():
    cfg = BacktestConfig(
        initial_capital=10_000.0,
        risk=RiskConfig(position_pct=0.1, min_order_krw=5_000.0),  # 1,000원 -> 거부
    )
    result = BacktestEngine(cfg).run(rising_market(), AlwaysLong())
    assert len(result.trades) == 0


# ------------------------------------------------------------------ 지표
def test_max_drawdown_calculation():
    eq = pd.Series([100.0, 120.0, 60.0, 80.0])
    # 최고점 120 -> 최저 60 = -50%
    assert max_drawdown(eq) == pytest.approx(-0.5)


def test_max_drawdown_never_positive():
    eq = pd.Series([100.0, 110.0, 120.0])  # 단조 증가
    assert max_drawdown(eq) == pytest.approx(0.0)


def test_metrics_on_synthetic_are_sane():
    df = synthetic.make_ohlcv(bars=500, seed=9)
    cfg = BacktestConfig(initial_capital=1_000_000.0)
    result = BacktestEngine(cfg).run(df, build("ma_cross"))
    m = compute(result, 1_000_000.0, bars_per_year=365)

    assert m.max_drawdown_pct <= 0
    assert 0 <= m.win_rate_pct <= 100
    assert 0 <= m.exposure_pct <= 100
    assert m.num_trades == len(result.trades)
    assert m.total_fees >= 0


# ------------------------------------------------------------ 입력 검증
def test_rejects_empty_data():
    with pytest.raises(ValueError, match="비어"):
        BacktestEngine().run(pd.DataFrame(), AlwaysLong())


def test_rejects_unsorted_index():
    df = flat_market(10)
    shuffled = df.iloc[::-1]
    with pytest.raises(ValueError, match="오름차순"):
        BacktestEngine().run(shuffled, AlwaysLong())


def test_rejects_nan_prices():
    df = flat_market(10)
    df.loc[df.index[3], "close"] = np.nan
    with pytest.raises(ValueError, match="결측치"):
        BacktestEngine().run(df, AlwaysLong())


def test_buy_and_hold_makes_exactly_one_trade():
    """손절 없이 전액 투입한 '단순 보유'는 왕복 1회여야 한다.

    이게 깨지면 기준선이 오염되어 다른 전략과 비교할 수 없게 된다.
    """
    df = synthetic.make_ohlcv(bars=400, seed=21)
    cfg = BacktestConfig(
        initial_capital=1_000_000.0,
        risk=RiskConfig(
            position_pct=1.0, stop_loss_pct=None,
            take_profit_pct=None, daily_loss_limit_pct=None,
        ),
    )
    result = BacktestEngine(cfg).run(df, build("hold"))

    assert len(result.trades) == 1
    assert result.trades[0].reason == "end_of_data"


def test_rsi_strategy_actually_generates_entries():
    """RSI 전략이 실제로 진입 신호를 내는지 확인.

    trend_filter를 켜면 매우 보수적이라 구간에 따라 0회일 수 있다.
    그건 정상이지만, 필터를 끄면 반드시 신호가 나와야 한다.
    """
    df = synthetic.make_ohlcv(bars=800, seed=42)
    signals = build("rsi", trend_filter=None).generate_signals(df)
    assert (signals > 0).sum() > 0, "필터 없이도 진입이 0회라면 전략이 고장난 것"


def test_daily_loss_limit_blocks_new_entries():
    """일일 손실 한도를 넘으면 그날 신규 진입이 막혀야 한다."""
    idx = pd.date_range("2024-01-01", periods=6, freq="1h", name="timestamp")
    # 같은 날 안에서 급락시킨다
    close = [100.0, 100.0, 70.0, 70.0, 70.0, 70.0]
    df = pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": 1.0},
        index=idx,
    )

    cfg = BacktestConfig(
        initial_capital=1_000_000.0,
        fees=FeeModel(fee_rate=0.0, slippage_bp=0.0),
        risk=RiskConfig(
            position_pct=1.0, stop_loss_pct=0.05,
            daily_loss_limit_pct=0.10,
        ),
    )
    result = BacktestEngine(cfg).run(df, AlwaysLong())

    # 손절 후 한도에 걸려 같은 날 재진입이 무제한 반복되면 안 된다
    same_day = [t for t in result.trades if t.entry_time.date() == idx[0].date()]
    assert len(same_day) <= 2, f"일일 한도가 동작하지 않습니다 ({len(same_day)}회 진입)"


def test_all_strategies_run_without_error():
    """등록된 전략이 전부 예외 없이 돌아야 한다."""
    df = synthetic.make_ohlcv(bars=600, seed=13)
    engine = BacktestEngine(BacktestConfig())

    for name in ["ma_cross", "rsi", "bb", "hold"]:
        result = engine.run(df, build(name))
        assert len(result.equity) == len(df)
        assert (result.equity > 0).all(), f"{name}: 자산이 0 이하로 갔습니다"
