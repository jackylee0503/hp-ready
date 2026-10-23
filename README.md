# HP-Ready Triage

**An honest first heat-pump answer for a homeowner in under three minutes, and, from the same result, an installer prep sheet for nuuEnergy.**

Built for WATT THE HACK Munich 2026, challenge #4 by nuuEnergy: *"Can AI tell whether a home is ready for clean heating?"* The organiser's pages are in `docs/challenge/`.

## What it does

For each home it returns:
- a traffic light **with probabilities**, using the organiser's meanings: 🟢 likely suitable / 🟡 potentially suitable, checks remain or too little data / 🔴 an obstacle in the data we have,
- **what's still open**: what we can't tell from the data, and what a technician must check on site (missing data is "can't tell yet", never a red),
- the required flow temperature and heating load as ranges (area-and-age method and bill method side by side),
- contradictions it found in the data and which source it trusted,
- an installer prep sheet: remote quote / visit with parts / hold, radiators to swap, valves, checks on site,
- running cost now vs with a heat pump (challenge price assumptions only).

## How it decides

The LLM only **reads**: it pulls facts out of free-text notes (wood stove, unused floor, insulation work) and quotes the sentence it used. A physics engine **decides**:

`area × W/m² by age × k` → heating load → radiator output (EN 442) → required flow temperature → traffic light, with Monte Carlo over the unknowns. One parameter (k) is calibrated on the three dev buildings.

## Run it

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Then open the local URL it prints in any browser.

Optional: put `ANTHROPIC_API_KEY = "sk-ant-..."` in `.streamlit/secrets.toml` for live notes extraction. Without it the app uses `data/notes_cache.json`, then a keyword fallback.

## Repo map

| Path | What |
| --- | --- |
| `app.py` | Streamlit app: 🏠 Homeowner, 📊 Evaluation, 🔧 Installer |
| `schema.py`, `loader.py`, `engine.py`, `calibrate.py`, `extract.py` | data model, data loading, physics engine, calibration, photo extraction (later) |
| `data/` | organiser data (anonymised): 3 dev + 2 evaluation buildings, labelled pipe-system photos, the notes cache |
| `CLAUDE.md` | build spec for the coding agent |
| `docs/challenge/` | the organiser's challenge pages (mission, guardrails, data, judging) |
| `docs/DESIGN.md` | design, data findings, decisions, domain primer |
| `docs/PITCH.md` | pitch script and demo order |

## Status

Pre-event: plan reviewed and aligned to the organiser's pages, dev data analysed (k = 1.01, all 3 dev verdicts reproduced), evaluation inputs (B-04, B-05) in `data/`, Cloud deploy shell live (optional; the demo runs locally). Code is written during the event.
