#!/usr/bin/env python3
"""
analyze_frontpage_rovat_overlap.py

2. Téma: A címlapi és rovatoldali cikkek halmazának összehasonlítása és
átfedés-elemzése portálonként az articles.db pillanatkép-adatai alapján.
"""

import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

DB_PATH = Path("articles.db")


def load_overlap_data():
    conn = sqlite3.connect(str(DB_PATH))
    # Egy cikk megjelenhetett címlapon, rovatoldalon vagy mindkettőn
    # A forrásfájl nevében a '_rovat_' jelzi, ha rovatoldalról származik
    query = """
    SELECT 
        s.article_id,
        a.site,
        a.latest_title,
        a.link,
        s.source_file,
        s.scraped_at,
        CASE 
            WHEN s.source_file LIKE '%_rovat_%' THEN 'rovat'
            ELSE 'címlap'
        END AS source_type
    FROM frontpage_snapshots s
    JOIN articles a ON s.article_id = a.id
    """
    df_snaps = pd.read_sql_query(query, conn)
    conn.close()
    return df_snaps


def calculate_overlap_metrics(df_snaps: pd.DataFrame):
    # Cikkenként meghatározzuk, megjelent-e címlapon, rovatoldalon
    art_presence = df_snaps.groupby(["site", "article_id"]).agg(
        has_frontpage=("source_type", lambda s: (s == "címlap").any()),
        has_rovat=("source_type", lambda s: (s == "rovat").any()),
        frontpage_count=("source_type", lambda s: (s == "címlap").sum()),
        rovat_count=("source_type", lambda s: (s == "rovat").sum()),
    ).reset_index()

    art_presence["category"] = "egyéb"
    art_presence.loc[art_presence["has_frontpage"] & art_presence["has_rovat"], "category"] = "Közös (Címlap ÉS Rovat)"
    art_presence.loc[art_presence["has_frontpage"] & ~art_presence["has_rovat"], "category"] = "Csak címlapon"
    art_presence.loc[~art_presence["has_frontpage"] & art_presence["has_rovat"], "category"] = "Csak rovatoldalon"

    # Portál szintű összegzés
    rows = []
    for site, grp in art_presence.groupby("site"):
        total_arts = len(grp)
        front_arts = grp["has_frontpage"].sum()
        rovat_arts = grp["has_rovat"].sum()
        both_arts = (grp["has_frontpage"] & grp["has_rovat"]).sum()
        only_front = (grp["has_frontpage"] & ~grp["has_rovat"]).sum()
        only_rovat = (~grp["has_frontpage"] & grp["has_rovat"]).sum()

        # Átfedési arányok (Jaccard index és átfedési % a címlaphoz képest)
        overlap_pct_of_front = (both_arts / front_arts * 100) if front_arts > 0 else 0
        overlap_pct_of_rovat = (both_arts / rovat_arts * 100) if rovat_arts > 0 else 0
        jaccard_similarity = (both_arts / total_arts * 100) if total_arts > 0 else 0

        rows.append({
            "site": site,
            "osszes_egyedi_cikk": total_arts,
            "cimlapon_megjelent": front_arts,
            "rovatban_megjelent": rovat_arts,
            "kozos_cikkek": both_arts,
            "csak_cimlap": only_front,
            "csak_rovat": only_rovat,
            "cimlap_atfedese_rovattal_pct": round(overlap_pct_of_front, 1),
            "rovat_atfedese_cimlappal_pct": round(overlap_pct_of_rovat, 1),
            "jaccard_hasonlosag_pct": round(jaccard_similarity, 1),
        })

    summary_df = pd.DataFrame(rows)
    return art_presence, summary_df


def plot_overlap(summary_df: pd.DataFrame):
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle("Címlapi és rovatoldali cikkek megoszlása és átfedése", fontsize=15, fontweight="bold")

    sites = summary_df["site"].tolist()
    y_pos = range(len(sites))

    # 1. Stacked Bar Chart: cikkek elhelyezkedése
    ax1 = axes[0]
    p1 = ax1.barh(y_pos, summary_df["csak_cimlap"], label="Csak címlapon", color="#e41a1c", alpha=0.85)
    p2 = ax1.barh(y_pos, summary_df["kozos_cikkek"], left=summary_df["csak_cimlap"], label="Közös (Címlap + Rovat)", color="#4daf4a", alpha=0.85)
    p3 = ax1.barh(y_pos, summary_df["csak_rovat"], left=summary_df["csak_cimlap"] + summary_df["kozos_cikkek"], label="Csak rovatoldalon", color="#377eb8", alpha=0.85)

    ax1.set_yticks(y_pos)
    ax1.set_yticklabels(sites)
    ax1.set_xlabel("Egyedi cikkek száma")
    ax1.set_title("Cikkek megoszlása (Darabszám)")
    ax1.legend(loc="lower right")

    # Értékek ráírása
    for i, total in enumerate(summary_df["osszes_egyedi_cikk"]):
        ax1.text(total + 15, i, f"Össz: {total}", va="center", fontsize=9, fontweight="bold")

    # 2. Címlapi cikkek lefedettsége a rovatok által
    ax2 = axes[1]
    bars = ax2.bar(summary_df["site"], summary_df["cimlap_atfedese_rovattal_pct"], color="#984ea3", alpha=0.85)
    ax2.set_title("Címlapi cikkek hány %-a található meg a rovatokban is?")
    ax2.set_ylabel("Címlapi átfedés (%)")
    ax2.tick_params(axis="x", rotation=25)
    ax2.set_ylim(0, 105)

    for b in bars:
        ax2.text(b.get_x() + b.get_width()/2, b.get_height() + 1.5, f"{b.get_height():.1f}%", ha="center", va="bottom", fontweight="bold")

    plt.tight_layout()
    plot_path = Path("frontpage_rovat_overlap.png")
    plt.savefig(plot_path, dpi=200)
    plt.close()
    return plot_path


if __name__ == "__main__":
    print("[+] Pillanatkép és cikkadatok betöltése...")
    df_snaps = load_overlap_data()
    art_presence, summary_df = calculate_overlap_metrics(df_snaps)
    plot_path = plot_overlap(summary_df)

    print("\n" + "=" * 80)
    print("CÍMLAPI ÉS ROVATOLDALI ÁTFEDÉS TÁBLÁZAT")
    print("=" * 80)
    print(summary_df.to_string(index=False))
    print(f"\n[✓] Diagram elmentve: {plot_path.resolve()}")
