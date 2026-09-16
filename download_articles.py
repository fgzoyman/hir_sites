#!/usr/bin/env python3
"""
download_articles.py

Cikkek letöltése és feldolgozása az articles.db adatbázis alapján.

Funkciók:
1. Még le nem mentett cikkek (downloaded == 0) lekérdezése az SQLite adatbázisból.
2. Portálonkénti kíméletes lekérés (rate limiting, timeout, valódi böngésző User-Agent).
3. Háromutas Markdown konverzió cikkoldalanként az összehasonlításhoz:
   - MarkItDown: nyers HTML -> Markdown átalakítás
   - Trafilatura: fókuszált cikkszöveg- és főtartalom-kiemelés -> Markdown
   - Newspaper4k: cikkfeldolgozó szövegkimenet -> Markdown
4. Newspaper4k strukturált metaadatok és NLP kinyerése:
   - Alapadatok: cím, szerzők, megjelenési dátum, címkék, canonical_link
   - Médiaelemek: top_image, meta_img, images, movies
   - Webes / SEO metaadatok: meta_description, meta_keywords, meta_lang, meta_site_name, meta_data
   - NLP adatok: summary (összefoglaló), keywords, keyword_scores
5. Eredmények mentése:
   - Fájlrendszer: scraped_articles/{site}/article_{id}/
       - article_{id}_markitdown.md
       - article_{id}_trafilatura.md
       - article_{id}_newspaper.md
       - article_{id}_meta_nlp.json
   - Adatbázis: articles tábla frissítése (downloaded = 1, elérési utak, kinyert főbb adatok).
"""

import argparse
import io
import json
import random
import re
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

# Biztosítjuk a lokális virtuális környezet elérhetőségét
venv_site_packages = Path(__file__).parent / ".venv/lib/python3.12/site-packages"
if venv_site_packages.exists() and str(venv_site_packages.resolve()) not in sys.path:
    sys.path.insert(0, str(venv_site_packages.resolve()))

import requests
import trafilatura
from markitdown import MarkItDown
from newspaper import Article

DEFAULT_DB_PATH = Path(__file__).parent / "articles.db"
DEFAULT_OUTPUT_DIR = Path(__file__).parent / "scraped_articles"

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:130.0) Gecko/20100101 Firefox/130.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
]


def sanitize_filename(name: str) -> str:
    """Biztonságos mappa- és fájlnév generálás."""
    cleaned = re.sub(r'[\\/*?:"<>|]', "", name)
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned.strip("._") or "unknown"


def fetch_html(url: str, session: requests.Session, timeout: int = 15, max_retries: int = 3) -> tuple[int, str]:
    """
    HTML letöltése emberi viselkedéshez hasonló részletes böngésző fejlécekkel és refererrel.
    Átmeneti hálózati időkiesés vagy reset esetén automatikus újrapóbálkozással (max_retries).
    """
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    for attempt in range(1, max_retries + 1):
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "hu-HU,hu;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": origin + "/",
            "DNT": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }
        try:
            resp = session.get(url, headers=headers, timeout=timeout)
            resp.encoding = resp.apparent_encoding or "utf-8"
            return resp.status_code, resp.text
        except Exception as e:
            if attempt < max_retries:
                time.sleep(1.0 * attempt)
            else:
                print(f"[!] Hiba a letöltéskor ({url}) {max_retries} próbálkozás után: {e}", file=sys.stderr)
                return 0, ""


def extract_markitdown(html_content: str, md_converter: MarkItDown) -> str:
    """HTML konvertálása MarkItDown segítségével."""
    try:
        stream = io.BytesIO(html_content.encode("utf-8", errors="ignore"))
        result = md_converter.convert_stream(stream, file_extension=".html")
        return result.text_content or ""
    except Exception as e:
        return f"<!-- MarkItDown konverziós hiba: {e} -->"


def extract_trafilatura(html_content: str, url: str) -> str:
    """Főtartalom kinyerése és formázása Markdownként Trafilatura használatával."""
    try:
        extracted = trafilatura.extract(
            html_content,
            url=url,
            output_format="markdown",
            include_links=True,
            include_images=True,
            include_tables=True,
        )
        return extracted or ""
    except Exception as e:
        return f"<!-- Trafilatura konverziós hiba: {e} -->"


def process_newspaper(html_content: str, url: str) -> tuple[str, Dict[str, Any]]:
    """Cikk feldolgozása, NLP futtatása és metaadatok kinyerése Newspaper4k-val."""
    meta: Dict[str, Any] = {}
    md_text = ""
    try:
        article = Article(url, language="hu")
        article.download(input_html=html_content)
        article.parse()
        try:
            article.nlp()
        except Exception as nlp_err:
            meta["nlp_error"] = str(nlp_err)

        # Metaadatok felépítése
        publish_date_str = ""
        if article.publish_date:
            try:
                publish_date_str = article.publish_date.isoformat()
            except Exception:
                publish_date_str = str(article.publish_date)

        meta = {
            "title": article.title or "",
            "authors": article.authors or [],
            "publish_date": publish_date_str,
            "tags": list(article.tags) if article.tags else [],
            "canonical_link": article.canonical_link or "",
            "top_image": article.top_image or "",
            "meta_img": article.meta_img or "",
            "images": list(article.images) if article.images else [],
            "movies": list(article.movies) if article.movies else [],
            "meta_description": article.meta_description or "",
            "meta_keywords": article.meta_keywords or [],
            "meta_lang": article.meta_lang or "",
            "meta_site_name": article.meta_site_name or "",
            "summary": article.summary or "",
            "keywords": article.keywords or [],
            "keyword_scores": article.keyword_scores if hasattr(article, "keyword_scores") else {},
            "meta_data": article.meta_data or {},
        }

        # Newspaper Markdown formátum előállítása
        lines = []
        if article.title:
            lines.append(f"# {article.title}\n")
        if publish_date_str or article.authors:
            sub = []
            if publish_date_str:
                sub.append(f"Dátum: {publish_date_str}")
            if article.authors:
                sub.append(f"Szerző(k): {', '.join(article.authors)}")
            lines.append(f"*{' | '.join(sub)}*\n")
        if article.top_image:
            lines.append(f"![Kiemelt kép]({article.top_image})\n")
        if article.text:
            lines.append(article.text)
        md_text = "\n".join(lines)

    except Exception as e:
        meta["error"] = str(e)
        md_text = f"<!-- Newspaper feldolgozási hiba: {e} -->"

    return md_text, meta


def process_single_article(
    article_id: int,
    link: str,
    site: str,
    session: requests.Session,
    md_converter: MarkItDown,
    output_base_dir: Path,
) -> Dict[str, Any]:
    """Egy cikk letöltése, 3-utas konverziója és mentése."""
    site_folder = sanitize_filename(site.lower() if site else "other")
    target_dir = output_base_dir / site_folder / f"article_{article_id}"
    target_dir.mkdir(parents=True, exist_ok=True)

    status_code, html_content = fetch_html(link, session)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if status_code != 200 or not html_content:
        return {
            "id": article_id,
            "downloaded": -1 if status_code != 200 else 0,
            "http_status": status_code,
            "download_time": now_str,
            "error": "Sikertelen HTTP lekérés",
        }

    # 1. MarkItDown
    md_markitdown = extract_markitdown(html_content, md_converter)
    md_markitdown_file = target_dir / f"article_{article_id}_markitdown.md"
    md_markitdown_file.write_text(md_markitdown, encoding="utf-8")

    # 2. Trafilatura
    md_trafilatura = extract_trafilatura(html_content, link)
    md_trafilatura_file = target_dir / f"article_{article_id}_trafilatura.md"
    md_trafilatura_file.write_text(md_trafilatura, encoding="utf-8")

    # 3. Newspaper4k (szöveg + metaadatok + NLP)
    md_newspaper, meta_nlp = process_newspaper(html_content, link)
    md_newspaper_file = target_dir / f"article_{article_id}_newspaper.md"
    md_newspaper_file.write_text(md_newspaper, encoding="utf-8")

    meta_json_file = target_dir / f"article_{article_id}_meta_nlp.json"
    meta_json_file.write_text(json.dumps(meta_nlp, ensure_ascii=False, indent=2), encoding="utf-8")

    # Relatív útvonalak a projekt gyökeréhez képest
    project_root = Path(__file__).resolve().parent
    return {
        "id": article_id,
        "downloaded": 1,
        "http_status": status_code,
        "download_time": now_str,
        "md_markitdown_path": str(md_markitdown_file.resolve().relative_to(project_root)),
        "md_trafilatura_path": str(md_trafilatura_file.resolve().relative_to(project_root)),
        "md_newspaper_path": str(md_newspaper_file.resolve().relative_to(project_root)),
        "meta_json_path": str(meta_json_file.resolve().relative_to(project_root)),
        "publish_date": meta_nlp.get("publish_date") or "",
        "authors": ", ".join(meta_nlp.get("authors") or []),
        "summary": meta_nlp.get("summary") or "",
        "keywords": ", ".join(meta_nlp.get("keywords") or []),
        "newspaper_title": meta_nlp.get("title") or "",
    }


def interleave_articles_by_site(articles: list[tuple]) -> list[tuple]:
    """
    Cikkek portálonkénti csoportosítása és összefésülése (round-robin / shuffle),
    hogy ne ugyanahhoz a szerverhez menjen egymás után sok lekérés.
    """
    by_site: Dict[str, list[tuple]] = {}
    for art in articles:
        site = (art[2] or "unknown").lower()
        by_site.setdefault(site, []).append(art)

    # Minden portál belső listáját is megkeverjük
    for site, items in by_site.items():
        random.shuffle(items)

    interleaved = []
    # Portálok sorrendje is dinamikus legyen minden körben
    site_keys = list(by_site.keys())
    while any(by_site.values()):
        random.shuffle(site_keys)
        for s in site_keys:
            if by_site[s]:
                interleaved.append(by_site[s].pop(0))

    return interleaved


def simulate_human_reading_delay(base_min: float = 1.0, base_max: float = 2.5):
    """
    Emberi böngészési és olvasási tempó szimulációja:
    - Véletlenszerű várakozás mikroszekundumos jitterrel
    - Időnként egy-egy hosszabb olvasási szünet (pl. 15%-os eséllyel 3-5 mp)
    """
    sleep_time = random.uniform(base_min, base_max)
    # 15% eséllyel hosszabb olvasási szünetet tartunk
    if random.random() < 0.15:
        sleep_time += random.uniform(1.5, 3.5)
    time.sleep(sleep_time)


def download_articles(
    db_path: Path = DEFAULT_DB_PATH,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    limit: Optional[int] = None,
    site_filter: Optional[str] = None,
    shuffle_sites: bool = True,
    delay_range: tuple[float, float] = (1.0, 2.5),
):
    """Még le nem mentett cikkek letöltése és szinkronizálása az adatbázissal."""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    query = "SELECT id, link, site, latest_title FROM articles WHERE downloaded = 0"
    params = []
    if site_filter:
        query += " AND LOWER(site) = LOWER(?)"
        params.append(site_filter)
    query += " ORDER BY id ASC"

    cursor.execute(query, params)
    pending_articles = cursor.fetchall()

    if shuffle_sites and not site_filter:
        pending_articles = interleave_articles_by_site(pending_articles)

    if limit:
        pending_articles = pending_articles[:limit]

    total_pending = len(pending_articles)
    if total_pending == 0:
        print("[i] Nincs letöltésre váró cikk az adatbázisban.")
        conn.close()
        return

    print(f"\n[+] Cikkek letöltésének indítása: {total_pending} cikk feldolgozása...")
    print(f"    - Stratégia: szerverek közötti kevert sorrend (round-robin interleave)")
    print(f"    - Célkönyvtár: {output_dir.resolve()}")

    session = requests.Session()
    md_converter = MarkItDown()

    successful = 0
    failed = 0

    for idx, (art_id, link, site, title) in enumerate(pending_articles, start=1):
        print(f"[{idx:3d}/{total_pending}] Letöltés (ID {art_id:4d} | {site:<12}): {link[:65]}...")

        res = process_single_article(art_id, link, site, session, md_converter, output_dir)

        if res["downloaded"] == 1:
            successful += 1
            cursor.execute("""
                UPDATE articles
                SET downloaded = 1,
                    download_time = ?,
                    http_status = ?,
                    md_markitdown_path = ?,
                    md_trafilatura_path = ?,
                    md_newspaper_path = ?,
                    meta_json_path = ?,
                    publish_date = ?,
                    authors = ?,
                    summary = ?,
                    keywords = ?
                WHERE id = ?
            """, (
                res["download_time"],
                res["http_status"],
                res["md_markitdown_path"],
                res["md_trafilatura_path"],
                res["md_newspaper_path"],
                res["meta_json_path"],
                res["publish_date"],
                res["authors"],
                res["summary"],
                res["keywords"],
                art_id,
            ))
            conn.commit()
            print(f"      [✓] Mentve: 3x MD + Meta/NLP JSON (Cím: {(res['newspaper_title'] or title)[:45]})")
        else:
            failed += 1
            cursor.execute("""
                UPDATE articles
                SET downloaded = ?,
                    download_time = ?,
                    http_status = ?
                WHERE id = ?
            """, (res["downloaded"], res["download_time"], res["http_status"], art_id))
            conn.commit()
            print(f"      [!] Sikertelen letöltés (Státusz: {res['http_status']})")

        # Kíméletes, emberi olvasási szünet a következő kérés előtt
        if idx < total_pending:
            simulate_human_reading_delay(delay_range[0], delay_range[1])

    conn.close()
    print("\n" + "=" * 55)
    print(f"LETÖLTÉSI ÖSSZESÍTŐ:")
    print(f"  Sikeres: {successful:4d}")
    print(f"  Sikertelen: {failed:4d}")
    print("=" * 55 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Cikkek letöltése és 3-utas Markdown/NLP feldolgozása.")
    parser.add_argument("--limit", type=int, default=None, help="Letöltendő cikkek maximális száma (teszteléshez)")
    parser.add_argument("--site", type=str, default=None, help="Szűrés adott portálra (pl. origo, blikk)")
    parser.add_argument("--no-shuffle", action="store_true", help="Ne keverje meg a portálok sorrendjét")
    parser.add_argument("--db", type=str, default=str(DEFAULT_DB_PATH), help="Adatbázis elérési útja")
    parser.add_argument("--output-dir", type=str, default=str(DEFAULT_OUTPUT_DIR), help="Cikkek mentési könyvtára")

    args = parser.parse_args()
    download_articles(
        db_path=Path(args.db),
        output_dir=Path(args.output_dir),
        limit=args.limit,
        site_filter=args.site,
        shuffle_sites=not args.no_shuffle,
    )


if __name__ == "__main__":
    main()
