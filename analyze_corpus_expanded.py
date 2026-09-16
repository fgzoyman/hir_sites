#!/usr/bin/env python3
"""
analyze_corpus_expanded.py

1. Téma: A kibővített cikkanyag (4448 cikk) összehasonlító tartalmi, terjedelmi
és hangulati elemzése portálonként.
"""

import json
import sqlite3
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

DB_PATH = Path("articles.db")

HU_STOPWORDS = {
    "a", "az", "egy", "be", "ki", "le", "fel", "meg", "el", "at", "ra", "re",
    "rol", "rol", "ban", "ben", "ba", "be", "hoz", "hez", "hoz", "val", "vel",
    "nem", "is", "hogy", "mint", "ha", "de", "es", "vagy", "csak", "mar", "meg",
    "itt", "ott", "most", "ugy", "igy", "volt", "lesz", "van", "vannak", "voltak",
    "lett", "lettek", "volna", "kell", "lehet", "miatt", "után", "utan", "elott",
    "alatt", "szerint", "kozott", "között", "ellen", "mellett", "soran", "során",
    "altal", "által", "mind", "minden", "senki", "sem", "semmi", "ahol", "amikor",
    "aki", "akik", "amely", "amelyek", "amit", "amiket", "nagyon", "sok", "tobb",
    "több", "nagy", "uj", "új", "alapjan", "alapján", "kapcsan", "kapcsán", "ez",
    "az", "ezt", "azt", "ebben", "abban", "ebbol", "abbol", "ennek", "annak",
    "neki", "nekik", "veluk", "vele", "roluk", "rola", "tehat", "tehát", "pedig",
    "hiszen", "ezert", "ezért", "ugyanis", "viszont", "amig", "amíg", "ma",
    "tegnap", "holnap", "nap", "ev", "év", "évben", "evben", "soran", "miatt"
}

POSITIVE_TERMS = {
    "siker", "sikeres", "győzelem", "győzött", "rekord", "bravúr", "fejlődés",
    "növekedés", "erősödik", "javul", "elismerés", "támogatás", "együttműködés",
    "stabilitás", "áttörés", "megmentette", "öröm", "ünnep", "történelmi",
    "pozitív", "eredményes", "kiemelkedő", "virágzik", "remény", "megállapodás"
}

NEGATIVE_CRISIS_TERMS = {
    "válság", "veszteség", "katasztrófa", "omlás", "zuhanás", "tragédia", "halál",
    "halálos", "elhunyt", "gyász", "dráma", "csőd", "rekorddrága", "veszély",
    "aggodalom", "infláció", "drágulás", "bezár", "leáll", "összeomlott", "áldozat",
    "baleset", "kár", "gyilkosság", "botrány", "szegénység", "hiány", "fenyegetés"
}

WAR_TERMS = {
    "háború", "katona", "hadsereg", "támadás", "rakéta", "drón", "orosz", "ukrán",
    "putyin", "zelenszkij", "front", "fegyver", "légicsapás", "hadművelet", "bomba",
    "nato", "védelem", "harc", "tüzérség", "veszteség", "hadifogoly", "offenzíva"
}

ECONOMY_TERMS = {
    "forint", "euró", "árfolyam", "kamat", "mnb", "infláció", "költségvetés",
    "adó", "gazdaság", "recesszió", "gdp", "beruházás", "fizetés", "bér",
    "nyugdíj", "drágulás", "áremelés", "üzlet", "profit", "tőzsde", "bank"
}


def clean_tokens(text: str) -> list[str]:
    import re
    words = re.findall(r"[a-záéíóöőúüű]{3,}", (text or "").lower())
    return [w for w in words if w not in HU_STOPWORDS]


def load_corpus_data():
    conn = sqlite3.connect(str(DB_PATH))
    query = """
    SELECT id, link, site, latest_title, md_trafilatura_path, md_markitdown_path, meta_json_path, authors, summary, keywords
    FROM articles
    WHERE downloaded = 1
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


def analyze_article_corpus(df: pd.DataFrame):
    results = []
    portal_tokens = Counter()
    portal_kw_counter = {}

    for _, row in df.iterrows():
        site = row["site"] or "Ismeretlen"
        title = str(row["latest_title"] or "")
        traf_path = Path(row["md_trafilatura_path"]) if row["md_trafilatura_path"] else None

        content = ""
        if traf_path and traf_path.exists():
            try:
                content = traf_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                pass

        # Ha a trafilatura üres volt, megpróbáljuk a markitdownt
        if not content and row["md_markitdown_path"]:
            mp = Path(row["md_markitdown_path"])
            if mp.exists():
                try:
                    content = mp.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    pass

        words = clean_tokens(f"{title} {content}")
        text_lower = f"{title} {content}".lower()
        word_count = len(content.split())
        char_count = len(content)

        # Tematika és szótár számlálók
        pos_cnt = sum(1 for t in POSITIVE_TERMS if t in text_lower)
        neg_cnt = sum(1 for t in NEGATIVE_CRISIS_TERMS if t in text_lower)
        war_cnt = sum(1 for t in WAR_TERMS if t in text_lower)
        econ_cnt = sum(1 for t in ECONOMY_TERMS if t in text_lower)

        # Kulcsszavak a JSON metaadatból ha van
        kws = []
        if row["keywords"]:
            kws = [k.strip().lower() for k in str(row["keywords"]).split(",") if k.strip()]
        elif row["meta_json_path"]:
            jp = Path(row["meta_json_path"])
            if jp.exists():
                try:
                    meta = json.loads(jp.read_text(encoding="utf-8"))
                    kws = [k.strip().lower() for k in meta.get("keywords", []) if k.strip()]
                except Exception:
                    pass

        if site not in portal_kw_counter:
            portal_kw_counter[site] = Counter()
        for kw in kws:
            if len(kw) > 2 and kw not in HU_STOPWORDS:
                portal_kw_counter[site][kw] += 1

        results.append({
            "id": row["id"],
            "site": site,
            "title": title,
            "word_count": word_count,
            "char_count": char_count,
            "pos_score": pos_cnt,
            "neg_score": neg_cnt,
            "net_sentiment": pos_cnt - neg_cnt,
            "is_war": war_cnt >= 2,
            "is_econ": econ_cnt >= 2,
            "war_count": war_cnt,
            "econ_count": econ_cnt,
        })

    df_res = pd.DataFrame(results)
    return df_res, portal_kw_counter


def generate_summary_and_plot(df_res: pd.DataFrame, portal_kw_counter: dict):
    # Portál szintű aggregáció
    summary = df_res.groupby("site").agg(
        cikkek_szama=("id", "count"),
        atlag_szoszam=("word_count", "mean"),
        median_szoszam=("word_count", "median"),
        atlag_karakterszam=("char_count", "mean"),
        pozitiv_arany=("pos_score", lambda s: (s > 0).mean() * 100),
        negativ_arany=("neg_score", lambda s: (s > 0).mean() * 100),
        haborus_cikkek_pct=("is_war", lambda s: s.mean() * 100),
        gazdasagi_cikkek_pct=("is_econ", lambda s: s.mean() * 100),
        netto_hangulat=("net_sentiment", "mean")
    ).reset_index()

    # Kerekítés
    summary["atlag_szoszam"] = summary["atlag_szoszam"].round(1)
    summary["median_szoszam"] = summary["median_szoszam"].round(1)
    summary["atlag_karakterszam"] = summary["atlag_karakterszam"].round(0)
    summary["pozitiv_arany"] = summary["pozitiv_arany"].round(1)
    summary["negativ_arany"] = summary["negativ_arany"].round(1)
    summary["haborus_cikkek_pct"] = summary["haborus_cikkek_pct"].round(1)
    summary["gazdasagi_cikkek_pct"] = summary["gazdasagi_cikkek_pct"].round(1)
    summary["netto_hangulat"] = summary["netto_hangulat"].round(2)

    # Top kulcsszavak portálonként
    top_kws_by_site = {}
    for site, cnt in portal_kw_counter.items():
        top_kws_by_site[site] = [w for w, _ in cnt.most_common(6)]

    # Ábra készítése
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("Kibővített cikkanyag portálonkénti összehasonlítása (N = 4448 cikk)", fontsize=16, fontweight="bold")

    sites = summary["site"].tolist()
    colors = ["#2b5c8f", "#d95f02", "#7570b3", "#e7298a", "#1b9e77", "#e6ab02"]
    site_color_map = {s: colors[i % len(colors)] for i, s in enumerate(sites)}
    plot_colors = [site_color_map[s] for s in sites]

    # 1. Cikkek száma és átlagos szószám
    ax1 = axes[0, 0]
    bars1 = ax1.bar(summary["site"], summary["cikkek_szama"], color=plot_colors, alpha=0.85)
    ax1.set_title("Cikkek száma portálonként")
    ax1.set_ylabel("Cikkek darabszáma")
    ax1.tick_params(axis="x", rotation=25)
    for b in bars1:
        ax1.text(b.get_x() + b.get_width()/2, b.get_height() + 15, f"{int(b.get_height())}", ha="center", va="bottom", fontsize=9)

    # 2. Medián szószám
    ax2 = axes[0, 1]
    bars2 = ax2.bar(summary["site"], summary["median_szoszam"], color=plot_colors, alpha=0.85)
    ax2.set_title("Cikkek medián szószáma (tényleges terjedelem)")
    ax2.set_ylabel("Szavak száma (medián)")
    ax2.tick_params(axis="x", rotation=25)
    for b in bars2:
        ax2.text(b.get_x() + b.get_width()/2, b.get_height() + 8, f"{int(b.get_height())}", ha="center", va="bottom", fontsize=9)

    # 3. Háborús és gazdasági témájú cikkek aránya
    ax3 = axes[1, 0]
    import numpy as np
    x = np.arange(len(sites))
    width = 0.35
    ax3.bar(x - width/2, summary["haborus_cikkek_pct"], width, label="Háborús fókuszú (%)", color="#b2182b", alpha=0.85)
    ax3.bar(x + width/2, summary["gazdasagi_cikkek_pct"], width, label="Gazdasági fókuszú (%)", color="#2166ac", alpha=0.85)
    ax3.set_xticks(x)
    ax3.set_xticklabels(sites, rotation=25)
    ax3.set_ylabel("Cikkek aránya (%)")
    ax3.set_title("Témaarányok: Háború vs. Gazdaság")
    ax3.legend()

    # 4. Nettó hangulatindex
    ax4 = axes[1, 1]
    bars4 = ax4.bar(summary["site"], summary["netto_hangulat"], color=[
        "#2ca02c" if v >= 0 else "#d62728" for v in summary["netto_hangulat"]
    ], alpha=0.85)
    ax4.axhline(0, color="gray", linestyle="--", linewidth=0.8)
    ax4.set_title("Átlagos nettó hangulatindex (pozitív - negatív)")
    ax4.set_ylabel("Hangulat pontszám")
    ax4.tick_params(axis="x", rotation=25)
    for b in bars4:
        h = b.get_height()
        va = "bottom" if h >= 0 else "top"
        ax4.text(b.get_x() + b.get_width()/2, h + (0.05 if h >= 0 else -0.15), f"{h:.2f}", ha="center", va=va, fontsize=9)

    plt.tight_layout()
    plot_path = Path("corpus_expanded_analysis.png")
    plt.savefig(plot_path, dpi=200)
    plt.close()

    return summary, top_kws_by_site, plot_path


if __name__ == "__main__":
    print("[+] Kibővített korpusz beolvasása az adatbázisból...")
    df = load_corpus_data()
    print(f"    - Betöltve: {len(df)} feldolgozott cikk")
    df_res, portal_kw = analyze_article_corpus(df)
    summary, top_kws, plot_path = generate_summary_and_plot(df_res, portal_kw)

    print("\n" + "=" * 80)
    print("KIBŐVÍTETT KORPUSZ ÖSSZEFOGLALÓ TÁBLÁZAT")
    print("=" * 80)
    print(summary.to_string(index=False))

    print("\n" + "=" * 80)
    print("TOP KULCSSZAVAK PORTÁLONKÉNT")
    print("=" * 80)
    for site, kws in top_kws.items():
        print(f"  {site:<15}: {', '.join(kws)}")
    print(f"\n[✓] Mentett összehasonlító diagram: {plot_path.resolve()}")
