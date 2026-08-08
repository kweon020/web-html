# Pixel Agents 설정 (로컬 머신 전용)

[Pixel Agents](https://github.com/pixel-agents-hq/pixel-agents)는 Claude Code 세션을
픽셀아트 캐릭터로 시각화합니다. 에이전트가 코드를 쓰면 타이핑하고, 파일을 찾으면 읽는 동작을 하고,
입력을 기다리면 말풍선을 띄웁니다.

> **먼저 알아둘 것**: Pixel Agents는 **로컬 머신의 Claude Code 세션만** 봅니다.
> claude.ai/code 같은 원격 클라우드 세션은 훅 연결도 없고 로컬 `~/.claude/projects/`에
> 트랜스크립트도 남지 않으므로 **절대 나타나지 않습니다.** 이건 설정 문제가 아니라 구조적 한계입니다.
> 픽셀 오피스로 보고 싶다면 이 레포를 로컬에 clone하고 로컬에서 Claude Code를 실행하세요.

## 설치

경로는 둘 중 **하나만** 고릅니다.

### A. VS Code 확장 (권장)

1. VS Code 버전 확인 — **1.105.0 이상** 필요 (Help → About)
2. Marketplace 또는 Open VSX에서 `Pixel Agents` 검색 → Install
3. 이 레포를 clone한 폴더를 VS Code로 열기
4. 터미널에서 Claude Code 실행
5. Pixel Agents 패널 열기

### B. 독립 실행 CLI

```bash
node -v                      # v20 이상 필요
cd /path/to/web-html
npx pixel-agents             # 또는: npm i -g pixel-agents && pixel-agents
```

## 감지 방식

기본값인 **Hooks 모드**를 그대로 씁니다. Claude Code의 `SessionStart` / `PreToolUse` /
`PermissionRequest` / `Stop` 이벤트를 받아서 실시간으로 반영합니다.

훅이 안 붙으면 **Heuristic 모드**로 자동 폴백해 `~/.claude/projects/`의 JSONL 트랜스크립트를
스캔합니다. 느리고 정보가 적지만 아무것도 안 보이는 것보다는 낫습니다.

설정/상태는 `~/.claude/`와 `~/.pixel-agents/`에 저장됩니다. **이 레포에 커밋하지 않습니다.**

## 서브에이전트

`code-reviewer` 같은 에이전트를 서브에이전트로 호출하면 부모 세션에 연결된 별도 캐릭터가 생깁니다.
단, 캐릭터는 **활동 상태만** 보여줍니다 — 리뷰 내용이나 판단 이유는 터미널/트랜스크립트에서 확인해야 합니다.

설치만 해둔 에이전트는 보이지 않습니다. **실제로 호출된 에이전트만** 캐릭터가 생깁니다.

## 안 보일 때 확인 순서

1. **Windows + WSL 경로 불일치** — Claude Code는 WSL에서 돌고 스캐너는 Windows쪽
   `C:\Users\...\.claude\projects\`를 보고 있는 경우. 가장 흔한 원인입니다.
2. **훅 설정 덮어쓰기** — 다른 Claude Code 확장이 이미 훅을 등록해뒀다면
   `settings.json`의 `hooks` 항목이 append가 아니라 overwrite 되면서 Pixel Agents 항목이 사라질 수 있습니다.
   이벤트별로 항목이 여러 개 남아있는지 확인하세요.
3. **버전** — VS Code < 1.105.0, Node < 20
4. **터미널 불일치** — VS Code 확장이 감시하지 않는 터미널에서 Claude Code를 실행한 경우
