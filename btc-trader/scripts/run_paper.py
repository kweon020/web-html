#!/usr/bin/env python3
"""실시간 페이퍼 트레이딩 (실제 주문 없음).

    python scripts/run_paper.py --strategy ma_cross --interval 60m

Ctrl+C로 중단. 포지션은 data/paper_state.json에 저장되어 재시작해도 유지된다.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from btc_trader.broker import PaperBroker  # noqa: E402
from btc_trader.config import FeeModel, RiskConfig  # noqa: E402
from btc_trader.live.paper_runner import PaperRunner  # noqa: E402
from btc_trader.strategies import STRATEGIES, build  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="페이퍼 트레이딩")
    p.add_argument("--strategy", default="ma_cross", choices=sorted(STRATEGIES))
    p.add_argument("--market", default="KRW-BTC")
    p.add_argument("--interval", default="60m")
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--position-pct", type=float, default=0.3)
    p.add_argument("--stop-loss", type=float, default=0.03)
    p.add_argument("--poll", type=float, default=30.0, help="시세 확인 주기(초)")
    p.add_argument("--state", default="data/paper_state.json")
    p.add_argument("--once", action="store_true", help="한 번만 실행하고 종료")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
    )

    broker = PaperBroker(
        initial_cash=args.capital,
        fees=FeeModel(),
        state_path=args.state,
    )
    runner = PaperRunner(
        strategy=build(args.strategy),
        broker=broker,
        market=args.market,
        interval=args.interval,
        risk=RiskConfig(
            position_pct=args.position_pct,
            stop_loss_pct=args.stop_loss or None,
        ),
        poll_seconds=args.poll,
    )

    print("─" * 60)
    print("  페이퍼 트레이딩 — 실제 주문은 나가지 않습니다")
    print("─" * 60)

    if args.once:
        runner.run_once()
    else:
        runner.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
