# Pitch: HP-Ready Triage (target 4 minutes)

Adjust to the real slot length on the day. If only 3 minutes: drop step 4 of the demo and B-01 in step 2.
Numbers below are first estimates from the spec; replace them with the engine's output on the day.

## 0:00-0:30 Hook

> "'Would a heat pump even work in my home?' Millions of homeowners never get past that question, and today only a technician's visit answers it.
> We built a tool that gives an honest first answer in under three minutes, from the bill and a few facts: green, yellow or red, why, and what a technician still has to check.
> And for nuuEnergy, whose scarcest resource is the installer's time, the same answer becomes the installer's prep sheet."

## 0:30-1:00 How it works (one sentence each)

> "The AI reads what the homeowner gave us, including messy notes, and quotes what it used.
> Physics decides: heating load from area and age, radiator output from manufacturer tables, the flow temperature the house needs.
> Where we don't know, we say so with probabilities. Missing data isn't a no, and nothing is made up."

## 1:00-3:15 Live demo

1. **🏠 Homeowner (≈70 s).** Enter the persona with four taps plus the bill numbers, well under three minutes. "The homeowner gets one sentence, a probability and what's still open, not a false promise." Press the next-step button: "Getting a quote today means hours of forms. Here the request is already filled in; they add a name, a phone number and a postcode." (Quote a number of hours only if you measured it.) Clear the build year: "Missing data isn't a no. Yellow, 'we can't tell yet', and the one thing that settles it."
2. **📊 Evaluation (≈75 s).** "Your three dev houses: our heating load vs yours, all three verdicts reproduced with a single calibrated number. And your two evaluation houses:"
   B-04: "Single-pipe system, and with today's radiators it needs above 60 °C, even if they are all large. That's an obstacle, not missing data: red, here is what gets it to yellow and what the technician checks on the loop."
   B-05: "Your data contradicts itself: 125 m² but 14 rooms, and a bill 76 % above what size and age say. We trust size and age, widen the range and ask whether all heated area is included."
   If time: B-01, "the bill says about 2.4 kW, size and age say about 11 kW", and the AI fact for B-02: "'A wood stove is used all winter.' The engine then treats the gas bill as a lower bound."
3. **🔧 Installer (≈30 s).** "Same result, installer's view. B-04: hold, with the loop checks. B-03: visit with parts, about N radiators, 12 valves, hydraulic balancing, check the unused top floor."
4. **Rechenweg (≈15 s, optional).** Open the expander: every number, every assumption, both heating-load methods side by side.

## 3:15-3:45 Why this matters for nuuEnergy

> "We don't cancel site visits. We make them short and precise.
> Green with high confidence: quote remotely. Yellow or uncertain: go, with the right parts. Red: don't drive, here's what would change it."

## 3:45-4:00 Next step

> "Phase 2: every visit nuuEnergy does becomes training data. The one number we calibrate today gets better with every house."

## Likely questions

- **"Why not let the AI decide?"** It can't show its work and it can't tell you how sure it is. We need both for a decision that sends a person out.
- **"Your dev set is only three houses."** That's why we fit one number, show leave-one-out error, and report probabilities. Two of the three sit right on the 55/60 °C edges, and we say so.
- **"Single-pipe isn't a deal-breaker, why is B-04 red?"** Red means an obstacle with today's radiators, not "never". We show exactly what gets it to yellow, and a confirmed single-pipe system never gets a green without an on-site check.
- **"What if the homeowner doesn't know something?"** Then it's yellow, "we can't tell yet", plus the one question that would settle it. Missing data never makes a house red.
- **"How did you get radiator output without photos?"** Manufacturer EN 442 tables, size unknown → we sample sizes and show the spread. A photo (in the homeowner flow) narrows it.
- **"What about cost?"** Only the challenge's fixed prices and JAZ values. We never invent installation cost or subsidies.

## Checklist before going on stage

- [ ] Local `streamlit run app.py` open in the browser (primary path)
- [ ] Cloud link, only if used: opened 10 minutes before (cold start), incognito link works
- [ ] Screen recording of the happy path ready
- [ ] Persona inputs written down, homeowner flow timed under 3 minutes
- [ ] B-04 / B-05 numbers in this script replaced with the engine's output
