import re
from typing import Any, Dict, List
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag
from parsers.base_parser import BaseArticleParser, clean_text, normalize_url


class NepszavaParser(BaseArticleParser):
    site_name = "Nepszava"
    default_base_url = "https://nepszava.hu"

    def is_valid_article_url(self, url: str) -> bool:
        if not super().is_valid_article_url(url):
            return False
        # Népszava cikk URL-ek: 7 számjegy és aláhúzásjel van a slug előtt
        # pl: https://nepszava.hu/3332383_sopron-legszennyezettsege-a-legalacsonyabb-hazankban
        parsed = urlparse(url)
        path = parsed.path
        if re.search(r"/\d{7}_[a-z0-9\-]+", path):
            return True
        return False

    def parse(self) -> List[Dict[str, Any]]:
        articles: List[Dict[str, Any]] = []
        order = 1

        # Cikk-linkek keresése
        link_elements = self.soup.find_all("a", href=True)

        for link_el in link_elements:
            raw_url = link_el["href"]
            clean_url = normalize_url(raw_url, self.default_base_url)

            if not self.is_valid_article_url(clean_url):
                continue

            if clean_url in self.seen_links:
                continue

            # Megkeressük a cikk legszűkebb értelmes konténerét
            # Ha a link maga tartalmaz címet és képet, vagy a szülő divje
            container = link_el
            parent = link_el.parent
            if parent and parent.name in ["div", "li", "section"]:
                # Ha a szülő csak ezt a cikket tartalmazza, használhatjuk
                other_article_links = [
                    a for a in parent.find_all("a", href=True)
                    if self.is_valid_article_url(normalize_url(a["href"], self.default_base_url))
                ]
                if len(other_article_links) == 1:
                    container = parent

            if self.is_ad(container):
                continue

            # Cím kinyerése
            title_el = (
                container.find(attrs={"itemprop": "headline"})
                or container.find(["h1", "h2", "h3", "h4", "h5", "h6"])
            )
            if title_el:
                title = clean_text(title_el.get_text())
            else:
                title = clean_text(link_el.get_text())

            if not title or len(title) < 5:
                continue

            # Lead kinyerése
            lead = ""
            lead_el = container.find(attrs={"itemprop": "abstract"})
            if not lead_el:
                # Keresünk p taget, ami nem a cím része
                for p in container.find_all("p"):
                    p_text = clean_text(p.get_text())
                    if p_text and p_text != title and len(p_text) > 15:
                        lead = p_text
                        break
            else:
                lead = clean_text(lead_el.get_text())

            # Média kinyerése
            media_type, media_url, media_alt = self.extract_media(container)

            # Szerző kinyerése (véleményeknél gyakori)
            authors = []
            author_el = container.find(class_=re.compile(r"author--link|author", re.I))
            if author_el:
                author_name = clean_text(author_el.get_text())
                if author_name and len(author_name) < 40 and author_name != title:
                    authors.append(author_name)

            # Rovat / címkék kinyerése
            section = ""
            tags = []
            tag_links = container.find_all("a", href=re.compile(r"/tag/|/cimke/|/rovat/"))
            for t in tag_links:
                t_txt = clean_text(t.get_text())
                if t_txt and t_txt not in tags and t_txt != title:
                    tags.append(t_txt)

            self.seen_links.add(clean_url)
            articles.append(
                self.build_record(
                    order=order,
                    link=clean_url,
                    title=title,
                    authors=authors,
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
