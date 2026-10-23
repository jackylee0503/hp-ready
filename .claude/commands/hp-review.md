---
description: Hand a physics/principles review to a separate agent that has not seen the work
---

Spawn one general-purpose subagent with the brief below. Do not pass the main session's context; it should look only at the files.

"Review schema.py, loader.py, engine.py, calibrate.py, extract.py and app.py against CLAUDE.md.
- Principles 1-7: places where the LLM produces verdicts or numbers, numbers outside the fixed assumptions, red without a reason and a path to yellow
- Physics: units (kWh vs kW, °C vs K), direction of the radiator exponent, DHW subtraction, Hs/Hi efficiency basis, cost formula matches the fixed assumptions, best_color = colour of the Monte Carlo p50
- Organiser alignment (docs/challenge/): η 0.88 by default and 1,000 kWh hot water per person; both heating-load methods shown with their range; colours per the organiser meanings (unclear → yellow, never red; red only for an obstacle); confirmed single-pipe never green; mixed heating uses the radiator circuit; open_checks present and always lists exact heating load, electrical capacity and the outdoor-unit spot; cost above 60 °C shown as a lower bound at JAZ 2.8
- Interface contract: signatures that differ from CLAUDE.md
- Demo risk: API or file calls without try/except, paths with no cache fallback, Streamlit reruns that call the API again
Report findings by severity (breaks demo / loses points / minor), each as file:line plus a one-line fix. Do not edit anything."

When the result comes back, ask the user (in Korean) whether to fix the "breaks demo" items right away.

$ARGUMENTS
