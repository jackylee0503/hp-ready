# UI design (locked 2026-10-23)

Export of the design canvas "HP-Ready homeowner flow". These files are the source of truth for layout, order and exact copy; `CLAUDE.md` → "Screens" summarises them for the build. Numbers on the screens are examples from the spec's scratch calculation; the engine supplies the real ones.

The `.dc.html` files need the canvas runtime to render, so read them rather than opening them in a browser. Each one is a single screen:

| File | Screen |
| --- | --- |
| `Main.dc.html` | Phone 1/4: tell us about your house |
| `Step2.dc.html` | Phone 2/4: radiator photo |
| `Step3.dc.html` | Phone 3/4: bill or listing |
| `Step4.dc.html` | Phone 4/4: is this right? |
| `Answer.dc.html` | Phone: the answer, rows open on tap |
| `Request.dc.html` | Phone: pre-filled quote request |
| `Handover.dc.html` | The one-page A4 pre-visit sheet (PDF for the installer) |
| `NextStep.dc.html` | The next-step button for each verdict |
| `WebHome.dc.html` | Desktop: wizard with "What we know so far" |
| `WebAnswer.dc.html` | Desktop: answer with the quote request beside it |
| `WebEval.dc.html` | Desktop: Evaluation table and details (pitch screen) |
| `WebInstaller.dc.html` | Desktop: installer prep sheet |
| `canvas.json` | How the screens are laid out on the canvas |

Images are referenced as `/_blob/<id>` uploads on the canvas: `3ef8d7eb…` is `data/pipe_photos/05_zweirohr-vermutet_kompakt.jpeg`, `a1407ddd…` is `assets/demo/bill_demo_gas_2025_photo.jpg`.
