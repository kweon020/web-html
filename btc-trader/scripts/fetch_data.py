#!/usr/bin/env python3
"""업비트에서 과거 캔들을 받아 CSV로 저장한다.

    python scripts/fetch_data.py --interval 1d --bars 1500
    python scripts/fetch_data.py --interval 60m --bars 2000 --out data/btc_1h.csv

API 키가 필요 없다 (공개 시세 API).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from btc_trader.data import upbit  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="업비트 캔들 수집")
    p.add_argument("--market", default="KRW-BTC", help="마켓 코드 (기본 KRW-BTC)")
    p.add_argument(
        "--interval", default="1d",
        choices=["1m", "3m", "5m", "15m", "30m", "60m", "240m", "1d", "1w"],
    )
    p.add_argument("--bars", type=int, default=1000, help="가져올 봉 개수")
    p.add_argument("--out", default=None, help="저장 경로 (기본 data/<market>_<interval>.csv)")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    out = Path(args.out) if args.out else Path("data") / f"{args.market}_{args.interval}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)

    print(f"{args.market} {args.interval} 봉 {args.bars}개를 받는 중...")
    try:
        df = upbit.fetch_history(
            market=args.market, interval=args.interval, bars=args.bars
        )
    except upbit.UpbitDataError as exc:
        print(f"\n실패: {exc}", file=sys.stderr)
        print("네트워크 또는 방화벽 문제일 수 있습니다.", file=sys.stderr)
        return 1

    if df.empty:
        print("받은 데이터가 없습니다.", file=sys.stderr)
        return 1

    upbit.save_csv(df, str(out))
    print(f"\n저장 완료: {out}")
    print(f"  기간: {df.index[0]} ~ {df.index[-1]}")
    print(f"  봉 개수: {len(df):,}")
    print(f"  종가 범위: {df['close'].min():,.0f} ~ {df['close'].max():,.0f} 원")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
