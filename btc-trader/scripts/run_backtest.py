#!/usr/bin/env python3
"""백테스트 실행.

    # 저장된 CSV로
    python scripts/run_backtest.py --csv data/KRW-BTC_1d.csv --strategy ma_cross

    # 데이터 없이 합성 데이터로 엔진만 확인
    python scripts/run_backtest.py --synthetic --strategy ma_cross

    # 전략 전부 비교
    python scripts/run_backtest.py --csv data/KRW-BTC_1d.csv --compare
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from btc_trader.backtest import BacktestEngine, compute  # noqa: E402
from btc_trader.config import BacktestConfig, FeeModel, RiskConfig  # noqa: E402
from btc_trader.data import synthetic, upbit  # noqa: E402
from btc_trader.strategies import STRATEGIES, build  # noqa: E402

# 봉 단위 -> 1년치 봉 개수 (연율화용)
BARS_PER_YEAR = {
    "1m": 525_600, "3m": 175_200, "5m": 105_120, "15m": 35_040,
    "30m": 17_520, "60m": 8_760, "240m": 2_190, "1d": 365, "1w": 52,
}


def main() -> int:
    p = argparse.ArgumentParser(description="백테스트")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--csv", help="fetch_data.py로 받은 CSV 경로")
    src.add_argument("--synthetic", action="store_true", help="합성 데이터 사용")

    p.add_argument("--strategy", default="ma_cross", choices=sorted(STRATEGIES))
    p.add_argument("--compare", action="store_true", help="모든 전략 비교")
    p.add_argument("--interval", default="1d", help="연율화 기준 봉 단위")
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--position-pct", type=float, default=0.3, help="1회 투입 비율")
    p.add_argument("--stop-loss", type=float, default=0.03, help="손절 %% (0이면 없음)")
    p.add_argument("--take-profit", type=float, default=0.0, help="익절 %% (0이면 없음)")
    p.add_argument("--fee", type=float, default=0.0005, help="편도 수수료율")
    p.add_argument("--slippage-bp", type=float, default=5.0)
    p.add_argument("--json-out", default=None, help="지표를 JSON으로 저장")
    args = p.parse_args()

    # --- 데이터 ---
    if args.synthetic:
        df = synthetic.make_ohlcv(bars=800)
        label = "합성 데이터 (실제 시세 아님)"
    else:
        path = Path(args.csv)
        if not path.exists():
            print(f"파일이 없습니다: {path}", file=sys.stderr)
            print("먼저 실행하세요: python scripts/fetch_data.py", file=sys.stderr)
            return 1
        df = upbit.load_csv(str(path))
        label = str(path)

    config = BacktestConfig(
        initial_capital=args.capital,
        fees=FeeModel(fee_rate=args.fee, slippage_bp=args.slippage_bp),
        risk=RiskConfig(
            position_pct=args.position_pct,
            stop_loss_pct=args.stop_loss or None,
            take_profit_pct=args.take_profit or None,
        ),
        bars_per_year=BARS_PER_YEAR.get(args.interval, 365),
    )

    print("=" * 68)
    print(f"데이터   : {label}")
    print(f"기간     : {df.index[0]} ~ {df.index[-1]}  ({len(df):,} 봉)")
    print(f"수수료   : 편도 {args.fee * 100:.3f}%  슬리피지 {args.slippage_bp:.1f}bp")
    print(f"투입비율 : {args.position_pct * 100:.0f}%   손절 {args.stop_loss * 100:.1f}%")
    print("=" * 68)

    # 'hold'는 비교 기준선이다. 손절이나 부분투입을 적용하면
    # 더 이상 '단순 보유'가 아니게 되어 비교가 무의미해진다.
    # 그래서 전액 투입 + 손절 없음으로 따로 돌린다.
    benchmark_config = BacktestConfig(
        initial_capital=args.capital,
        fees=config.fees,
        risk=RiskConfig(
            position_pct=1.0,
            stop_loss_pct=None,
            take_profit_pct=None,
            daily_loss_limit_pct=None,
        ),
        bars_per_year=config.bars_per_year,
    )

    names = sorted(STRATEGIES) if args.compare else [args.strategy]
    results = {}

    for name in names:
        strategy = build(name)
        if len(df) < strategy.warmup + 10:
            print(f"\n[{name}] 데이터 부족 (워밍업 {strategy.warmup}봉 필요) — 건너뜀")
            continue

        is_benchmark = name == "hold"
        engine = BacktestEngine(benchmark_config if is_benchmark else config)
        result = engine.run(df, strategy)
        metrics = compute(
            result, args.capital,
            (benchmark_config if is_benchmark else config).bars_per_year,
        )
        results[name] = metrics

        suffix = "  ← 기준선 (전액투입·손절없음)" if is_benchmark else ""
        print(f"\n[{name}] {strategy.describe()}{suffix}")
        print(metrics.format())

    if args.compare and results:
        print("\n" + "=" * 68)
        print("요약 (수익률 / MDD / 샤프 / 거래수)")
        print("=" * 68)
        ranked = sorted(results.items(), key=lambda kv: -kv[1].total_return_pct)
        for name, m in ranked:
            print(
                f"  {name:<10} {m.total_return_pct:>+9.2f}%  "
                f"{m.max_drawdown_pct:>8.2f}%  {m.sharpe:>6.2f}  {m.num_trades:>4}회"
            )
        print("\n  * 'hold'(단순 보유)를 못 이기는 전략은 쓸 이유가 없습니다.")

    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(
            json.dumps({k: v.to_dict() for k, v in results.items()}, indent=2),
            encoding="utf-8",
        )
        print(f"\nJSON 저장: {args.json_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
