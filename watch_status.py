#!/usr/bin/env python3
"""
watch_status.py

Segédmodul az articles.db adatbázis letöltési és feldolgozási állapotának
folyamatos vagy egyszeri lekérdezésére, terminálban és Python környezetben.
"""

import argparse
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

DEFAULT_DB_PATH = Path(__file__).parent / "articles.db"
DEFAULT_LOG_PATH = Path(__file__).parent / "download_articles.log"


def get_process_status() -> dict:
    """Ellenőrzi, hogy fut-e a háttérbeli letöltő folyamat."""
    try:
        out = subprocess.check_output(["pgrep", "-f", "download_articles.py"], text=True).strip()
        pids = [int(p) for p in out.splitlines() if p.strip()]
        return {"running": len(pids) > 0, "pids": pids}
    except Exception:
        return {"running": False, "pids": []}


def get_status_summary(db_path: Path = DEFAULT_DB_PATH) -> dict:
    """Részletes összesítés lekérése az adatbázisból."""
    if not db_path.exists():
        return {"error": f"Adatbázis nem található: {db_path}"}

    conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            site,
            COUNT(*) AS total,
            SUM(CASE WHEN downloaded = 1 THEN 1 ELSE 0 END) AS downloaded,
            SUM(CASE WHEN downloaded = 0 THEN 1 ELSE 0 END) AS pending,
            SUM(CASE WHEN downloaded = -1 THEN 1 ELSE 0 END) AS failed
        FROM articles
        GROUP BY site
        ORDER BY downloaded DESC, total DESC
    """)
    site_stats = []
    tot_articles = 0
    tot_downloaded = 0
    tot_pending = 0
    tot_failed = 0

    for site, total, downloaded, pending, failed in cursor.fetchall():
        pct = (downloaded / total * 100) if total else 0.0
        site_stats.append({
            "site": site,
            "total": total,
            "downloaded": downloaded,
            "pending": pending,
            "failed": failed,
            "pct": pct,
        })
        tot_articles += total
        tot_downloaded += downloaded
        tot_pending += pending
        tot_failed += failed

    conn.close()

    overall_pct = (tot_downloaded / tot_articles * 100) if tot_articles else 0.0
    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total": tot_articles,
        "downloaded": tot_downloaded,
        "pending": tot_pending,
        "failed": tot_failed,
        "percent": overall_pct,
        "sites": site_stats,
    }


def render_status(db_path: Path = DEFAULT_DB_PATH, log_path: Optional[Path] = DEFAULT_LOG_PATH, show_log_lines: int = 5) -> str:
    """Szöveges formátumú állapotjelentés összeállítása."""
    summary = get_status_summary(db_path)
    proc = get_process_status()

    if "error" in summary:
        return f"[!] {summary['error']}"

    proc_status = f"FUT (PID: {', '.join(map(str, proc['pids']))})" if proc["running"] else "LEÁLLT / NEM FUT"

    lines = []
    lines.append("=" * 66)
    lines.append(f" LETÖLTÉSI ÁLLAPOT -- {summary['timestamp']}")
    lines.append("=" * 66)
    lines.append(f"  Háttérfolyamat státusz : {proc_status}")
    lines.append(f"  Összes cikk száma      : {summary['total']}")
    lines.append(f"  Letöltve / feldolgozva : {summary['downloaded']:4d} ({summary['percent']:5.1f}%)")
    lines.append(f"  Még hátravan           : {summary['pending']:4d}")
    lines.append(f"  Hibás lekérés (HTTP!=200): {summary['failed']:4d}")
    lines.append("-" * 66)
    lines.append(f"  {'Portál':<14} | {'Összes':<6} | {'Kész':<6} | {'Hátralévő':<9} | {'Haladás':<8} | {'Hiba'}")
    lines.append("-" * 66)

    for s in summary["sites"]:
        bar_len = int(s["pct"] / 10)
        bar = "█" * bar_len + "░" * (10 - bar_len)
        lines.append(
            f"  {s['site']:<14} | {s['total']:6d} | {s['downloaded']:6d} | {s['pending']:9d} | {s['pct']:5.1f}% {bar} | {s['failed']:4d}"
        )
    lines.append("=" * 66)

    if log_path and log_path.exists() and show_log_lines > 0:
        lines.append(f"\n--- Utolsó {show_log_lines} naplóbejegyzés ({log_path.name}) ---")
        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as lf:
                log_lines = lf.readlines()[-show_log_lines:]
                for ll in log_lines:
                    lines.append("  " + ll.rstrip())
        except Exception as e:
            lines.append(f"  [!] Nem sikerült olvasni a logot: {e}")

    return "\n".join(lines)


def watch_progress(
    interval: float = 5.0,
    db_path: Path = DEFAULT_DB_PATH,
    log_path: Optional[Path] = DEFAULT_LOG_PATH,
    show_log_lines: int = 4,
    max_iterations: Optional[int] = None,
):
    """
    Folyamatos terminál figyelő ciklus (Ctrl+C-vel leállítható).
    """
    iteration = 0
    try:
        while True:
            # Képernyő törlése terminálban
            os.system("clear" if os.name != "nt" else "cls")
            print(render_status(db_path, log_path, show_log_lines))
            print(f"\n[Frissítés {interval} mp-enként, kilépés: Ctrl+C]\n")

            iteration += 1
            if max_iterations and iteration >= max_iterations:
                break

            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n[i] Megfigyelés leállítva.")


def main():
    parser = argparse.ArgumentParser(description="Adatbázis letöltési állapot és napló figyelése.")
    parser.add_argument("--watch", "-w", action="store_true", help="Folyamatos frissítés terminálban")
    parser.add_argument("--interval", "-i", type=float, default=5.0, help="Frissítési időköz másodpercben (alap: 5.0)")
    parser.add_argument("--db", type=str, default=str(DEFAULT_DB_PATH), help="Adatbázis útvonal")
    parser.add_argument("--log", type=str, default=str(DEFAULT_LOG_PATH), help="Logfájl útvonal")
    parser.add_argument("--lines", "-n", type=int, default=5, help="Megjelenítendő utolsó logsorok száma")
    parser.add_argument("--count", "-c", type=int, default=None, help="Frissítések maximális száma (alapértelmezetten végtelen)")

    args = parser.parse_args()

    if args.watch:
        watch_progress(
            interval=args.interval,
            db_path=Path(args.db),
            log_path=Path(args.log),
            show_log_lines=args.lines,
            max_iterations=args.count,
        )
    else:
        print(render_status(Path(args.db), Path(args.log), args.lines))


if __name__ == "__main__":
    main()
