import re
from typing import Any, Dict, List
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag
from parsers.base_parser import BaseArticleParser, clean_text, normalize_url


class HuszonnegyParser(BaseArticleParser):
    site_name = "24.hu"
    default_base_url = "https://24.hu"

    def is_valid_article_url(self, url: str) -> bool:
        if not super().is_valid_article_url(url):
            return False
        parsed = urlparse(url)
        path = parsed.path

        # Kizárandó útvonalak
        if any(p in path for p in ["/tag/", "/cimke/", "/rovat/", "/szerzo/", "/hirlevel/"]):
            return False

        # 24.hu cikkek URL-je tipikusan: /[rovat]/YYYY/MM/DD/[slug]/ vagy /[rovat]/[alrovat]/YYYY/MM/DD/[slug]/
        if re.search(r"/\d{4}/\d{2}/\d{2}/", path):
            return True

        return False

    def extract_section_from_url(self, url: str) -> str:
        parsed = urlparse(url)
        parts = [p for p in parsed.path.split("/") if p]
        # Ha fn/gazdasag, akkor "gazdasag" vagy "fn/gazdasag"
        if parts:
            if parts[0] == "fn" and len(parts) > 1 and not re.match(r"^\d{4}$", parts[1]):
                return parts[1]
            if not re.match(r"^\d{4}$", parts[0]):
                return parts[0]
        return ""

    def parse(self) -> List[Dict[str, Any]]:
        articles: List[Dict[str, Any]] = []
        containers = self.soup.find_all("article")
        order = 1

        for card in containers:
            if self.is_ad(card):
                continue

            # Link és cím keresése
            link_el = card.select_one(".m-articleWidget__title a, a.m-articleWidget__link, h2 a, h3 a")
            if not link_el:
                link_el = card.find("a", href=True)

            if not link_el or not link_el.get("href"):
                continue

            raw_url = link_el["href"]
            clean_url = normalize_url(raw_url, self.default_base_url)

            if not self.is_valid_article_url(clean_url):
                continue

            if clean_url in self.seen_links:
                continue

            title = clean_text(link_el.get_text())
            if not title:
                title_tag = card.find(["h1", "h2", "h3", "h4"])
                if title_tag:
                    title = clean_text(title_tag.get_text())

            if not title or len(title) < 5:
                continue

            # Lead keresése
            lead = ""
            lead_el = card.select_one(".m-articleWidget__lead, .m-articleWidget__content p, p")
            if lead_el:
                l_text = clean_text(lead_el.get_text())
                if l_text and l_text != title and len(l_text) > 10:
                    lead = l_text

            # Média keresése
            media_type, media_url, media_alt = self.extract_media(card)

            # Címkék (pl. Élő, Vélemény)
            tags = []
            tag_el = card.select_one(".a-tag, .m-articleWidget__category")
            if tag_el:
                t_txt = clean_text(tag_el.get_text())
                if t_txt and t_txt != title:
                    tags.append(t_txt)

            # Rovat
            section = self.extract_section_from_url(clean_url)

            self.seen_links.add(clean_url)
            articles.append(
                self.build_record(
                    order=order,
                    link=clean_url,
                    title=title,
                    authors=[],
                    section=section,
                    tags=tags,
                    lead=lead,
                    media_type=media_type,
                    media_url=media_url,
                    media_alt=media_alt,
                )
            )
            order += 1

        return articles
