import re
from typing import Any, Dict, List
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag
from parsers.base_parser import BaseArticleParser, clean_text, normalize_url


class PortfolioParser(BaseArticleParser):
    site_name = "Portfolio"
    default_base_url = "https://www.portfolio.hu"

    def is_valid_article_url(self, url: str) -> bool:
        if not super().is_valid_article_url(url):
            return False
        parsed = urlparse(url)
        path = parsed.path

        # Kizárandó útvonalak
        if any(p in path for p in ["/rovat/", "/portfolio-signature", "/impresszum", "/adatvedelem", "/szerzo/"]):
            return False

        # Valódi cikk URL-ek: Portfolio, Pénzcentrum, Agrárszektor cikkekben van cikk-azonosító vagy dátum
        # pl. -\d{5,}$ vagy /\d{8}/ vagy /podcast/[slug]
        if re.search(r"-\d{5,}$|/\d{8}/|/podcast/[a-z0-9\-]+|/prof/[a-z0-9\-]+", path):
            return True

        return False

    def extract_section(self, container: Tag, url: str) -> str:
        # Ha a kártyán van kategória / rovat jelölés
        sec_el = container.find(class_=re.compile(r"tag|section|rubric|category", re.I))
        if sec_el:
            sec_text = clean_text(sec_el.get_text())
            if sec_text and len(sec_text) < 30:
                return sec_text

        # Egyébként URL-ből
        parsed = urlparse(url)
        parts = [p for p in parsed.path.split("/") if p]
        if parts and not re.match(r"^\d+$", parts[0]):
            return parts[0]
        return ""

    def parse(self) -> List[Dict[str, Any]]:
        articles: List[Dict[str, Any]] = []
        cards = self.soup.find_all("article")
        order = 1

        for card in cards:
            if self.is_ad(card):
                continue

            # Menü és fejléc kártyák kiszűrése
            card_classes = card.get("class", [])
            if any("menu" in c.lower() for c in card_classes):
                continue

            # Cikk linkjének megkeresése
            article_link = ""
            heading = card.find(["h1", "h2", "h3", "h4", "h5"])
            if heading and heading.find("a", href=True):
                article_link = heading.find("a")["href"]
            else:
                for a in card.find_all("a", href=True):
                    href = a["href"]
                    if self.is_valid_article_url(normalize_url(href, self.default_base_url)):
                        article_link = href
                        break

            if not article_link:
                continue

            clean_url = normalize_url(article_link, self.default_base_url)
            if not self.is_valid_article_url(clean_url):
                continue

            if clean_url in self.seen_links:
                continue

            # Cím meghatározása
            title = ""
            if heading:
                title = clean_text(heading.get_text())
            else:
                title_link = card.find("a", href=True)
                if title_link:
                    title = clean_text(title_link.get_text())

            if not title or len(title) < 5:
                continue

            # Lead keresése
            lead = ""
            lead_el = card.find("p")
            if lead_el:
                l_text = clean_text(lead_el.get_text())
                if l_text and l_text != title and len(l_text) > 10:
                    lead = l_text

            # Média keresése
            media_type, media_url, media_alt = self.extract_media(card)

            # Rovat keresése
            section = self.extract_section(card, clean_url)

            # Külső partner jelzése a rovatban, ha nem portfolio.hu
            domain = urlparse(clean_url).netloc.lower()
            if "penzcentrum" in domain:
                section = f"Pénzcentrum: {section}" if section else "Pénzcentrum"
            elif "agrarszektor" in domain:
                section = f"Agrárszektor: {section}" if section else "Agrárszektor"

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
