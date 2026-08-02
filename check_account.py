"""Alpaca 모의계좌(Paper) 연결 확인 스크립트.

.env 에서 키를 읽어 계좌 정보를 한 번만 조회한다.
- 주문은 절대 넣지 않는다 (조회 전용).
- 실계좌(api.alpaca.markets)에는 접속하지 않는다 (paper=True 고정).
- API 키/시크릿 값은 어떤 경우에도 화면에 출력하지 않는다.
"""

import os
import sys

from dotenv import load_dotenv

PAPER_HOST = "paper-api.alpaca.markets"


def mask(value: str) -> str:
    """키가 '읽혔는지'만 보여주고 값 자체는 숨긴다."""
    if not value:
        return "(없음)"
    return f"(길이 {len(value)}자, 값 숨김)"


def main() -> int:
    load_dotenv()

    api_key = os.getenv("ALPACA_API_KEY", "").strip()
    secret_key = os.getenv("ALPACA_SECRET_KEY", "").strip()

    print("1) .env 에서 키 읽기")
    print(f"   ALPACA_API_KEY    : {mask(api_key)}")
    print(f"   ALPACA_SECRET_KEY : {mask(secret_key)}")

    if not api_key or not secret_key:
        print()
        print("[실패] .env 에 ALPACA_API_KEY / ALPACA_SECRET_KEY 가 없습니다.")
        print("       .env.example 을 .env 로 복사한 뒤 모의계좌 키를 넣어주세요.")
        print("       키 발급: https://app.alpaca.markets/paper/dashboard/overview")
        return 1

    from alpaca.trading.client import TradingClient

    # paper=True 이면 SDK 가 paper-api.alpaca.markets 로만 접속한다.
    client = TradingClient(api_key, secret_key, paper=True)

    # 실계좌 주소로 새어나가지 않았는지 실제 접속 전에 확인한다.
    # _base_url 은 BaseURL Enum 이므로 .value 로 실제 주소를 꺼낸다.
    raw_base_url = getattr(client, "_base_url", "")
    base_url = str(getattr(raw_base_url, "value", raw_base_url))
    print()
    print(f"2) 접속 대상 확인: {base_url}")
    if PAPER_HOST not in base_url:
        print(f"[중단] 모의계좌 주소({PAPER_HOST})가 아니라 접속하지 않습니다.")
        return 1

    print()
    print("3) 계좌 조회 (조회 전용, 주문 없음)")
    try:
        account = client.get_account()
    except Exception as exc:  # 네트워크/인증 오류를 초보자도 읽을 수 있게
        message = str(exc)
        print(f"[실패] 계좌 조회 중 오류: {type(exc).__name__}: {message}")
        if "Proxy" in type(exc).__name__ or "proxy" in message.lower():
            print("       원인: 네트워크(프록시)가 paper-api.alpaca.markets 접속을 막았습니다.")
            print("       조치: 방화벽/프록시 없는 네트워크에서 다시 실행하세요. 키 문제가 아닙니다.")
        elif "401" in message or "403" in message:
            print("       원인: 인증 실패. 키가 틀렸거나 실계좌 키를 넣은 경우입니다.")
            print("       조치: Alpaca Paper 대시보드에서 키를 다시 발급받아 .env 에 넣으세요.")
        else:
            print("       조치: 인터넷 연결과 .env 의 키 값을 확인한 뒤 다시 실행하세요.")
        return 1

    print(f"   계좌 상태   : {account.status}")
    print(f"   계좌 번호   : {account.account_number}")
    print(f"   통화        : {account.currency}")
    print(f"   현금        : {account.cash}")
    print(f"   매수 가능   : {account.buying_power}")
    print(f"   자산 총액   : {account.portfolio_value}")
    print(f"   거래 정지   : {account.trading_blocked}")

    status = str(account.status)
    if "ACTIVE" not in status:
        print()
        print(f"[실패] 계좌 상태가 ACTIVE 가 아닙니다: {status}")
        return 1

    print()
    print("[성공] 모의계좌 연결 및 잔고 조회 완료 (상태: ACTIVE)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
