import re
from typing import Any, Dict, List
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag
from parsers.base_parser import BaseArticleParser, clean_text, normalize_url


class OrigoParser(BaseArticleParser):
    site_name = "Origo"
    default_base_url = "https://www.origo.hu"

    def is_valid_article_url(self, url: str) -> bool:
        if not super().is_valid_article_url(url):
            return False
        parsed = urlparse(url)
        path = parsed.path.lower()

        # Kizárandó útvonalak
        if any(p in path for p in ["/cimke/", "/rovat/", "/szerzo/", "/kereses/", "/video/"]):
            # Megjegyzés: Ha maga a cikk a /video/ alatt van dátummal, az lehet cikk, de /cimke/ és /rovat/ nem
            if "/cimke/" in path or "/rovat/" in path or "/szerzo/" in path:
                return False

        # Origo cikkek tipikusan: /[rovat]/YYYY/MM/... vagy /[rovat]/[alrovat]/YYYY/MM/...
        # vagy legalább egy cikk slug
        if not re.search(r"/\d{4}/\d{2}/|[a-z0-9\-]{8,}$", path):
            return False

        return True

    def extract_section_from_url(self, url: str) -> str:
        parsed = urlparse(url)
        parts = [p for p in parsed.path.split("/") if p]
        if parts:
            first = parts[0]
            if not re.match(r"^\d{4}$", first):
                return first
        return ""

    def parse(self) -> List[Dict[str, Any]]:
        articles: List[Dict[str, Any]] = []
        cards = self.soup.select("article.article-card")
        order = 1

        for card in cards:
            if self.is_ad(card):
                continue

            # Link és Cím keresése
            title_el = card.select_one(".article-card-title, h1, h2, h3, h4")
            link_el = card.select_one("a.article-card-thumbnail, a.article-card-link") or card.find("a", href=True)

            if not link_el or not link_el.get("href"):
                continue

            raw_url = link_el["href"]
            clean_url = normalize_url(raw_url, self.default_base_url)

            if not self.is_valid_article_url(clean_url):
                continue

            if clean_url in self.seen_links:
                continue

            title = ""
            if title_el:
                title = clean_text(title_el.get_text())
            elif link_el:
                title = clean_text(link_el.get_text())

            if not title or len(title) < 5:
                continue

            # Lead
            lead_el = card.select_one(".article-card-lead, p")
            lead = clean_text(lead_el.get_text()) if lead_el else ""

            # Média
            has_video = bool(card.select_one(".icon-video, .article-icons-video, [class*='video']"))
            media_type, media_url, media_alt = self.extract_media(card)
            if has_video:
                media_type = "video"

            # Rovat
            section_el = card.select_one(".article-card-tag, .tag, .section")
            section = clean_text(section_el.get_text()) if section_el else ""
            if not section:
                section = self.extract_section_from_url(clean_url)

            self.seen_links.add(clean_url)
            articles.append(
                self.build_record(
                    order=order,
                    link=clean_url,
                    title=title,
                    authors=[],
                    section=section,
                    tags=[],
                    lead=lead,
                    media_type=media_type,
                    media_url=media_url,
                    media_alt=media_alt,
                )
            )
            order += 1

        return articles
