from pathlib import Path

import pytest

from parse_scraped import process_html_file


SCRAPED_DATA_DIR = Path(__file__).parent.parent / "scraped_data"


def get_real_html_files():
    if not SCRAPED_DATA_DIR.exists():
        return []
    return sorted(
        [
            f
            for f in SCRAPED_DATA_DIR.glob("*.html")
            if not f.name.endswith("_articles.html") and not f.name.startswith("tmp")
        ]
    )


class TestIntegrationScrapedFiles:
    html_files = get_real_html_files()

    @pytest.mark.skipif(len(html_files) == 0, reason="Nincsenek mentett HTML minták")
    def test_found_six_sample_files(self):
        assert len(self.html_files) >= 6

    @pytest.mark.parametrize("html_file", html_files, ids=lambda f: f.name)
    def test_process_real_html_file(self, html_file: Path):
        site_key, records = process_html_file(html_file)

        assert site_key is not None
        assert site_key in ["origo", "nepszava", "huszonnegy", "blikk", "portfolio", "vadhajtasok"]
        assert len(records) > 0, f"A(z) {html_file.name} fájlból nem sikerült cikket kinyerni!"

        seen_links = set()
        expected_orders = list(range(1, len(records) + 1))
        actual_orders = [r["order"] for r in records]

        assert actual_orders == expected_orders, "Az 'order' nem 1-től növekvő sorrendben fut!"

        for r in records:
            assert r["site"]
            assert r["source_file"] == html_file.name
            assert r["title"] and len(r["title"]) >= 3
            assert r["link"].startswith("http://") or r["link"].startswith("https://")
            assert "/cimke/" not in r["link"], f"Címke oldal került a cikkek közé: {r['link']}"
            assert r["media_type"] in ["image", "video", "none"]
            assert isinstance(r["authors"], list)
            assert isinstance(r["tags"], list)

            assert r["link"] not in seen_links, f"Duplikált link található: {r['link']}"
            seen_links.add(r["link"])
