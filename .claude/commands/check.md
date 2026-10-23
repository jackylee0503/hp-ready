---
description: Smoke check — is the current state demo-ready? Commit if it passes
---

Run these in order and report results briefly (to the user in Korean). Do not fix anything; on failure give one line of cause + a proposed fix.

1. `python engine.py` — dev cases, the 2 evaluation cases and the example house print with a Rechenweg. Sanity: flow temperature 35-75 °C, heating load 3-30 kW, B-01 green, B-02 green and B-03 yellow (or "uncertain" including that colour); B-04 never green (single-pipe cap); B-05 uses the radiator circuit (mixed); a house with a core field removed comes out yellow "can't tell yet", never red.
2. `python -c "from loader import load_buildings; print(len(load_buildings()))"` — all buildings in `data/` load.
3. `python calibrate.py` if it exists — print k, the 3 dev errors and the leave-one-out table.
4. Start `streamlit run app.py --server.headless true --server.port 8599` in the background, confirm `/_stcore/health` returns ok within 10 s, then **kill that PID** (leave no process behind).
5. Determinism: `evaluate` on the same house twice → identical result.
6. Checklist of where we are against the priorities in CLAUDE.md (P0-a / P0-b / P0-c / P1).

If everything passes: look at `git status`, then `git add <only the files changed in this piece of work>` and `git commit -m "check: <one-line summary>"`. Never `git add -A` (keeps raw `samples/` photos and `.streamlit/secrets.toml` out).
