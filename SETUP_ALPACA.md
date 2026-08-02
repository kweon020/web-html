# Alpaca 모의계좌 연결 확인 (macOS / zsh)

## 1. 설치 여부 확인

```zsh
python3 --version      # 3.10 이상이면 OK
pip show alpaca-py     # "Package(s) not found" 면 아직 미설치
```

Python 이 없거나 3.10 미만이면: `brew install python@3.11`

## 2. 가상환경 + 설치

```zsh
cd <이 저장소 폴더>
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt      # alpaca-py, python-dotenv
```

설치 확인:

```zsh
python -c "import alpaca; print(alpaca.__version__)"
```

## 3. 모의계좌 키 넣기

1. https://app.alpaca.markets/paper/dashboard/overview 접속
2. 오른쪽 **Generate New Key** → API Key ID 와 Secret Key 를 복사
   (Secret 은 이때 한 번만 보여줍니다)
3. 키 파일 만들기:

```zsh
cp .env.example .env
open -e .env          # 두 줄에 복사한 값 붙여넣기
```

`.env` 는 `.gitignore` 에 있어 깃에 올라가지 않습니다.

## 4. 연결 확인

```zsh
python check_account.py
```

성공하면 계좌 상태가 `ACTIVE` 로 찍히고, 현금·매수가능금액·자산총액이 보입니다.
이 스크립트는 **조회만** 하고 주문은 넣지 않으며, `paper=True` 로 고정되어
실계좌(api.alpaca.markets)에는 접속하지 않습니다.

## 자주 나는 오류

| 증상 | 원인 | 조치 |
|---|---|---|
| `.env 에 ... 가 없습니다` | `.env` 미작성 | 3번 단계 다시 |
| `401` / `403` (Alpaca 응답) | 키 오타 또는 실계좌 키 사용 | Paper 대시보드에서 재발급 |
| `ProxyError` / 연결 실패 | 회사망·방화벽이 차단 | 다른 네트워크에서 실행 |
| `command not found: python` | 가상환경 미활성화 | `source .venv/bin/activate` |
