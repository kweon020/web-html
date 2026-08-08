"""기술적 지표 모음.

모든 함수는 pandas Series/DataFrame을 받아 같은 인덱스의 결과를 돌려준다.
중요: 어떤 지표도 미래 데이터를 참조하지 않는다(look-ahead 없음).
시점 t의 값은 t까지의 데이터만으로 계산된다.
"""

from __future__ import annotations

import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    """단순 이동평균."""
    return series.rolling(window=period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    """지수 이동평균.

    adjust=False로 재귀식(EMA_t = a*x_t + (1-a)*EMA_{t-1})을 쓴다.
    실시간 스트리밍에서 과거 전체를 다시 안 읽어도 같은 값이 나오게 하기 위함.
    """
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """RSI (Wilder 방식).

    Wilder의 평활은 alpha = 1/period 인 EMA와 같다.
    단순 rolling mean을 쓰는 구현이 많은데, 그건 원래 정의와 값이 다르다.
    """
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)

    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0.0, pd.NA)
    out = 100.0 - (100.0 / (1.0 + rs))
    # avg_loss == 0 이면 상승만 있었다는 뜻 -> RSI 100
    out = out.where(avg_loss != 0.0, 100.0)
    # avg_gain == 0 이면 하락만 있었다는 뜻 -> RSI 0
    out = out.where(avg_gain != 0.0, 0.0)
    return out.astype("float64")


def bollinger(
    series: pd.Series, period: int = 20, num_std: float = 2.0
) -> pd.DataFrame:
    """볼린저 밴드. mid/upper/lower 3개 컬럼을 돌려준다."""
    mid = sma(series, period)
    # ddof=0 (모집단 표준편차) — 대부분의 차트 프로그램이 이 방식을 쓴다
    std = series.rolling(window=period, min_periods=period).std(ddof=0)
    return pd.DataFrame(
        {
            "mid": mid,
            "upper": mid + num_std * std,
            "lower": mid - num_std * std,
        }
    )


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range. 손절 폭을 변동성에 비례시킬 때 쓴다.

    df는 high/low/close 컬럼을 가져야 한다.
    """
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)

    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)

    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def macd(
    series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.DataFrame:
    """MACD. macd/signal/hist 3개 컬럼."""
    macd_line = ema(series, fast) - ema(series, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return pd.DataFrame(
        {
            "macd": macd_line,
            "signal": signal_line,
            "hist": macd_line - signal_line,
        }
    )


def crossover(a: pd.Series, b: pd.Series) -> pd.Series:
    """a가 b를 아래에서 위로 뚫은 시점에 True.

    직전 봉과 현재 봉만 보므로 미래 참조가 없다.
    """
    return (a > b) & (a.shift(1) <= b.shift(1))


def crossunder(a: pd.Series, b: pd.Series) -> pd.Series:
    """a가 b를 위에서 아래로 뚫은 시점에 True."""
    return (a < b) & (a.shift(1) >= b.shift(1))
