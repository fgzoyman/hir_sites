import re
from typing import Any, Dict, List
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag
from parsers.base_parser import BaseArticleParser, clean_text, normalize_url


class BlikkParser(BaseArticleParser):
    site_name = "Blikk"
    default_base_url = "https://www.blikk.hu"

    def is_valid_article_url(self, url: str) -> bool:
        if not super().is_valid_article_url(url):
            return False
        parsed = urlparse(url)
        path = parsed.path.rstrip("/")
        parts = [p for p in path.split("/") if p]

        # Kizárandó szavak
        blacklisted = [
            "foto-bekuldes",
            "impresszum",
            "szerzoi-jogi",
            "rolunk",
            "kuldetes",
            "katalogus",
            "profile",
            "galeria",
            "video",
        ]
        if any(b in path.lower() for b in blacklisted):
            # Ha a galeria/video után van konkrét slug és hash cikk kód, az lehet cikk
            if path.lower().startswith("/galeria/") or path.lower().startswith("/video/"):
                pass
            else:
                return False

        # Blikk cikk: legalább 3 útvonal-elem a domain után, és a végén egy 7 karakteres hash áll
        # pl. /aktualis/belfold/slug/thv6m26
        if len(parts) >= 3 and re.match(r"^[a-z0-9]{7}$", parts[-1]):
            return True

        return False

    def extract_section_from_url(self, url: str) -> str:
        parsed = urlparse(url)
        parts = [p for p in parsed.path.split("/") if p]
        if parts and len(parts) >= 2:
            return f"{parts[0]}/{parts[1]}"
        elif parts:
            return parts[0]
        return ""

    def parse(self) -> List[Dict[str, Any]]:
        articles: List[Dict[str, Any]] = []
        order = 1

        links = self.soup.find_all("a", href=True)

        for link_el in links:
            raw_url = link_el["href"]
            clean_url = normalize_url(raw_url, self.default_base_url)

            if not self.is_valid_article_url(clean_url):
                continue

            if clean_url in self.seen_links:
                continue

            # Konténer meghatározása: ha van közvetlen kártya-szülő div
            container = link_el
            parent = link_el.parent
            if parent and parent.name in ["div", "article", "li"]:
                container = parent

            if self.is_ad(container):
                continue

            # Cím kinyerése
            # Kifejezett cím-tageket preferálunk a leíró szövegek (pl. lead/p) előtt
            heading_tags = link_el.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
            title = ""
            for h in heading_tags:
                t = clean_text(h.get_text())
                if t and (not title or len(t) > len(title)):
                    title = t

            if not title:
                other_tags = link_el.find_all(["span", "p"])
                for el in other_tags:
                    t = clean_text(el.get_text())
                    if t and (not title or len(t) > len(title)):
                        title = t

            if not title:
                title = clean_text(link_el.get_text())

            # Ha a cím ÉLŐ-vel vagy hasonlóval kezdődik, megtisztítjuk
            title = re.sub(r"^ÉLŐ", "Élő: ", title).strip()

            if not title or len(title) < 5:
                continue

            # Lead keresése
            lead = ""
            if container != link_el:
                for p in container.find_all("p"):
                    p_text = clean_text(p.get_text())
                    if p_text and p_text != title and len(p_text) > 15:
                        lead = p_text
                        break

            # Média keresése
            media_type, media_url, media_alt = self.extract_media(container)
            if media_type == "none":
                media_type, media_url, media_alt = self.extract_media(link_el)

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
