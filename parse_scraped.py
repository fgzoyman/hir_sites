#!/usr/bin/env python3
"""
parse_scraped.py


Oldalspecifikus HTML feldolgozó hat magyar hírportál címlapjaihoz:
1. Origo
2. Népszava
3. 24.hu
4. Blikk
5. Portfolio
6. Vadhajtások

Használat:
    python parse_scraped.py                    # automatikusan a scraped_data/ legújabb mentését dolgozza fel
    python parse_scraped.py scraped_data/      # a legújabb 6 fájl feldolgozása és hozzáfűzése a CSV-hez
    python parse_scraped.py scraped_data/ --all # az összes mentés feldolgozása
    python parse_scraped.py scraped_data/1_Origo_2026-09-08_10-18-36.html --site origo
    python parse_scraped.py scraped_data/ --csv scraped_links_summary.csv
"""

import argparse
import csv
import json
import sys
from pathlib import Path

# Biztosítjuk a lokális virtuális környezet site-packages könyvtárának betöltését
venv_site_packages = Path(__file__).parent / ".venv/lib/python3.12/site-packages"
if venv_site_packages.exists() and str(venv_site_packages.resolve()) not in sys.path:
    sys.path.insert(0, str(venv_site_packages.resolve()))

from typing import Any, Dict, List

from bs4 import BeautifulSoup

from parsers import detect_site_key, get_parser, PARSER_REGISTRY


def process_html_file(file_path: Path, site_override: str = None) -> tuple[str, List[Dict[str, Any]]]:
    """Egyetlen HTML fájl feldolgozása a hozzárendelt parserrel."""
    try:
        html_content = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        print(f"[!] Hiba a fájl olvasásakor ({file_path.name}): {e}", file=sys.stderr)
        return "", []

    soup = BeautifulSoup(html_content, "html.parser")

    site_key = site_override or detect_site_key(str(file_path), soup)
    if not site_key:
        print(f"[-] Nem sikerült azonosítani a portált a fájlhoz: {file_path.name}", file=sys.stderr)
        return "", []

    parser = get_parser(site_key, soup, source_file=file_path.name)
    if not parser:
        print(f"[-] Nem található parser a következő oldalhoz: {site_key}", file=sys.stderr)
        return site_key, []

    records = parser.parse()
    return site_key, records


FIELDNAMES = [
    "site",
    "order",
    "link",
    "title",
    "authors",
    "section",
    "tags",
    "lead",
    "source_file",
    "media_type",
    "media_url",
    "media_alt",
]


def save_json(records: List[Dict[str, Any]], output_path: Path):
    """Cikkek mentése formázott JSON-ként."""
    output_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def append_or_write_csv(records: List[Dict[str, Any]], output_path: Path, overwrite: bool = False):
    """Cikkek mentése vagy hozzáfűzése CSV-hez duplikációszűréssel a forrásfájl szintjén."""
    if not records and output_path.exists():
        return

    existing_source_files = set()
    file_exists = output_path.exists() and output_path.stat().st_size > 0

    if file_exists and not overwrite:
        try:
            with output_path.open("r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    sf = row.get("source_file")
                    if sf:
                        existing_source_files.add(sf)
        except Exception as e:
            print(f"[!] Figyelmeztetés a meglévő CSV olvasásakor ({output_path.name}): {e}", file=sys.stderr)

    # Csak azokat a rekordokat fűzzük hozzá, amelyek forrásfájlja még nem szerepel a CSV-ben
    new_records = [r for r in records if overwrite or r.get("source_file") not in existing_source_files]
    skipped_count = len(records) - len(new_records)
    if skipped_count > 0:
        print(f"[i] {skipped_count} rekord kihagyva, mert a forrásfájl már szerepel a CSV-ben.")

    if not new_records and file_exists:
        print(f"[i] Nincs új rekord, a CSV változatlan maradt: {output_path.name}")
        return

    mode = "w" if (overwrite or not file_exists) else "a"
    with output_path.open(mode, encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if mode == "w":
            writer.writeheader()
        for r in new_records:
            row = dict(r)
            if isinstance(row.get("authors"), list):
                row["authors"] = "; ".join(row.get("authors", []))
            if isinstance(row.get("tags"), list):
                row["tags"] = "; ".join(row.get("tags", []))
            writer.writerow(row)

    action = "újraírva" if mode == "w" else "hozzáfűzve"
    print(f"[✓] CSV sikeresen frissítve ({action}: {len(new_records)} sor) -> {output_path.resolve()}")


def get_latest_batch_files(files: List[Path]) -> List[Path]:
    """
    A legfrissebb mentési köteghez (legújabb időbélyeg) tartozó fájlok kiválasztása.
    Fájlnév minta: {id}_{short_name}_{YYYY-MM-DD_HH-MM-SS}.html
    """
    import re
    timestamp_pattern = re.compile(r"(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})\.html$")
    
    files_by_ts: Dict[str, List[Path]] = {}
    for f in files:
        match = timestamp_pattern.search(f.name)
        if match:
            ts = match.group(1)
            files_by_ts.setdefault(ts, []).append(f)

    if not files_by_ts:
        return files

    latest_ts = max(files_by_ts.keys())
    return sorted(files_by_ts[latest_ts])


def print_summary_stats(all_records: List[Dict[str, Any]]):
    """Kitöltöttségi statisztikák kiírása a konzolra."""
    total = len(all_records)
    if total == 0:
        print("Nincs feldolgozott cikk.")
        return

    has_title = sum(1 for r in all_records if r.get("title"))
    has_lead = sum(1 for r in all_records if r.get("lead"))
    has_section = sum(1 for r in all_records if r.get("section"))
    has_authors = sum(1 for r in all_records if r.get("authors"))
    has_tags = sum(1 for r in all_records if r.get("tags"))
    has_media = sum(1 for r in all_records if r.get("media_type") != "none" and r.get("media_url"))

    print("\n" + "=" * 55)
    print(f"ÖSSZESÍTETT STATISZTIKA (Összes cikk: {total})")
    print("=" * 55)
    print(f"  Cím:       {has_title:4d} / {total} ({has_title/total*100:5.1f}%)")
    print(f"  Lead:      {has_lead:4d} / {total} ({has_lead/total*100:5.1f}%)")
    print(f"  Rovat:     {has_section:4d} / {total} ({has_section/total*100:5.1f}%)")
    print(f"  Szerző:    {has_authors:4d} / {total} ({has_authors/total*100:5.1f}%)")
    print(f"  Címkék:    {has_tags:4d} / {total} ({has_tags/total*100:5.1f}%)")
    print(f"  Média:     {has_media:4d} / {total} ({has_media/total*100:5.1f}%)")
    print("=" * 55)


def main():
    parser = argparse.ArgumentParser(description="HTML híroldal feldolgozó hat hírportálhoz.")
    parser.add_argument("input_path", nargs="?", default="scraped_data", help="HTML fájl vagy könyvtár elérési útja (alapértelmezett: scraped_data)")
    parser.add_argument("--site", choices=list(PARSER_REGISTRY.keys()), help="Portál kézi megadása")
    parser.add_argument("--csv", default="scraped_links_summary.csv", help="Kimeneti CSV fájl neve (alapértelmezett: scraped_links_summary.csv)")
    parser.add_argument("--output-dir", help="JSON fájlok mentési könyvtára (alapértelmezés: input könyvtár)")
    parser.add_argument("--all", action="store_true", help="Az összes talált HTML fájl feldolgozása a csak legfrissebb mentés helyett")
    parser.add_argument("--overwrite-csv", action="store_true", help="A kimeneti CSV teljes újraírása a meglévő tartalom hozzáfűzése helyett")

    args = parser.parse_args()
    input_path = Path(args.input_path)

    if not input_path.exists():
        print(f"[!] A megadott útvonal nem létezik: {input_path}", file=sys.stderr)
        sys.exit(1)

    html_files: List[Path] = []
    if input_path.is_file():
        if input_path.suffix.lower() == ".html":
            html_files.append(input_path)
    else:
        # Csak az eredeti mentett HTML-eket gyűjtjük, kihagyva az esetleges generált vagy átmeneti fájlokat
        raw_files = sorted([
            f for f in input_path.glob("*.html")
            if not f.name.endswith("_articles.html") and not f.name.startswith("tmp")
        ])
        if args.all:
            html_files = raw_files
        else:
            html_files = get_latest_batch_files(raw_files)

    if not html_files:
        print("[!] Nem található feldolgozandó HTML fájl.", file=sys.stderr)
        sys.exit(1)

    all_records: List[Dict[str, Any]] = []
    site_counts: Dict[str, int] = {}

    batch_mode = "mindegyik" if args.all or input_path.is_file() else "legújabb mentés"
    print(f"\n[+] Feldolgozás indítása ({batch_mode}): {len(html_files)} HTML fájl...")

    for html_file in html_files:
        site_key, records = process_html_file(html_file, args.site)
        count = len(records)
        site_counts[site_key or "ismeretlen"] = site_counts.get(site_key or "ismeretlen", 0) + count
        all_records.extend(records)

        # JSON mentése oldalanként
        out_dir = Path(args.output_dir) if args.output_dir else html_file.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        json_path = out_dir / f"{html_file.stem}_articles.json"
        save_json(records, json_path)

        print(f"  [✓] {html_file.name:<38} -> {site_key or '?':<12} : {count:3d} cikk kinyerve -> {json_path.name}")

    # Összesített CSV mentése / hozzáfűzése
    if args.csv:
        csv_path = Path(args.csv)
        append_or_write_csv(all_records, csv_path, overwrite=args.overwrite_csv)

    # Statisztika
    print_summary_stats(all_records)


if __name__ == "__main__":
    main()
