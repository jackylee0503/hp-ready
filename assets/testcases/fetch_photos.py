"""Download the test photos listed in photos.json into assets/testcases/photos/ (run on your own machine).

    python assets/testcases/fetch_photos.py

Wikimedia asks for a descriptive User-Agent; the photos are openly licensed (author and licence per file in
photos.json, keep that attribution if you show a photo in the pitch).
"""
import json
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "photos"
UA = "HP-Ready-hackathon-testcases/1.0 (WATT THE HACK Munich 2026; contact via GitHub jackylee0503/hp-ready)"


def main() -> None:
    OUT.mkdir(exist_ok=True)
    photos = json.loads((HERE / "photos.json").read_text(encoding="utf-8"))["photos"]
    for key, p in photos.items():
        if "image_url" not in p:              # already in the repo
            print("repo", key, "→", p["local"])
            continue
        ext = Path(p["image_url"].split("?")[0]).suffix.lower() or ".jpg"
        dst = OUT / f"{key}{ext}"
        if dst.exists():
            print("have", dst.name)
            continue
        req = urllib.request.Request(p["image_url"], headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                dst.write_bytes(r.read())
            print("got ", dst.name, f"({dst.stat().st_size // 1024} KB)")
        except Exception as e:  # noqa: BLE001
            print("FAIL", key, e, "→ open", p["page_url"], "and save it by hand as", dst.name)


if __name__ == "__main__":
    main()
