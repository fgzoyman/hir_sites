#!/usr/bin/env python3
"""
run_pipeline.py

Teljes integrált adatgyűjtési és feldolgozási folyamat a 6 hírportálhoz:
1. Címlapi adatfelvétel (SeleniumBase Undetected ChromeDriver segítségével, linknormalizálással)
2. Címlapi HTML-ek feldolgozása, rovatok és linkek kinyerése -> hozzáfűzés a scraped_links_summary.csv-hez
3. Új linkek szinkronizálása az SQLite adatbázisba (articles.db)
4. Kizárólag az újonnan feltűnt (downloaded == 0) cikkek kíméletes, round-robin letöltése
   és 3-utas Markdown (MarkItDown, Trafilatura, Newspaper4k) + NLP mentése.

Használat:
    python run_pipeline.py                 # teljes folyamat (címlap scrape -> feldolgozás -> új cikkek letöltése)
    python run_pipeline.py --headless      # címlapok mentése láthatatlan böngészővel
    python run_pipeline.py --skip-scrape   # meglévő címlapi HTML-ek feldolgozása és új cikkek letöltése mentés nélkül
    python run_pipeline.py --limit 30      # legfeljebb 30 új cikk letöltése teszteléshez
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# Virtuális környezet site-packages könyvtárának betöltése
venv_site_packages = Path(__file__).parent / ".venv/lib/python3.12/site-packages"
if venv_site_packages.exists() and str(venv_site_packages.resolve()) not in sys.path:
    sys.path.insert(0, str(venv_site_packages.resolve()))

import article_db
import download_articles
import parse_scraped
import scrape_sites


def run_pipeline(
    headless: bool = False,
    skip_scrape: bool = False,
    include_rovatok: bool = False,
    rovatok_path: Optional[Path] = None,
    limit_downloads: Optional[int] = None,
    csv_path: Path = Path("scraped_links_summary.csv"),
    db_path: Path = Path("articles.db"),
    data_dir: Path = Path("scraped_data"),
    articles_dir: Path = Path("scraped_articles"),
):
    """Az 1-2-3 lépésből álló integrált munkafolyamat futtatása."""
    start_time = time.time()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print("\n" + "=" * 70)
    print(f" INTEGRÁLT HÍRADATBÁZIS ÉS CIKKGYŰJTŐ FOLYAMAT -- {now_str}")
    print("=" * 70)

    # -------------------------------------------------------------
    # 1. LÉPÉS: Címlapi adatfelvétel a 6 oldalon (SeleniumBase)
    # -------------------------------------------------------------
    saved_html_files: List[Path] = []
    if skip_scrape:
        print("\n[1/3] Címlapok mentése kihagyva (--skip-scrape aktív).")
        raw_files = sorted([
            f for f in data_dir.glob("*.html")
            if not f.name.endswith("_articles.html") and not f.name.startswith("tmp")
        ])
        saved_html_files = parse_scraped.get_latest_batch_files(raw_files)
        print(f"      Feldolgozásra kijelölt legfrissebb mentett fájlok: {len(saved_html_files)} db")
    else:
        print("\n[1/3] CÍMLAPI ÉS ROVAT ADATFELVÉTEL A 6 HÍRPORTÁLON...")
        saved_html_files = scrape_sites.scrape_frontpages(
            output_dir=data_dir,
            headless=headless,
            include_rovatok=include_rovatok,
            rovatok_path=rovatok_path,
        )

        # Ellenőrzés: ha rovatok is kellenek, 110 oldalnak kell lennie, ha csak címlap, akkor 6-nak
        expected_count = 110 if include_rovatok else 6
        if len(saved_html_files) < expected_count:
            print(
                f"\n[!] HIBA: Nem sikerült mindegyik oldalt lementeni! "
                f"Elvárt: {expected_count} db, Mentve: {len(saved_html_files)} db.\n"
                f"A folyamat a hiányzó oldalak miatt nem lép tovább a JSON feldolgozásra.",
                file=sys.stderr,
            )
            return

        print(f"[✓] 1. lépés kész: Mind a(z) {len(saved_html_files)} oldal sikeresen és hiánytalanul lementve.")

    if not saved_html_files:
        print("[!] Nem található feldolgozható címlapi HTML fájl. A folyamat leáll.", file=sys.stderr)
        return

    # -------------------------------------------------------------
    # 2. LÉPÉS: HTML-ek feldolgozása, kinyerés és hozzáírás a CSV-hez
    # -------------------------------------------------------------
    print("\n[2/3] CÍMLAPI LINKEK ÉS METAADATOK KINYERÉSE, HOZZÁÍRÁS A CSV-HEZ...")
    all_new_records = []
    for html_file in saved_html_files:
        site_key, records = parse_scraped.process_html_file(html_file)
        all_new_records.extend(records)

        # JSON mentése fájlonként
        json_path = html_file.parent / f"{html_file.stem}_articles.json"
        parse_scraped.save_json(records, json_path)
        print(f"  [✓] {html_file.name:<40} -> {site_key or '?':<12} : {len(records):3d} cikk kinyerve")

    # Rekordok hozzáfűzése a scraped_links_summary.csv-hez
    parse_scraped.append_or_write_csv(all_new_records, csv_path, overwrite=False)
    print(f"[✓] 2. lépés kész: Címlapi elemek feldolgozva és hozzáírva: {csv_path.name}")

    # Szinkronizálás az SQLite adatbázisba
    print("\n[+] Új linkek szinkronizálása az adatbázisba (articles.db)...")
    article_db.sync_csv_to_db(csv_path=csv_path, db_path=db_path)

    # -------------------------------------------------------------
    # 3. LÉPÉS: Kizárólag az újonnan feltűnt (downloaded == 0) cikkek letöltése
    # -------------------------------------------------------------
    print("\n[3/3] ÚJONNAN FELTŰNT CIKKEK LETÖLTÉSE ÉS 3-UTAS FELDOLGOZÁSA...")
    download_articles.download_articles(
        db_path=db_path,
        output_dir=articles_dir,
        limit=limit_downloads,
        shuffle_sites=True,
        delay_range=(1.0, 2.2),
    )

    elapsed = time.time() - start_time
    print("\n" + "=" * 70)
    print(f"[✓] INTEGRÁLT FOLYAMAT SIKERESEN BEFEJEZŐDÖTT! Futási idő: {elapsed/60:.1f} perc")
    print("=" * 70)
    article_db.print_db_summary(db_path=db_path)


def main():
    parser = argparse.ArgumentParser(description="Integrált hírgyűjtő folyamat: címlapok -> CSV/DB -> új cikkek letöltése.")
    parser.add_argument("--headless", action="store_true", help="Böngésző futtatása háttérben (fej nélküli mód)")
    parser.add_argument("--skip-scrape", action="store_true", help="Címlapok mentésének kihagyása, meglévő legújabb fájlok feldolgozása")
    parser.add_argument("--include-rovatok", action="store_true", help="A híroldalak rovatainak letöltése is (rovatok_urljei.txt alapján)")
    parser.add_argument("--rovatok-file", type=str, default="rovatok_urljei.txt", help="Rovatok URL-jeit tartalmazó fájl")
    parser.add_argument("--limit", type=int, default=None, help="Legfeljebb ennyi új cikk letöltése (teszteléshez)")
    parser.add_argument("--csv", type=str, default="scraped_links_summary.csv", help="Cél CSV fájl elérési útja")
    parser.add_argument("--db", type=str, default="articles.db", help="SQLite adatbázis elérési útja")

    args = parser.parse_args()

    run_pipeline(
        headless=args.headless,
        skip_scrape=args.skip_scrape,
        include_rovatok=args.include_rovatok,
        rovatok_path=Path(args.rovatok_file) if args.rovatok_file else None,
        limit_downloads=args.limit,
        csv_path=Path(args.csv),
        db_path=Path(args.db),
    )


if __name__ == "__main__":
    main()
