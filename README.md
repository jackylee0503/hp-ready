# HP-Ready Triage

**Tell nuuEnergy which homes are heat-pump ready before an installer drives there, and what to bring if they go.**

Built for WATT THE HACK Munich 2026, challenge #4 by nuuEnergy: *"Can AI tell whether a home is ready for clean heating?"*

## What it does

For each home it returns:
- a traffic light (🟢 ready / 🟡 ready after swapping a few radiators / 🔴 not yet) **with probabilities**,
- the required flow temperature and heating load as ranges,
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

Optional: put `ANTHROPIC_API_KEY = "sk-ant-..."` in `.streamlit/secrets.toml` for live notes extraction. Without it the app uses `data/notes_cache.json`, then a keyword fallback.

## Repo map

| Path | What |
| --- | --- |
| `app.py` | Streamlit app: 📊 Evaluation, 🔧 Installer, 🏠 Homeowner |
| `schema.py`, `loader.py`, `engine.py`, `calibrate.py`, `extract.py` | data model, data loading, physics engine, calibration, photo extraction (later) |
| `data/` | organiser data (anonymised) and the notes cache |
| `CLAUDE.md` | build spec for the coding agent |
| `docs/DESIGN.md` | design, data findings, decisions, domain primer |
| `docs/PITCH.md` | pitch script and demo order |

## Status

Pre-event: plan reviewed, dev data analysed (k = 1.01, all 3 dev verdicts reproduced), Cloud deploy shell live. Code is written during the event.
