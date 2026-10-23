# Demo inputs (all fictional)

Test and demo inputs for the homeowner wizard. Everything here is made up and says so on the file itself: no real person, company or listing. Regenerate with `python assets/demo/make_demo_assets.py assets/demo`.

The "expected" column is the ground truth for checking the extraction missions. The LLM returns these raw values only; every conversion (m³ → kWh, kWh/m² → kWh a year) happens in the engine.

| File | Wizard step | What it is | Expected extraction |
| --- | --- | --- | --- |
| `house_persona_en.txt`, `house_persona_de.txt` | 1 · house text | the demo persona, English and German | year 1972 · living area 140 m² · terraced · renovation partly (windows 2015, roof insulated) · gas · 18,000 kWh a year · 3 people · 10 radiators · size: "the big flat ones" → large, low confidence |
| `house_conflict_en.txt` | 1 · house text | disagrees with the demo bill | year 1985 · 120 m² · detached · **oil** (the bill says gas → conflict, step 4 asks) · 4 people · never renovated, "as far as I know" → low confidence |
| `house_minimal_en.txt` | 1 · house text | too little to go on | about 150 m² · radiators · year empty (never guessed from "old") → yellow "can't tell yet", step 4 asks for the year |
| `bill_demo_gas_2025.pdf` | 3 · bill | text PDF of a gas bill | gas · 01.01.2025-31.12.2025 · 1,651 m³ · Zustandszahl 0.9523 · Brennwert 11.450 kWh/m³ · printed 18,002 kWh · total €2,462.12 (display only) · new monthly payment €205 |
| `bill_demo_gas_2025_photo.jpg` | 3 · bill | the same bill as a tilted phone photo | same values; tests the photo path |
| `listing_demo_reihenhaus_1994.png` | 3 · listing | a fictional sale listing, no platform branding | terraced (Reihenmittelhaus) · 128 m² · 5 rooms · year 1994 · Verbrauchsausweis · 128 kWh/(m²·a) · gas · central heating · class D · windows renewed 2012 → partly renovated |
| `../../data/pipe_photos/*` | 2 · radiator | the organiser's installer-labelled photos | see `data/pipe_photos/labels.json`; 07 must come back "unknown" |

Engine notes for the listing: a certificate's kWh/(m²·a) refers to its reference area A_N, not the living area. Without A_N, the certificate rules estimate it as 1.2 × living area (1.35 for a one- or two-family house with a heated basement), so 128 kWh/(m²·a) × ~154 m² ≈ 19,700 kWh a year including hot water (show it as a range, low confidence).

Not here, because this workspace can't download from those sites:
- an exterior photo of a house: take one yourself (any house, no people or number plates) and add it to `samples/` (gitignored) or here if it shows nothing private;
- the real Stadtwerke München sample bill (link in `CLAUDE.md` → "Photo inputs"), if you want a real bill layout next to the fictional one.
