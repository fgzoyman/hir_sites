#!/usr/bin/env python3
"""
analyze_position_dynamics.py

3. Téma: Pozíció- és rangmozgási dinamika elemzése a kibővített adatbázison.
Vizsgálja a több mentésben szereplő cikkek elmozdulásait, emelkedő és süllyedő
cikkeket, valamint a címlapi stabilitást.
"""

import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

DB_PATH = Path("articles.db")


def load_snapshots_for_dynamics():
    conn = sqlite3.connect(str(DB_PATH))
    # Kizárólag a fő címlapi pillanatképeket elemezzük a tiszta pozíció- és rangmozgáshoz
    query = """
    SELECT 
        s.article_id,
        a.site,
        a.latest_title,
        s.source_file,
        s.scraped_at,
        s.order_num
    FROM frontpage_snapshots s
    JOIN articles a ON s.article_id = a.id
    WHERE s.source_file NOT LIKE '%_rovat_%'
    ORDER BY s.article_id, s.scraped_at ASC
    """
    df_snaps = pd.read_sql_query(query, conn)
    conn.close()
    return df_snaps


def calculate_position_dynamics(df_snaps: pd.DataFrame):
    # Egyedi mentési időpontok
    timepoints = sorted(df_snaps["scraped_at"].unique())

    # Cikkenkénti aggregáció
    metrics = []
    for (site, art_id), grp in df_snaps.groupby(["site", "article_id"]):
        n_snaps = len(grp)
        orders = grp["order_num"].tolist()
        first_order = orders[0]
        last_order = orders[-1]
        min_order = min(orders)
        max_order = max(orders)

        # Mozgás iránya és nagysága (kisebb sorszám = előkelőbb hely)
        # Ha a pozíció csökken számszerűen (pl. 20 -> 5), az előlépést / emelkedést jelent!
        order_changes = [orders[i] - orders[i+1] for i in range(len(orders) - 1)]
        max_rise = max([0] + order_changes) # pozitív, ha előrébb lépett
        max_drop = max([0] + [-d for d in order_changes]) # pozitív, ha hátrébb csúszott
        net_movement = first_order - last_order # pozitív = összességében előrébb lépett

        pos_range = max_order - min_order
        pos_std = np.std(orders) if len(orders) > 1 else 0.0

        metrics.append({
            "site": site,
            "article_id": art_id,
            "title": grp["latest_title"].iloc[0],
            "n_snaps": n_snaps,
            "first_order": first_order,
            "last_order": last_order,
            "min_order": min_order,
            "max_order": max_order,
            "pos_range": pos_range,
            "pos_std": round(pos_std, 2),
            "max_rise": max_rise,
            "max_drop": max_drop,
            "net_movement": net_movement,
            "has_order_change": pos_range > 0,
            "significant_rise": max_rise >= 5,
            "significant_drop": max_drop >= 5,
        })

    df_metrics = pd.DataFrame(metrics)

    # Portál szintű összefoglaló
    site_summary = []
    for site, grp in df_metrics.groupby("site"):
        total_arts = len(grp)
        multi_arts = grp[grp["n_snaps"] >= 2]
        multi_cnt = len(multi_arts)
        multi_pct = (multi_cnt / total_arts * 100) if total_arts > 0 else 0

        shifted_arts = multi_arts[multi_arts["has_order_change"]]
        shift_pct = (len(shifted_arts) / multi_cnt * 100) if multi_cnt > 0 else 0

        rising_cnt = len(multi_arts[multi_arts["significant_rise"]])
        dropping_cnt = len(multi_arts[multi_arts["significant_drop"]])

        avg_std = multi_arts["pos_std"].mean() if multi_cnt > 0 else 0.0
        avg_range = multi_arts["pos_range"].mean() if multi_cnt > 0 else 0.0

        site_summary.append({
            "site": site,
            "cimlapi_cikkek": total_arts,
            "tobbszor_megjelent": multi_cnt,
            "tobb_mentes_arany_pct": round(multi_pct, 1),
            "poziciot_valtott_db": len(shifted_arts),
            "poziciovaltok_aranya_pct": round(shift_pct, 1),
            "jelentos_emelkedes_db": rising_cnt,
            "jelentos_esessel_db": dropping_cnt,
            "atlagos_pozicio_szoras": round(avg_std, 2),
            "atlagos_pozicio_sav": round(avg_range, 1),
        })

    df_site_summary = pd.DataFrame(site_summary)

    # Legnagyobb ugrást produkáló cikkek
    top_rising = df_metrics.sort_values(by="max_rise", ascending=False).head(8)
    top_falling = df_metrics.sort_values(by="max_drop", ascending=False).head(8)

    return df_metrics, df_site_summary, top_rising, top_falling


def plot_position_dynamics(df_site_summary: pd.DataFrame, df_metrics: pd.DataFrame):
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle("Címlapi rangmozgási dinamika és stabilitás portálonként", fontsize=15, fontweight="bold")

    sites = df_site_summary["site"].tolist()
    x = np.arange(len(sites))
    width = 0.35

    # 1. Mozgás dinamika: pozíciót váltó cikkek vs. stabil cikkek aránya
    ax1 = axes[0]
    bars1 = ax1.bar(x - width/2, df_site_summary["tobb_mentes_arany_pct"], width, label="Több mentésben jelen lévő (%)", color="#41b6c4", alpha=0.85)
    bars2 = ax1.bar(x + width/2, df_site_summary["poziciovaltok_aranya_pct"], width, label="Ebből pozíciót változtató (%)", color="#225ea8", alpha=0.85)

    ax1.set_xticks(x)
    ax1.set_xticklabels(sites, rotation=25)
    ax1.set_ylabel("Arány (%)")
    ax1.set_title("Cikkek megjelenési és mozgási aránya")
    ax1.legend(loc="upper right")
    ax1.set_ylim(0, 105)

    for b in bars1:
        ax1.text(b.get_x() + b.get_width()/2, b.get_height() + 1.5, f"{b.get_height():.0f}%", ha="center", va="bottom", fontsize=8)
    for b in bars2:
        ax1.text(b.get_x() + b.get_width()/2, b.get_height() + 1.5, f"{b.get_height():.0f}%", ha="center", va="bottom", fontsize=8, fontweight="bold")

    # 2. Pozíció szórás (mobilitási index)
    ax2 = axes[1]
    bars_std = ax2.bar(sites, df_site_summary["atlagos_pozicio_szoras"], color="#fc4e2a", alpha=0.85)
    ax2.set_title("Átlagos pozíció-szórás (Címlapi mobilitási index)")
    ax2.set_ylabel("Pozíció szórás (helyezések)")
    ax2.tick_params(axis="x", rotation=25)

    for b in bars_std:
        ax2.text(b.get_x() + b.get_width()/2, b.get_height() + 0.3, f"{b.get_height():.2f}", ha="center", va="bottom", fontweight="bold")

    plt.tight_layout()
    plot_path = Path("position_dynamics_analysis.png")
    plt.savefig(plot_path, dpi=200)
    plt.close()
    return plot_path


if __name__ == "__main__":
    print("[+] Címlapi pillanatkép adatok betöltése...")
    df_snaps = load_snapshots_for_dynamics()
    print(f"    - Betöltve: {len(df_snaps)} címlapi pillanatkép-rekord")

    df_metrics, df_site_summary, top_rising, top_falling = calculate_position_dynamics(df_snaps)
    plot_path = plot_position_dynamics(df_site_summary, df_metrics)

    print("\n" + "=" * 80)
    print("CÍMLAPI MOZGÁSI DINAMIKA ÖSSZEFOGLALÓ")
    print("=" * 80)
    print(df_site_summary.to_string(index=False))

    print("\n" + "=" * 80)
    print("TOP 5 LEGNAGYOBB CÍMLAPI ELŐRELÉPÉS (RISING ARTICLES)")
    print("=" * 80)
    for _, r in top_rising.head(5).iterrows():
        print(f"  +{r['max_rise']:2d} hely | {r['site']:<12} | Pozíció: {r['first_order']} -> {r['min_order']} | {r['title'][:60]}")

    print("\n" + "=" * 80)
    print("TOP 5 LEGNAGYOBB CÍMLAPI VISSZAESÉS (FALLING ARTICLES)")
    print("=" * 80)
    for _, r in top_falling.head(5).iterrows():
        print(f"  -{r['max_drop']:2d} hely | {r['site']:<12} | Pozíció: {r['first_order']} -> {r['max_order']} | {r['title'][:60]}")

    print(f"\n[✓] Diagram elmentve: {plot_path.resolve()}")
