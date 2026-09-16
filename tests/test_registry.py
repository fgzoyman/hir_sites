from bs4 import BeautifulSoup

from parsers import (
    PARSER_REGISTRY,
    detect_site_key,
    get_parser,
)
from parsers.blikk_parser import BlikkParser
from parsers.huszonnegy_parser import HuszonnegyParser
from parsers.nepszava_parser import NepszavaParser
from parsers.origo_parser import OrigoParser
from parsers.portfolio_parser import PortfolioParser
from parsers.vadhajtasok_parser import VadhajtasokParser


class TestRegistrySiteDetection:
    def test_detect_by_filename(self):
        test_cases = [
            ("1_Origo_2026-09-08_10-18-36.html", "origo"),
            ("scraped_data/2_Nepszava_2026-09-08_10-18-36.html", "nepszava"),
            ("3_Huszonnegy_2026-09-08_10-18-36.html", "huszonnegy"),
            ("4_Blikk_2026-09-08_10-18-36.html", "blikk"),
            ("5_Portfolio_2026-09-08_10-18-36.html", "portfolio"),
            ("6_Vadhajtasok_2026-09-08_10-18-36.html", "vadhajtasok"),
        ]
        for filename, expected_key in test_cases:
            assert detect_site_key(filename) == expected_key

    def test_detect_by_meta_og_site_name(self):
        html = '<meta property="og:site_name" content="Portfolio.hu">'
        soup = BeautifulSoup(html, "html.parser")
        assert detect_site_key("sample.html", soup=soup) == "portfolio"

    def test_detect_by_canonical_url(self):
        html = '<link rel="canonical" href="https://www.blikk.hu/">'
        soup = BeautifulSoup(html, "html.parser")
        assert detect_site_key("sample.html", soup=soup) == "blikk"

    def test_detect_unknown_returns_none(self):
        soup = BeautifulSoup("<html><head></head><body>Ismeretlen lap</body></html>", "html.parser")
        assert detect_site_key("random_file.html", soup=soup) is None


class TestRegistryGetParser:
    def test_get_parser_instantiates_correct_classes(self):
        soup = BeautifulSoup("<html></html>", "html.parser")

        mapping = {
            "origo": OrigoParser,
            "nepszava": NepszavaParser,
            "huszonnegy": HuszonnegyParser,
            "blikk": BlikkParser,
            "portfolio": PortfolioParser,
            "vadhajtasok": VadhajtasokParser,
        }

        for key, expected_cls in mapping.items():
            parser = get_parser(key, soup=soup, source_file=f"{key}.html")
            assert isinstance(parser, expected_cls)
            assert parser.source_file == f"{key}.html"

    def test_get_parser_unknown_returns_none(self):
        soup = BeautifulSoup("<html></html>", "html.parser")
        assert get_parser("nemletezo_portal", soup=soup) is None

    def test_parser_registry_contains_six_sites(self):
        expected_keys = {"origo", "nepszava", "huszonnegy", "blikk", "portfolio", "vadhajtasok"}
        assert set(PARSER_REGISTRY.keys()) == expected_keys
