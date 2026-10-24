"""Bill extraction MVP.

Purpose:
    Parse a household energy bill (PDF or image) and return structured fields
    that can be passed downstream to the validation layer and engine.

Scope:
    - extract raw text from a bill
    - parse likely energy values
    - return only structured data, no confidence or contradiction logic
    - keep the interface simple and easy to validate in a hackathon setting

This file intentionally does NOT decide the final heat-pump verdict.
It only turns a messy bill into useable fields.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

try:
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover
    fitz = None

try:
    from PIL import Image, ImageOps
except Exception:  # pragma: no cover
    Image = None
    ImageOps = None

try:
    import pytesseract
except Exception:  # pragma: no cover
    pytesseract = None


# Bill parsing stack:
# - fitz: PDF text extraction from utility bills
# - PIL: image preprocessing before OCR
# - pytesseract: OCR for scanned bills and screenshots
# - These are intentionally kept local and lightweight for a hackathon MVP.


def _clean_number(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip()
    value = value.replace(" ", "")
    value = value.replace(".", "")
    value = value.replace(",", ".")
    try:
        return float(value)
    except Exception:
        return None


def _normalise_date(date_text: str | None) -> str | None:
    if not date_text:
        return None
    s = date_text.strip()
    # dd.mm.yyyy -> yyyy-mm-dd
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", s)
    if m:
        d, mo, y = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    # yyyy-mm-dd
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        y, mo, d = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    return s


def _extract_first(patterns: list[str], text: str) -> str | None:
    for pat in patterns:
        m = re.search(pat, text, flags=re.I | re.S)
        if m:
            return m.group(1).strip()
    return None


def _guess_fuel_type(text: str) -> str | None:
    lower = text.lower()
    if re.search(r"lpg|liquefied gas|flüssiggas|propane", lower):
        return "lpg"
    if re.search(r"oil|heizöl|öl", lower):
        return "oil"
    if re.search(r"district|fernwärme|district heating", lower):
        return "district"
    if re.search(r"electric|strom|electricity", lower):
        return "electric"
    if re.search(r"gas|natural gas|erdgas|gasoil", lower):
        return "gas"
    return None


def _extract_pdf_text(path: str | os.PathLike[str]) -> str:
    if fitz is None:
        raise RuntimeError("PyMuPDF is not installed. Install with: pip install pymupdf")
    doc = fitz.open(path)
    text_parts: list[str] = []
    for page in doc:
        text_parts.append(page.get_text())
    return "\n".join(text_parts)


def _extract_ocr_text(path: str | os.PathLike[str]) -> str:
    if Image is None or pytesseract is None:
        raise RuntimeError("OCR dependencies are not installed. Install: pip install pillow pytesseract")
    img = Image.open(path)
    img = ImageOps.grayscale(img)
    img = img.resize((img.width * 2, img.height * 2))
    return pytesseract.image_to_string(img, lang="eng")


def parse_bill_text(text: str) -> dict[str, Any]:
    """Parse a raw bill text blob into structured fields.

    This is intentionally narrow: it extracts the obvious core bill values only.
    It does not do confidence estimation or contradiction logic.
    """
    text = (text or "").strip()
    if not text:
        return {
            "fuel_type": None,
            "annual_fuel_kwh": None,
            "annual_fuel_m3": None,
            "annual_fuel_liters": None,
            "period_start": None,
            "period_end": None,
            "total_cost_eur": None,
            "source": None,
        }

    fuel_type = _guess_fuel_type(text)

    annual_kwh = None
    annual_m3 = None
    annual_liters = None

    # Annual kWh patterns
    kwh_match = re.search(r"(?:annual|yearly|jahres|verbrauch)[^\n]{0,30}?(\d[\d\s.,]{2,})\s*(?:kwh|kWh)", text, flags=re.I)
    if kwh_match:
        annual_kwh = _clean_number(kwh_match.group(1))
    else:
        m = re.search(r"(\d[\d\s.,]{2,})\s*(?:kwh|kWh)", text, flags=re.I)
        if m:
            annual_kwh = _clean_number(m.group(1))

    # gas volume patterns
    gas_match = re.search(r"(?:annual|yearly|jahres|verbrauch)[^\n]{0,30}?(\d[\d\s.,]{2,})\s*(?:m3|m³|nm3|Nm3)", text, flags=re.I)
    if gas_match:
        annual_m3 = _clean_number(gas_match.group(1))
    else:
        m = re.search(r"(\d[\d\s.,]{2,})\s*(?:m3|m³|nm3|Nm3)", text, flags=re.I)
        if m:
            annual_m3 = _clean_number(m.group(1))

    # oil liters patterns
    oil_match = re.search(r"(?:annual|yearly|jahres|verbrauch)[^\n]{0,30}?(\d[\d\s.,]{2,})\s*(?:liter|litre|liters|litres|l)", text, flags=re.I)
    if oil_match:
        annual_liters = _clean_number(oil_match.group(1))
    else:
        m = re.search(r"(\d[\d\s.,]{2,})\s*(?:liter|litre|liters|litres|l)\b", text, flags=re.I)
        if m:
            annual_liters = _clean_number(m.group(1))

    # Dates: look for a range first
    period_start = None
    period_end = None
    range_match = re.search(r"(\d{1,2}\.\d{1,2}\.\d{4})\s*[–-]\s*(\d{1,2}\.\d{1,2}\.\d{4})", text)
    if range_match:
        period_start = _normalise_date(range_match.group(1))
        period_end = _normalise_date(range_match.group(2))
    else:
        # try ISO style date ranges too
        iso_match = re.search(r"(\d{4}-\d{1,2}-\d{1,2})\s*[–-]\s*(\d{4}-\d{1,2}-\d{1,2})", text)
        if iso_match:
            period_start = _normalise_date(iso_match.group(1))
            period_end = _normalise_date(iso_match.group(2))

    # total cost
    total_cost = None
    total_match = re.search(r"(?:total|gesamt|amount due|summe)[^\n]{0,30}?(\d+[\.,]\d{2}|\d+)[\s]*€", text, flags=re.I)
    if total_match:
        total_cost = _clean_number(total_match.group(1))
    else:
        # last-resort: any euro value near billing data
        euro_matches = re.findall(r"(\d+[\.,]\d{2})\s*€", text, flags=re.I)
        if euro_matches:
            total_cost = _clean_number(euro_matches[-1])

    return {
        "fuel_type": fuel_type,
        "annual_fuel_kwh": annual_kwh,
        "annual_fuel_m3": annual_m3,
        "annual_fuel_liters": annual_liters,
        "period_start": period_start,
        "period_end": period_end,
        "total_cost_eur": total_cost,
        "source": "text",
    }


def extract_bill_data(file_path: str | os.PathLike[str]) -> dict[str, Any]:
    """Extract structured data from a household energy bill.

    Order of operations:
        1. try PDF text extraction if file looks like PDF
        2. if PDF is not text-extractable, try OCR
        3. parse known bill fields into a simple dict

    Output fields are intentionally minimal. This module does not decide the final
    verdict or apply contradiction logic.
    """
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"Bill file not found: {file_path}")

    text = ""
    method = "unknown"

    suffix = p.suffix.lower()

    if suffix == ".pdf":
        try:
            text = _extract_pdf_text(p)
            method = "pdf_text"
        except Exception:
            try:
                text = _extract_ocr_text(p)
                method = "ocr"
            except Exception:
                raise RuntimeError("Could not read PDF text or OCR the file.")
    elif suffix in {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}:
        try:
            text = _extract_ocr_text(p)
            method = "ocr"
        except Exception:
            raise RuntimeError("Could not OCR the image bill.")
    else:
        # fallback: plain text file
        try:
            text = p.read_text(encoding="utf-8")
            method = "text"
        except Exception:
            raise RuntimeError("Unsupported file type for bill extraction.")

    structured = parse_bill_text(text)
    structured["source"] = method
    structured["raw_excerpt"] = text[:1200]
    structured["status"] = "ok" if any(v is not None for v in structured.values() if v not in (None, "text")) else "no_data_found"
    return structured


if __name__ == "__main__":
    # Minimal self-check: parse a sample text blob if no file path is supplied.
    demo = """
    Jahresverbrauch 2025: 18.240 kWh
    Gasverbrauch: 1.820 m3
    Rechnungszeitraum: 01.01.2025 - 31.12.2025
    Gesamt: 1.420,50 €
    Lieferant: Gas
    """
    print(json.dumps(parse_bill_text(demo), indent=2, ensure_ascii=False))
