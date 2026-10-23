---
description: 스모크 체크 — 지금 상태가 데모 가능한지 확인하고, 통과하면 커밋
---

순서대로 실행하고 결과만 짧게 보고해. 고치지는 말고, 실패하면 원인 한 줄 + 수정안만.

1. `python engine.py` — 예시 집 결과와 Rechenweg가 나오는지, 숫자가 CLAUDE.md 도메인 배경의 감과 크게 어긋나지 않는지 (공급온도 35~75°C, 난방부하 3~30 kW 범위 밖이면 의심)
2. `python -c "from loader import load_buildings; print(len(load_buildings()))"` — data/가 있으면 5채 로드되는지
3. `python calibrate.py` 가 있으면 실행 — 3채 오차와 leave-one-out 표
4. `streamlit run app.py --server.headless true --server.port 8599` 를 백그라운드로 띄워 10초 내 에러 없이 뜨는지(`/_stcore/health` = ok) 확인 후 **그 PID로 종료** (프로세스 남기지 말 것)
5. 결정론: 같은 입력으로 evaluate 두 번 → 결과 동일한지
6. CLAUDE.md 우선순위 기준으로 지금 어디까지 됐는지 체크리스트 (P0-a / P0-b / P1)

전부 통과하면 `git status`로 변경 파일을 보고, **이번 작업에서 바꾼 파일만 이름으로** `git add <파일들> && git commit -m "check: <한 줄 요약>"`. `git add -A` 금지 (`samples/` 원본 사진·`.streamlit/secrets.toml` 섞임 방지).
