#!/usr/bin/env python3
"""
article_db.py

SQLite adatbázis-kezelő és szinkronizáló modul a címlapi cikk-linkekhez és megjelenésekhez.

Táblák:
1. articles:
   - id: folytonos, auto-increment egész szám azonosító (elsődleges kulcs)
   - link: a cikk egyedi URL-je (UNIQUE)
   - site: hírportál azonosító (origo, nepszava, huszonnegy, blikk, portfolio, vadhajtasok)
   - first_seen_at: az első címlapi észlelés időpontja
   - last_seen_at: a legutolsó címlapi észlelés időpontja
   - latest_title: a legfrissebb észlelt cím
   - downloaded: le van-e már mentve a cikk (0 = nem, 1 = igen, -1 = hiba)
   - download_time: cikk letöltésének időpontja
   - http_status: HTTP státuszkód a letöltéskor
   - md_markitdown_path: markitdown által generált markdown elérési útja
   - md_trafilatura_path: trafilatura által generált markdown elérési útja
   - md_newspaper_path: newspaper4k által generált markdown elérési útja
   - meta_json_path: newspaper4k metaadatok és NLP eredmények JSON fájlja
   - publish_date: kinyert közzétételi dátum
   - authors: kinyert szerzők
   - summary: cikk összefoglaló (NLP)
   - keywords: kinyert kulcsszavak (NLP)

2. frontpage_snapshots:
   - id: egyedi azonosító
   - article_id: hivatkozás az articles.id-ra
   - source_file: forrás HTML fájl neve
   - scraped_at: címlapi mentés időpontja (a forrásfájlból kinyerve)
   - site: portál neve
   - order_num: címlapi pozíció / sorszám
   - title: cím ebben a mentésben
   - lead: beharangozó szöveg ebben a mentésben
   - section: rovat
   - media_type: média típusa (image, video, none)
   - media_url: média URL
   - media_alt: média alt szöveg
   - UNIQUE(article_id, source_file)
"""

import csv
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

DEFAULT_DB_PATH = Path(__file__).parent / "articles.db"
DEFAULT_CSV_PATH = Path(__file__).parent / "scraped_links_summary.csv"

TIMESTAMP_REGEX = re.compile(r"(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})")


def parse_timestamp_from_filename(filename: str) -> Optional[str]:
    """Időbélyeg kinyerése a fájlnévből ISO formátumban (YYYY-MM-DD HH:MM:SS)."""
    match = TIMESTAMP_REGEX.search(filename)
    if match:
        date_part = match.group(1)
        time_part = match.group(2).replace("-", ":")
        return f"{date_part} {time_part}"
    return None


def init_db(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Adatbázis sémájának inicializálása."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")

    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                link TEXT UNIQUE NOT NULL,
                site TEXT,
                first_seen_at DATETIME,
                last_seen_at DATETIME,
                latest_title TEXT,
                downloaded INTEGER DEFAULT 0,
                download_time DATETIME,
                http_status INTEGER,
                md_markitdown_path TEXT,
                md_trafilatura_path TEXT,
                md_newspaper_path TEXT,
                meta_json_path TEXT,
                publish_date TEXT,
                authors TEXT,
                summary TEXT,
                keywords TEXT
            );
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS frontpage_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
                source_file TEXT NOT NULL,
                scraped_at DATETIME,
                site TEXT,
                order_num INTEGER,
                title TEXT,
                lead TEXT,
                section TEXT,
                media_type TEXT,
                media_url TEXT,
                media_alt TEXT,
                UNIQUE(article_id, source_file)
            );
        """)

        conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_link ON articles(link);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_downloaded ON articles(downloaded);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_article_id ON frontpage_snapshots(article_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_source_file ON frontpage_snapshots(source_file);")

    return conn


def sync_csv_to_db(csv_path: Path = DEFAULT_CSV_PATH, db_path: Path = DEFAULT_DB_PATH):
    """
    scraped_links_summary.csv tartalmának szinkronizálása az SQLite adatbázisba.
    Biztosítja az egyedi cikkek rekordjait (articles) és az idősoros címlapi előfordulásokat (frontpage_snapshots).
    """
    if not csv_path.exists():
        print(f"[!] A megadott CSV fájl nem létezik: {csv_path}", file=sys.stderr)
        return

    conn = init_db(db_path)
    cursor = conn.cursor()

    # Meglévő cikk-linkek és ID-k betöltése memóriába
    cursor.execute("SELECT link, id, first_seen_at, last_seen_at FROM articles")
    link_cache = {row[0]: {"id": row[1], "first_seen_at": row[2], "last_seen_at": row[3]} for row in cursor.fetchall()}

    # Meglévő (article_id, source_file) párok a duplikáció elkerülésére
    cursor.execute("SELECT article_id, source_file FROM frontpage_snapshots")
    snapshot_cache = {(row[0], row[1]) for row in cursor.fetchall()}

    print(f"[+] CSV betöltése és szinkronizálás az adatbázissal: {csv_path.name} -> {db_path.name}...")
    
    new_articles_count = 0
    new_snapshots_count = 0

    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            link = (row.get("link") or "").strip()
            if not link:
                continue

            site = (row.get("site") or "").strip()
            title = (row.get("title") or "").strip()
            lead = (row.get("lead") or "").strip()
            section = (row.get("section") or "").strip()
            source_file = (row.get("source_file") or "").strip()
            media_type = (row.get("media_type") or "").strip()
            media_url = (row.get("media_url") or "").strip()
            media_alt = (row.get("media_alt") or "").strip()
            
            try:
                order_num = int(row.get("order") or 0)
            except ValueError:
                order_num = 0

            scraped_at = parse_timestamp_from_filename(source_file)

            # 1. Cikk azonosítása vagy beszúrása az articles táblába
            if link not in link_cache:
                cursor.execute("""
                    INSERT INTO articles (link, site, first_seen_at, last_seen_at, latest_title)
                    VALUES (?, ?, ?, ?, ?)
                """, (link, site, scraped_at, scraped_at, title))
                article_id = cursor.lastrowid
                link_cache[link] = {
                    "id": article_id,
                    "first_seen_at": scraped_at,
                    "last_seen_at": scraped_at,
                }
                new_articles_count += 1
            else:
                article_id = link_cache[link]["id"]
                # Időbélyegek és latest_title frissítése, ha szükséges
                cached = link_cache[link]
                updated_first = cached["first_seen_at"]
                updated_last = cached["last_seen_at"]
                
                if scraped_at:
                    if not updated_first or scraped_at < updated_first:
                        updated_first = scraped_at
                    if not updated_last or scraped_at >= updated_last:
                        updated_last = scraped_at
                        if title:
                            cursor.execute("""
                                UPDATE articles 
                                SET last_seen_at = ?, latest_title = ?
                                WHERE id = ?
                            """, (updated_last, title, article_id))
                    
                    if updated_first != cached["first_seen_at"]:
                        cursor.execute("UPDATE articles SET first_seen_at = ? WHERE id = ?", (updated_first, article_id))
                    
                    cached["first_seen_at"] = updated_first
                    cached["last_seen_at"] = updated_last

            # 2. Címlapi pillanatkép beszúrása a frontpage_snapshots táblába
            snapshot_key = (article_id, source_file)
            if snapshot_key not in snapshot_cache:
                cursor.execute("""
                    INSERT OR IGNORE INTO frontpage_snapshots 
                    (article_id, source_file, scraped_at, site, order_num, title, lead, section, media_type, media_url, media_alt)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (article_id, source_file, scraped_at, site, order_num, title, lead, section, media_type, media_url, media_alt))
                snapshot_cache.add(snapshot_key)
                new_snapshots_count += 1

    conn.commit()
    
    cursor.execute("SELECT COUNT(*) FROM articles")
    total_articles = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM frontpage_snapshots")
    total_snapshots = cursor.fetchone()[0]

    conn.close()

    print(f"[✓] Szinkronizálás befejezve:")
    print(f"    - Új cikkek (articles):           +{new_articles_count:4d} (Összesen: {total_articles})")
    print(f"    - Új pillanatképek (snapshots):  +{new_snapshots_count:4d} (Összesen: {total_snapshots})")


def print_db_summary(db_path: Path = DEFAULT_DB_PATH):
    """Adatbázis statisztikáinak megjelenítése."""
    if not db_path.exists():
        print(f"[!] Adatbázis nem található: {db_path}")
        return

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM articles")
    total_articles = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM articles WHERE downloaded = 1")
    downloaded_articles = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM frontpage_snapshots")
    total_snapshots = cursor.fetchone()[0]

    cursor.execute("""
        SELECT site, COUNT(*) as cnt 
        FROM articles 
        GROUP BY site 
        ORDER BY cnt DESC
    """)
    site_counts = cursor.fetchall()

    cursor.execute("""
        SELECT COUNT(*) FROM (
            SELECT article_id, COUNT(*) as c 
            FROM frontpage_snapshots 
            GROUP BY article_id 
            HAVING c > 1
        )
    """)
    multi_seen = cursor.fetchone()[0]

    print("\n" + "=" * 55)
    print(f"ADATBÁZIS STATISZTIKA ({db_path.name})")
    print("=" * 55)
    print(f"  Egyedi cikkek száma:            {total_articles:4d}")
    print(f"  Többször megjelent cikkek:      {multi_seen:4d} ({multi_seen/total_articles*100:5.1f}% ha van adat)" if total_articles else "  Nincs cikk")
    print(f"  Címlapi pillanatképek száma:    {total_snapshots:4d}")
    print(f"  Letöltött és feldolgozott:      {downloaded_articles:4d} / {total_articles}")
    print("-" * 55)
    print("  Portálonkénti egyedi cikkek:")
    for s, c in site_counts:
        print(f"    - {s:<15}: {c:4d}")
    print("=" * 55 + "\n")

    conn.close()


if __name__ == "__main__":
    sync_csv_to_db()
    print_db_summary()
