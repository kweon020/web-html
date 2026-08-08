"""페이퍼 브로커 테스트."""

from __future__ import annotations

import pandas as pd
import pytest

from btc_trader.broker import PaperBroker
from btc_trader.config import FeeModel

TS = pd.Timestamp("2024-01-01 09:00")


def make_broker(cash=1_000_000.0, fee=0.0005, slip=5.0, **kw):
    return PaperBroker(initial_cash=cash, fees=FeeModel(fee, slip), **kw)


def test_buy_reduces_cash_and_creates_position():
    b = make_broker()
    r = b.buy(price=100_000_000.0, krw_amount=300_000.0, ts=TS)

    assert r.ok
    assert b.get_position().is_open
    assert b.get_cash() == pytest.approx(700_000.0, rel=1e-6)


def test_buy_spends_at_most_requested_amount():
    """수수료를 포함해도 요청 금액을 넘으면 안 된다."""
    b = make_broker()
    before = b.get_cash()
    b.buy(price=50_000_000.0, krw_amount=300_000.0, ts=TS)
    spent = before - b.get_cash()
    assert spent <= 300_000.0 + 1e-6


def test_sell_restores_cash():
    b = make_broker()
    b.buy(price=100_000_000.0, krw_amount=500_000.0, ts=TS)
    qty = b.get_position().qty

    r = b.sell(price=100_000_000.0, qty=qty, ts=TS)
    assert r.ok
    assert not b.get_position().is_open
    # 왕복 수수료+슬리피지만큼 줄어야 한다
    assert b.get_cash() < 1_000_000.0
    assert b.get_cash() > 950_000.0


def test_cannot_sell_more_than_held():
    b = make_broker()
    b.buy(price=100_000_000.0, krw_amount=100_000.0, ts=TS)
    r = b.sell(price=100_000_000.0, qty=b.get_position().qty * 2, ts=TS)

    assert not r.ok
    assert "부족" in r.message


def test_cannot_buy_more_than_cash():
    b = make_broker(cash=100_000.0)
    r = b.buy(price=100_000_000.0, krw_amount=500_000.0, ts=TS)

    assert not r.ok
    assert "부족" in r.message


def test_min_order_rejected():
    b = make_broker()
    r = b.buy(price=100_000_000.0, krw_amount=1_000.0, ts=TS)

    assert not r.ok
    assert "최소" in r.message


def test_slippage_makes_prices_worse():
    b = make_broker(slip=100.0)  # 1%
    buy = b.buy(price=100.0, krw_amount=500_000.0, ts=TS)
    assert buy.price > 100.0  # 매수는 비싸게

    sell = b.sell(price=100.0, qty=b.get_position().qty, ts=TS)
    assert sell.price < 100.0  # 매도는 싸게


def test_average_price_on_partial_buys():
    # 최소 주문금액(5,000원)을 넘도록 잡는다
    b = make_broker(cash=10_000_000.0, fee=0.0, slip=0.0)
    b.buy(price=100.0, krw_amount=10_000.0, ts=TS)   # 100개 @ 100
    b.buy(price=200.0, krw_amount=20_000.0, ts=TS)   # 100개 @ 200
    # (100*100 + 200*100) / 200 = 150
    assert b.get_position().qty == pytest.approx(200.0, rel=1e-6)
    assert b.get_position().avg_price == pytest.approx(150.0, rel=1e-6)


def test_state_survives_restart(tmp_path):
    """재시작해도 포지션이 유지되어야 한다.

    이게 없으면 봇을 재시작할 때마다 이미 산 걸 또 산다.
    """
    state = tmp_path / "state.json"

    b1 = make_broker(state_path=state)
    b1.buy(price=100_000_000.0, krw_amount=400_000.0, ts=TS)
    qty, cash = b1.get_position().qty, b1.get_cash()

    b2 = make_broker(state_path=state)
    assert b2.get_position().qty == pytest.approx(qty)
    assert b2.get_cash() == pytest.approx(cash)


def test_equity_includes_position_value():
    b = make_broker(fee=0.0, slip=0.0)
    b.buy(price=100.0, krw_amount=500_000.0, ts=TS)
    # 가격이 2배 되면 평가액도 그만큼
    assert b.equity(200.0) == pytest.approx(1_500_000.0, rel=1e-6)


def test_corrupt_state_file_falls_back(tmp_path):
    """상태 파일이 깨져도 죽지 않고 초기값으로 시작해야 한다."""
    state = tmp_path / "bad.json"
    state.write_text("{ 깨진 json", encoding="utf-8")

    b = make_broker(cash=777_000.0, state_path=state)
    assert b.get_cash() == pytest.approx(777_000.0)
    assert not b.get_position().is_open
