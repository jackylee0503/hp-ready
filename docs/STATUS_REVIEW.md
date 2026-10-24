# HP-Ready: Status Review (24 Oct)

**Verdict:** Past MVP. The full flow works and all 5 buildings get a result. The problem is the pitch, not the code: our main claim is saving installer time, but the installer view is hidden by default.

## Results (from `data/baseline_results.json`)

| Building | Verdict | P(green / yellow / red) | Flow temp p50 | Installer action |
| --- | --- | --- | --- | --- |
| B-01 (dev) | Green | 0.51 / 0.18 / 0.31 | 55 °C | Visit with parts |
| B-02 (dev) | Green | 1.00 / 0 / 0 | 37 °C | Visit with parts |
| B-03 (dev) | Yellow | 0.31 / 0.23 / 0.46 | 59 °C | Visit with parts |
| B-04 (eval) | Red | 0.01 / 0.09 / 0.90 | 73 °C | Hold |
| B-05 (eval) | Green | 0.68 / 0.08 / 0.24 | 50 °C | Visit with parts |

All 3 dev verdicts reproduced with one calibrated number (k = 1.01).

## Fix before the demo

1. **Show the installer view by default** (now only with `HP_SHOW_INSTALLER=1`). It is our core value.
2. **Borderline greens:** B-05 is green despite flagged contradictions; B-01 is green at 51 % vs 31 % red. When `boundary` is set, show yellow or "borderline".
3. **`image_rec2.py` (panel/garden) is not wired in.** Its docstring imports `site_checks`, the file is `image_rec2.py`. Wire it or drop it.
4. Don't claim 3 ML modules: `modules/calculation.py` is still a skeleton.
5. Put the numbers above into `docs/PITCH.md`.

## Our strength (one line)

The AI only reads (and quotes what it read); physics decides; every answer comes with probabilities, contradictions it found, and what a technician must still check.

## Pitch line

"We don't cancel site visits, we make them short and precise." Green → remote quote. Yellow → visit with the right parts. Red → don't drive. Don't quote % or hours saved; we haven't measured them.
