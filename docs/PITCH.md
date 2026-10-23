# Pitch: HP-Ready Triage (target 4 minutes)

Adjust to the real slot length on the day. If only 3 minutes: drop step 4 of the demo.

## 0:00-0:30 Hook

> "In Germany, the scarcest resource isn't energy. It's the installer's time.
> Today nuuEnergy has to send someone to almost every house just to find out whether a heat pump can work there.
> We built a tool that answers that before anyone drives out, and tells the installer what to bring if they go."

## 0:30-1:00 How it works (one sentence each)

> "The AI reads what the homeowner gave us, including messy notes, and quotes what it used.
> Physics decides: heating load from area and age, radiator output from manufacturer tables, the flow temperature the house needs.
> Where we don't know, we say so with probabilities. Nothing is made up."

## 1:00-3:15 Live demo

1. **📊 Evaluation (≈60 s).** "Here are your three dev houses: our heating load vs yours, and all three verdicts reproduced with a single calibrated number. Here are the two hidden houses, with ranges."
   Point at B-01: "Your data contradicts itself. The bill says about 3 kW, the house size and age say about 11 kW. We trust area and age, and we tell the installer to check usage and the LPG."
   Point at the AI facts: "B-02: 'A wood stove is used all winter.' The AI found it and quoted it; the engine then treats the gas bill as a lower bound."
2. **🔧 Installer (≈45 s).** B-03: "Visit with parts: about N radiators to upgrade, 12 valves, hydraulic balancing, and check the unused top floor. The installer leaves the depot knowing this."
3. **🏠 Homeowner (≈30 s).** Enter the persona by dropdowns. "The homeowner gets one sentence and a probability, not a false promise." Clear the build year: "If we don't know, we ask for the one thing that changes the answer."
4. **Rechenweg (≈15 s, optional).** Open the expander: every number, every assumption.

## 3:15-3:45 Why this matters for nuuEnergy

> "We don't cancel site visits. We make them short and precise.
> Green with high confidence: quote remotely. Yellow or uncertain: go, with the right parts. Red: don't drive, here's what would change it."

## 3:45-4:00 Next step

> "Phase 2: every visit nuuEnergy does becomes training data. The one number we calibrate today gets better with every house."

## Likely questions

- **"Why not let the AI decide?"** It can't show its work and it can't tell you how sure it is. We need both for a decision that sends a person out.
- **"Your dev set is only three houses."** That's why we fit one number, show leave-one-out error, and report probabilities. Two of the three sit right on the 55/60 °C edges, and we say so.
- **"How did you get radiator output without photos?"** Manufacturer EN 442 tables, size unknown → we sample sizes and show the spread. A photo (in the homeowner flow) narrows it.
- **"What about cost?"** Only the challenge's fixed prices. We never invent installation cost or subsidies.

## Checklist before going on stage

- [ ] Cloud app opened 10 minutes before (cold start), incognito link works
- [ ] Local `streamlit run app.py` ready as backup
- [ ] Screen recording of the happy path ready
- [ ] Persona inputs written down
