"""업비트 공개 시세 API 클라이언트.

공개 캔들 API는 인증이 필요 없다. 즉 API 키 없이도 백테스트 데이터를 받을 수 있다.
주문/잔고 조회에만 키가 필요하다.

Rate limit: 업비트 공개 API는 초당 10회, 분당 600회 수준이다.
넉넉하게 간격을 두고 호출한다.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import pandas as pd
import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://api.upbit.com/v1"

# 업비트가 한 번에 주는 최대 캔들 개수
MAX_COUNT = 200

# 지원하는 봉 단위 -> API 경로
_UNIT_PATHS = {
    "1m": "candles/minutes/1",
    "3m": "candles/minutes/3",
    "5m": "candles/minutes/5",
    "15m": "candles/minutes/15",
    "30m": "candles/minutes/30",
    "60m": "candles/minutes/60",
    "240m": "candles/minutes/240",
    "1d": "candles/days",
    "1w": "candles/weeks",
}


class UpbitDataError(RuntimeError):
    """시세 조회 실패."""


def _request(path: str, params: dict, *, max_retries: int = 4) -> list[dict]:
    """지수 백오프로 재시도하는 GET."""
    url = f"{BASE_URL}/{path}"
    delay = 1.0

    for attempt in range(max_retries + 1):
        try:
            resp = requests.get(url, params=params, timeout=15)
        except requests.RequestException as exc:
            if attempt == max_retries:
                raise UpbitDataError(
                    f"업비트 접속 실패: {exc}. 네트워크/방화벽을 확인하세요."
                ) from exc
            logger.warning("요청 실패 (%s), %.1f초 후 재시도", exc, delay)
            time.sleep(delay)
            delay *= 2
            continue

        # 429 = rate limit. 기다렸다 다시.
        if resp.status_code == 429:
            if attempt == max_retries:
                raise UpbitDataError("rate limit에 계속 걸립니다. 간격을 늘리세요.")
            logger.warning("rate limit, %.1f초 대기", delay)
            time.sleep(delay)
            delay *= 2
            continue

        if resp.status_code != 200:
            raise UpbitDataError(
                f"업비트 응답 {resp.status_code}: {resp.text[:200]}"
            )

        return resp.json()

    raise UpbitDataError("재시도 횟수를 초과했습니다.")


def fetch_candles(
    market: str = "KRW-BTC",
    interval: str = "1d",
    count: int = 200,
    to: datetime | None = None,
) -> pd.DataFrame:
    """캔들 최대 200개를 한 번에 가져온다.

    to를 주면 그 시점 '이전' 캔들을 가져온다(과거로 거슬러 올라갈 때 사용).
    """
    if interval not in _UNIT_PATHS:
        raise ValueError(
            f"지원하지 않는 봉 단위: {interval}. 가능한 값: {list(_UNIT_PATHS)}"
        )

    params: dict = {"market": market, "count": min(count, MAX_COUNT)}
    if to is not None:
        # 업비트는 UTC ISO8601을 기대한다
        params["to"] = to.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    raw = _request(_UNIT_PATHS[interval], params)
    return _to_dataframe(raw)


def fetch_history(
    market: str = "KRW-BTC",
    interval: str = "1d",
    bars: int = 1000,
    pause: float = 0.15,
) -> pd.DataFrame:
    """200개씩 나눠 받아 원하는 개수만큼 과거 데이터를 채운다."""
    frames: list[pd.DataFrame] = []
    remaining = bars
    cursor: datetime | None = None

    while remaining > 0:
        chunk = fetch_candles(
            market=market,
            interval=interval,
            count=min(remaining, MAX_COUNT),
            to=cursor,
        )
        if chunk.empty:
            logger.info("더 이상 과거 데이터가 없습니다.")
            break

        frames.append(chunk)
        remaining -= len(chunk)
        # 다음 요청은 이번에 받은 가장 오래된 캔들 '이전'부터
        cursor = chunk.index[0].to_pydatetime()

        if remaining > 0:
            time.sleep(pause)  # rate limit 예방

    if not frames:
        return _empty_frame()

    df = pd.concat(frames).sort_index()
    # 경계에서 중복이 생길 수 있다
    df = df[~df.index.duplicated(keep="first")]
    return df


def _to_dataframe(raw: list[dict]) -> pd.DataFrame:
    """업비트 응답 -> OHLCV DataFrame (시간 오름차순)."""
    if not raw:
        return _empty_frame()

    df = pd.DataFrame(raw)
    df["timestamp"] = pd.to_datetime(df["candle_date_time_kst"])

    out = (
        df.rename(
            columns={
                "opening_price": "open",
                "high_price": "high",
                "low_price": "low",
                "trade_price": "close",
                "candle_acc_trade_volume": "volume",
            }
        )[["timestamp", "open", "high", "low", "close", "volume"]]
        .set_index("timestamp")
        .sort_index()
        .astype("float64")
    )
    return out


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["open", "high", "low", "close", "volume"],
        index=pd.DatetimeIndex([], name="timestamp"),
        dtype="float64",
    )


def save_csv(df: pd.DataFrame, path: str) -> None:
    df.to_csv(path)
    logger.info("%d개 캔들을 %s에 저장했습니다.", len(df), path)


def load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.index.name = "timestamp"
    return df.astype("float64")
