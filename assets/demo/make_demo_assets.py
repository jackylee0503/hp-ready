"""Generate clearly fictional, labelled demo inputs for the HP-Ready homeowner flow.

Usage: python3 make_demo_assets.py <output_dir>
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# ---- bill numbers (fictional, internally consistent) ----
M3 = 1651
ZZ = 0.9523          # Zustandszahl
HS = 11.450          # Brennwert kWh/m3
KWH = round(M3 * ZZ * HS)          # 18,002
AP = 0.1050                        # Arbeitspreis €/kWh (fictional)
GP = 14.90                         # Grundpreis €/Monat (fictional)
arbeit = round(KWH * AP, 2)
grund = round(12 * GP, 2)
netto = round(arbeit + grund, 2)
mwst = round(netto * 0.19, 2)
brutto = round(netto + mwst, 2)
abschlag_paid = 12 * 195.00
nachzahlung = round(brutto - abschlag_paid, 2)


def de(x, nd=2):
    s = f"{x:,.{nd}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


BILL_LINES = [
    ("h", "Stadtwerke Musterstadt (fiktiv)"),
    ("s", "Musterweg 1 · 00000 Musterstadt"),
    ("gap", ""),
    ("t", "Jahresabrechnung Erdgas 2025"),
    ("gap", ""),
    ("kv", ("Kunde", "Max Mustermann")),
    ("kv", ("Kundennummer", "DEMO-000001")),
    ("kv", ("Verbrauchsstelle", "Musterstraße 1, 00000 Musterstadt")),
    ("kv", ("Abrechnungszeitraum", "01.01.2025 – 31.12.2025 (365 Tage)")),
    ("gap", ""),
    ("t2", "Verbrauchsermittlung"),
    ("kv", ("Zählerstand alt (01.01.2025)", "12.345 m³")),
    ("kv", ("Zählerstand neu (31.12.2025)", f"{de(12345 + M3, 0)} m³")),
    ("kv", ("Verbrauch", f"{de(M3, 0)} m³")),
    ("kv", ("Zustandszahl", de(ZZ, 4))),
    ("kv", ("Brennwert", f"{de(HS, 3)} kWh/m³")),
    ("kvb", ("Verbrauch in kWh", f"{de(KWH, 0)} kWh")),
    ("gap", ""),
    ("t2", "Kosten"),
    ("kv", ("Arbeitspreis", f"{de(KWH, 0)} kWh × {de(AP * 100, 2)} ct/kWh = {de(arbeit)} €")),
    ("kv", ("Grundpreis", f"12 Monate × {de(GP)} € = {de(grund)} €")),
    ("kv", ("Summe netto", f"{de(netto)} €")),
    ("kv", ("MwSt. 19 %", f"{de(mwst)} €")),
    ("kvb", ("Gesamtbetrag brutto", f"{de(brutto)} €")),
    ("kv", ("Geleistete Abschläge", f"12 × 195,00 € = {de(abschlag_paid)} €")),
    ("kvb", ("Nachzahlung", f"{de(nachzahlung)} €")),
    ("kv", ("Neuer Abschlag ab 02/2026", "205,00 € / Monat")),
    ("gap", ""),
    ("note", "DEMO – fiktive Rechnung. Keine echte Rechnung, kein echtes Unternehmen."),
    ("note", "Erstellt als Testeingabe für den HP-Ready Hackathon-Prototyp."),
]


def bill_pdf(path):
    pdfmetrics.registerFont(TTFont("DV", FONT))
    pdfmetrics.registerFont(TTFont("DVB", FONT_B))
    c = canvas.Canvas(str(path), pagesize=A4)
    w, h = A4
    c.setTitle("DEMO - fiktive Gas-Jahresabrechnung (Stadtwerke Musterstadt)")
    # watermark
    c.saveState()
    c.setFillColorRGB(0.85, 0.2, 0.2, alpha=0.12)
    c.setFont("DVB", 64)
    c.translate(w / 2, h / 2)
    c.rotate(35)
    c.drawCentredString(0, 0, "DEMO · FIKTIV")
    c.restoreState()
    y = h - 60
    for kind, val in BILL_LINES:
        if kind == "gap":
            y -= 10
            continue
        if kind == "h":
            c.setFont("DVB", 18); c.drawString(50, y, val); y -= 22
        elif kind == "s":
            c.setFont("DV", 10); c.drawString(50, y, val); y -= 14
        elif kind == "t":
            c.setFont("DVB", 15); c.drawString(50, y, val); y -= 22
        elif kind == "t2":
            c.setFont("DVB", 12); c.drawString(50, y, val); y -= 18
        elif kind in ("kv", "kvb"):
            c.setFont("DVB" if kind == "kvb" else "DV", 10.5)
            c.drawString(50, y, val[0]); c.drawString(250, y, val[1]); y -= 16
        elif kind == "note":
            c.setFillColorRGB(0.7, 0.1, 0.1); c.setFont("DVB", 10)
            c.drawString(50, y, val); y -= 14; c.setFillColorRGB(0, 0, 0)
    c.showPage()
    c.save()


def render_lines(lines, size=(1240, 1754), scale=2.0):
    img = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(img)
    f = lambda s, b=False: ImageFont.truetype(FONT_B if b else FONT, int(s * scale))
    y = int(60 * scale)
    x0, x1 = int(50 * scale), int(250 * scale)
    for kind, val in lines:
        if kind == "gap":
            y += int(10 * scale); continue
        if kind == "h":
            d.text((x0, y), val, fill="black", font=f(18, True)); y += int(24 * scale)
        elif kind == "s":
            d.text((x0, y), val, fill="#333", font=f(10)); y += int(15 * scale)
        elif kind == "t":
            d.text((x0, y), val, fill="black", font=f(15, True)); y += int(22 * scale)
        elif kind == "t2":
            d.text((x0, y), val, fill="black", font=f(12, True)); y += int(18 * scale)
        elif kind in ("kv", "kvb"):
            d.text((x0, y), val[0], fill="black", font=f(10.5, kind == "kvb"))
            d.text((x1, y), val[1], fill="black", font=f(10.5, kind == "kvb")); y += int(16 * scale)
        elif kind == "note":
            d.text((x0, y), val, fill="#B42318", font=f(10, True)); y += int(15 * scale)
    # watermark
    wm = Image.new("RGBA", size, (0, 0, 0, 0))
    wd = ImageDraw.Draw(wm)
    wd.text((size[0] * 0.12, size[1] * 0.45), "DEMO · FIKTIV", fill=(200, 40, 40, 40), font=f(64, True))
    wm = wm.rotate(35, center=(size[0] / 2, size[1] / 2))
    img = Image.alpha_composite(img.convert("RGBA"), wm).convert("RGB")
    return img


def bill_photo(path):
    page = render_lines(BILL_LINES)
    # fake "phone photo": grey table, slight rotation, soft blur, uneven light
    bg = Image.new("RGB", (page.width + 260, page.height + 260), "#8a8f96")
    rot = page.rotate(-3.5, expand=True, fillcolor="#8a8f96")
    bg.paste(rot, (110, 90))
    shade = Image.linear_gradient("L").resize(bg.size).rotate(90)
    bg = Image.composite(bg, Image.new("RGB", bg.size, "#5d6168"), shade.point(lambda v: 150 + v // 3))
    bg = bg.filter(ImageFilter.GaussianBlur(1.2)).resize((bg.width // 2, bg.height // 2))
    bg.save(path, quality=82)


LISTING = {
    "title": "Reihenmittelhaus mit Garten, ruhige Lage",
    "facts": [("Wohnfläche", "128 m²"), ("Zimmer", "5"), ("Baujahr", "1994"), ("Grundstück", "210 m²")],
    "energy": [
        ("Energieausweis", "Verbrauchsausweis"),
        ("Endenergieverbrauch", "128 kWh/(m²·a)"),
        ("Wesentlicher Energieträger", "Gas"),
        ("Heizungsart", "Zentralheizung"),
        ("Energieeffizienzklasse", "D"),
        ("Modernisierung", "Fenster 2012 erneuert"),
    ],
}


def listing_png(path):
    W, H = 1080, 1700
    img = Image.new("RGB", (W, H), "#F4F5F7")
    d = ImageDraw.Draw(img)
    f = lambda s, b=False: ImageFont.truetype(FONT_B if b else FONT, s)
    # photo placeholder (no real photo)
    d.rectangle([0, 0, W, 560], fill="#C9D2DC")
    d.text((W // 2 - 300, 250), "[ Foto – fiktives Beispiel ]", fill="#4A5565", font=f(40))
    d.rectangle([0, 560, W, 640], fill="#B42318")
    d.text((40, 578), "FIKTIVES BEISPIEL – kein echtes Inserat", fill="white", font=f(38, True))
    y = 680
    d.text((40, y), LISTING["title"], fill="#14213D", font=f(39, True)); y += 76
    d.text((40, y), "Kaufpreis: 489.000 € (fiktiv)", fill="#14213D", font=f(34)); y += 80
    # facts grid
    for i, (k, v) in enumerate(LISTING["facts"]):
        x = 40 + (i % 2) * 520
        yy = y + (i // 2) * 130
        d.rounded_rectangle([x, yy, x + 480, yy + 110], radius=18, fill="white", outline="#E2E6EA", width=2)
        d.text((x + 24, yy + 14), k, fill="#4A5565", font=f(28))
        d.text((x + 24, yy + 52), v, fill="#14213D", font=f(38, True))
    y += 290
    d.text((40, y), "Energie & Heizung", fill="#14213D", font=f(38, True)); y += 66
    for k, v in LISTING["energy"]:
        d.text((40, y), k, fill="#4A5565", font=f(30))
        d.text((560, y), v, fill="#14213D", font=f(30, True)); y += 56
    img.save(path)


TEXTS = {
    "house_persona_en.txt": "Terraced house from 1972, about 140 m². We got new windows in 2015 and the roof was insulated. Gas heating, roughly 18,000 kWh a year, three of us live here. 10 radiators, the big flat ones.\n",
    "house_persona_de.txt": "Reihenhaus von 1972, ca. 140 qm. 2015 neue Fenster, Dach gedämmt. Gasheizung, ungefähr 18.000 kWh im Jahr, wir sind zu dritt. 10 Heizkörper, die großen flachen.\n",
    "house_conflict_en.txt": "Detached house, built 1985, 120 m², oil heating, 4 people. Never renovated as far as I know.\n",
    "house_minimal_en.txt": "Old house, around 150 m², radiators everywhere. No idea about the rest.\n",
}

if __name__ == "__main__":
    bill_pdf(OUT / "bill_demo_gas_2025.pdf")
    bill_photo(OUT / "bill_demo_gas_2025_photo.jpg")
    listing_png(OUT / "listing_demo_reihenhaus_1994.png")
    for name, text in TEXTS.items():
        (OUT / name).write_text(text, encoding="utf-8")
    print("kWh", KWH, "| arbeit", arbeit, "| grund", grund, "| netto", netto, "| mwst", mwst,
          "| brutto", brutto, "| nachzahlung", nachzahlung)
