# Technical Guardrails

Four rules of thumb to get you started. Rough reference figures, not exact. **Honesty over precision:** if the data doesn't support a claim, say so and flag it.

### 1. Heating load (kW)

Two quick ways to estimate it. If you have both, show both, and show the range if they differ.

**a) Floor area × typical value per m², by building age:**

| Building | Heat load (W/m²) |
| --- | --- |
| Unrenovated, built before 1979 | 120-180 |
| Built in the 1980s-1990s | 80-120 |
| Renovated or built 2002+ | 40-60 |
| Low-energy house / new build | 15-40 |

**b) From consumption:**

1. Convert to kWh if needed: 1 litre of heating oil ≈ 10 kWh, 1 m³ of gas ≈ 10 kWh.
2. Useful heat ≈ consumption × 0.88 (the old boiler loses about 12 %).
3. Subtract hot water (the bill includes showers etc.): ~1,000 kWh per person per year.
4. ÷ ~2,000 full-load hours ≈ heat load in kW.

Above ~75 W/m², better windows or insulation may be worth it — a useful hint for the result.

### 2. Radiators

The key question: which flow temperature do the existing radiators need to keep the house warm? Heat pumps run efficiently up to about 55 °C; 55–60 °C still works, but with higher electricity consumption.

**How you turn this into green / yellow / red is up to you** – just make your logic transparent.

**Why higher temperatures cost more:** the hotter the water has to be, the harder the heat pump works. It needs more electricity to deliver the same amount of heat, so efficiency drops and operating costs go up. Many modern heat pumps can technically reach 60 °C or more, but it is the expensive way to run them. Your cost estimate should reflect this.

**Radiator output drops at lower temperatures:** at 55 °C a radiator delivers only about **half** of its rated output (usually stated for 75 °C). From the photo, estimate type and size — Type 11 / 22 / 33 = number of panels and fins — and check roughly whether the radiators can still cover the heat load.

Typical signals:

- **Underfloor heating** → good fit
- **Large or newer panel radiators** → usually fine at ≤ 55 °C
- **Small, old radiators or a single-pipe system (Einrohrheizung)** → flag as "needs checking"

### 3. Operating costs

**Heat pump:** useful heat ÷ efficiency × heat-pump electricity price

**Today:** annual consumption × current fuel price

**Efficiency (JAZ, Jahresarbeitszahl):** how many kWh of heat the heat pump makes from 1 kWh of electricity. You don't need to calculate it — **use these fixed values**, depending on the flow temperature from your radiator check:

| Heating system / flow temperature | JAZ to use |
| --- | --- |
| Underfloor heating (~35 °C) | 4.0 |
| Radiators up to 55 °C | 3.5 |
| Radiators 55–60 °C | 2.8 |

Please also use these fixed prices so all teams are comparable:

| Energy | Price for the challenge |
| --- | --- |
| ♨️ Heat-pump electricity | 26 ct/kWh |
| 🔥 Natural gas | 11 ct/kWh |
| 🛢️ Heating oil | 1.70 €/litre (≈ 17 ct/kWh) |

Show your assumptions openly in the result.

### 4. Always checked by a technician

Exact heat load, electrical capacity, and where the outdoor unit can go.

---

What does a gas bill look like? Here is a public sample bill from Stadtwerke München, the annual consumption in kWh is on the first page: [SWM sample bill (PDF)](https://www.swm.de/dam/doc/kundenservice/rechnung/musterrechnung-erklaerung.pdf)

---

## Key terms

- **Heating load (Heizlast):** how much heating power (kW) the house needs on the coldest day of the year. Determines how big the heat pump must be.
- **Flow temperature (Vorlauftemperatur):** temperature of the water going into the radiators. The lower, the more efficient the heat pump.
- **JAZ (Jahresarbeitszahl):** how many kWh of heat a heat pump delivers per kWh of electricity over a year. JAZ 3.5 = 1 kWh electricity becomes 3.5 kWh heat.
- **Full-load hours (Volllaststunden):** how many hours the heating would run at full power to deliver one year's heat. In Germany ~2,000 h. Annual heat ÷ full-load hours = heating load.
- **Boiler efficiency (Nutzungsgrad):** share of the gas or oil that actually ends up as heat. Older boilers: ~0.88.
- **Single-pipe vs. two-pipe system (Einrohr / Zweirohr):** in a two-pipe system each radiator has its own supply and return pipe — standard and fine. In a single-pipe system the radiators are connected in series, so the water cools down from one to the next — critical for a heat pump.
- **Radiator type (Typ 11 / 22 / 33):** first digit = number of panels, second digit = number of fin layers behind them. More panels and fins = more heat output. In a photo, look at the radiator from the side or top and count the panels.
- **Underfloor heating (Fußbodenheizung, FBH):** heating pipes in the floor. Works with very low flow temperatures (~35 °C) — ideal for heat pumps, but not required.
- More detail
    - **Ideal flow temperature:** ≤ 45 °C is ideal; up to ~55 °C is efficient; 55–60 °C works with higher electricity use.
    - **Full-load hours:** realistic range is ~1,800–2,100 hours per year.
    - **Myth-busting:** underfloor heating is **not** required; a full renovation is **not** required.
    - **Full technician checklist:** exact heat load (DIN EN 12831), room-by-room radiator sizing, electrical capacity & meter cabinet, hydraulics, outdoor-unit placement, sound and permits.