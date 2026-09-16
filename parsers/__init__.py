import re
from pathlib import Path
from typing import Dict, Optional, Type
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from parsers.base_parser import BaseArticleParser
from parsers.origo_parser import OrigoParser
from parsers.nepszava_parser import NepszavaParser
from parsers.huszonnegy_parser import HuszonnegyParser
from parsers.blikk_parser import BlikkParser
from parsers.portfolio_parser import PortfolioParser
from parsers.vadhajtasok_parser import VadhajtasokParser

PARSER_REGISTRY: Dict[str, Type[BaseArticleParser]] = {
    "origo": OrigoParser,
    "nepszava": NepszavaParser,
    "huszonnegy": HuszonnegyParser,
    "blikk": BlikkParser,
    "portfolio": PortfolioParser,
    "vadhajtasok": VadhajtasokParser,
}

FILENAME_MAP = {
    "1_origo": "origo",
    "origo": "origo",
    "2_nepszava": "nepszava",
    "nepszava": "nepszava",
    "3_huszonnegy": "huszonnegy",
    "huszonnegy": "huszonnegy",
    "24": "huszonnegy",
    "24hu": "huszonnegy",
    "4_blikk": "blikk",
    "blikk": "blikk",
    "5_portfolio": "portfolio",
    "portfolio": "portfolio",
    "6_vadhajtasok": "vadhajtasok",
    "vadhajtasok": "vadhajtasok",
}


def detect_site_key(filename_or_path: str, soup: Optional[BeautifulSoup] = None) -> Optional[str]:
    """Meghatározza a weboldal kulcsát fájlnév vagy HTML metaadat alapján."""
    name = Path(filename_or_path).stem.lower()

    for pattern, key in FILENAME_MAP.items():
        if pattern in name:
            return key

    if soup:
        # Próbáljuk og:site_name vagy canonical alapján
        meta_site = soup.find("meta", property="og:site_name")
        if meta_site and meta_site.get("content"):
            site_val = meta_site["content"].lower()
            for pattern, key in FILENAME_MAP.items():
                if pattern in site_val:
                    return key

        canonical = soup.find("link", rel="canonical")
        if canonical and canonical.get("href"):
            netloc = urlparse(canonical["href"]).netloc.lower()
            for pattern, key in FILENAME_MAP.items():
                if pattern in netloc:
                    return key

    return None


def get_parser(
    site_key: str, soup: BeautifulSoup, source_file: str = ""
) -> Optional[BaseArticleParser]:
    """Példányosítja a megfelelő parser osztályt a megadott oldal kulcshoz."""
    parser_cls = PARSER_REGISTRY.get(site_key.lower())
    if parser_cls:
        return parser_cls(soup=soup, source_file=source_file)
    return None
