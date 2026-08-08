# web-html

생활코딩 WEB1 - HTML 실습 레포입니다.

## 프로젝트 성격

- 순수 정적 HTML. **빌드 스텝 없음, 프레임워크 없음, 패키지 매니저 없음.**
- 학습 순서: HTML → CSS → JavaScript → Git
- 목적은 "동작하는 결과물"이 아니라 **학습**입니다. 손으로 직접 써보는 과정 자체가 목적이므로,
  자동화·추상화·리팩터링 제안으로 그 과정을 건너뛰게 하지 마세요.

## 코드 작성 규칙

- 바닐라 HTML/CSS/JS만 사용합니다. React/Vue/번들러/전처리기 제안 금지.
- 학습 단계보다 앞서가지 않습니다. (CSS 안 배운 시점에 CSS 파일 분리 제안 X)
- 설명은 한국어로.

## 에이전트 사용

The Agency(msitarzewski/agency-agents) 에이전트는 **이름을 명시해서** 호출합니다.
설명 기반 자동 매칭에 맡기지 마세요 — 이 레포 규모에 과한 에이전트가 선택됩니다.

| 시점 | 에이전트 |
|---|---|
| CSS/JS 추가 후 리뷰 | `code-reviewer` |
| 커밋·브랜치 작업 | `git-workflow-master` |

필요해지면 그때 추가 (전역 설치, 이 레포에 커밋하지 않음):

```bash
./scripts/install.sh --tool claude-code --no-interactive --agent accessibility-auditor
```

오케스트레이터(`agents-orchestrator`)는 쓰지 않습니다. 이 규모에서는 사람이 오케스트레이터입니다.
