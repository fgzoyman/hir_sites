import re
from typing import Any, Dict, List
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag
from parsers.base_parser import BaseArticleParser, clean_text, normalize_url


class VadhajtasokParser(BaseArticleParser):
    site_name = "Vadhajtasok"
    default_base_url = "https://www.vadhajtasok.hu"

    def is_valid_article_url(self, url: str) -> bool:
        if not super().is_valid_article_url(url):
            return False
        parsed = urlparse(url)
        path = parsed.path

        # Kizárandó címke, szerző, keresés oldalak
        if any(p in path for p in ["/cimke/", "/szerzo/", "/tag/", "/kategoria/"]):
            return False

        # Vadhajtások valódi cikkek URL-je dátumalapú: /YYYY/MM/DD/slug
        if re.search(r"/\d{4}/\d{2}/\d{2}/[a-z0-9\-]+", path):
            return True

        return False

    def parse(self) -> List[Dict[str, Any]]:
        articles: List[Dict[str, Any]] = []
        cards = self.soup.find_all("article")
        order = 1

        for card in cards:
            if self.is_ad(card):
                continue

            # Dátumalapú cikk-link keresése
            article_link = ""
            for a in card.find_all("a", href=True):
                href = a["href"]
                clean = normalize_url(href, self.default_base_url)
                if self.is_valid_article_url(clean):
                    article_link = clean
                    break

            if not article_link:
                continue

            if article_link in self.seen_links:
                continue

            # Cím meghatározása
            heading = card.find(["h1", "h2", "h3", "h4", "h5"])
            title = ""
            if heading:
                title = clean_text(heading.get_text())
            else:
                title_link = card.find("a", href=True)
                if title_link:
                    title = clean_text(title_link.get_text())

            if not title or len(title) < 5 or title.startswith("#"):
                continue

            # Lead keresése
            lead_el = card.select_one(".post-excerpt, p")
            lead = ""
            if lead_el:
                l_text = clean_text(lead_el.get_text())
                if l_text and l_text != title and len(l_text) > 10:
                    lead = l_text

            # Média keresése
            media_type, media_url, media_alt = self.extract_media(card)
            # Ha a címben vagy kártyán van videó utalás
            if "video" in title.lower() or card.find(class_=re.compile(r"video", re.I)):
                if media_type == "none":
                    media_type = "video"

            # Szerző / rovat
            section = ""
            author_el = card.find(class_=re.compile(r"author", re.I))
            authors = []
            if author_el:
                a_name = clean_text(author_el.get_text())
                if a_name and len(a_name) < 30:
                    authors.append(a_name)

            self.seen_links.add(article_link)
            articles.append(
                self.build_record(
                    order=order,
                    link=article_link,
                    title=title,
                    authors=authors,
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
