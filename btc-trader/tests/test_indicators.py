"""지표 정확성 테스트.

지표가 틀리면 백테스트 전체가 무의미해진다. 알려진 값과 대조한다.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from btc_trader.indicators import (
    atr, bollinger, crossover, crossunder, ema, macd, rsi, sma,
)


def test_sma_matches_manual_average():
    s = pd.Series([1.0, 2, 3, 4, 5])
    out = sma(s, 3)
    assert np.isnan(out.iloc[0]) and np.isnan(out.iloc[1])
    assert out.iloc[2] == pytest.approx(2.0)  # (1+2+3)/3
    assert out.iloc[4] == pytest.approx(4.0)  # (3+4+5)/3


def test_ema_recursive_formula():
    s = pd.Series([10.0, 20, 30, 40])
    out = ema(s, 2)
    alpha = 2 / (2 + 1)
    # min_periods=2 이므로 첫 유효값은 index 1
    expected = 10 * (1 - alpha) + 20 * alpha
    assert out.iloc[1] == pytest.approx(expected)


def test_rsi_all_gains_is_100():
    s = pd.Series(np.arange(1.0, 30.0))  # 단조 증가
    out = rsi(s, 14)
    assert out.dropna().iloc[-1] == pytest.approx(100.0)


def test_rsi_all_losses_is_zero():
    s = pd.Series(np.arange(30.0, 1.0, -1.0))  # 단조 감소
    out = rsi(s, 14)
    assert out.dropna().iloc[-1] == pytest.approx(0.0)


def test_rsi_stays_in_range():
    rng = np.random.default_rng(0)
    s = pd.Series(100 + np.cumsum(rng.normal(0, 1, 300)))
    out = rsi(s, 14).dropna()
    assert (out >= 0).all() and (out <= 100).all()


def test_bollinger_band_ordering():
    rng = np.random.default_rng(1)
    s = pd.Series(100 + np.cumsum(rng.normal(0, 1, 100)))
    b = bollinger(s, 20, 2.0).dropna()
    assert (b["upper"] >= b["mid"]).all()
    assert (b["mid"] >= b["lower"]).all()


def test_atr_is_positive():
    rng = np.random.default_rng(2)
    close = 100 + np.cumsum(rng.normal(0, 1, 200))
    df = pd.DataFrame({
        "high": close + 2, "low": close - 2, "close": close,
    })
    out = atr(df, 14).dropna()
    assert (out > 0).all()


def test_macd_hist_is_difference():
    rng = np.random.default_rng(3)
    s = pd.Series(100 + np.cumsum(rng.normal(0, 1, 200)))
    m = macd(s).dropna()
    assert np.allclose(m["hist"], m["macd"] - m["signal"])


def test_crossover_detects_single_bar():
    a = pd.Series([1.0, 1, 3, 3, 1])
    b = pd.Series([2.0, 2, 2, 2, 2])
    up = crossover(a, b)
    assert not up.iloc[1]
    assert up.iloc[2]       # 1 -> 3 이 2를 상향 돌파
    assert not up.iloc[3]   # 이미 위에 있으면 재발생 안 함

    down = crossunder(a, b)
    assert down.iloc[4]     # 3 -> 1 하향 돌파


def test_indicators_have_no_lookahead():
    """지표 t 값은 t 이후 데이터를 바꿔도 변하지 않아야 한다."""
    rng = np.random.default_rng(4)
    s = pd.Series(100 + np.cumsum(rng.normal(0, 1, 200)))

    full = rsi(s, 14)
    truncated = rsi(s.iloc[:150], 14)

    # 앞부분 150개는 동일해야 한다
    pd.testing.assert_series_equal(
        full.iloc[:150], truncated, check_names=False
    )
