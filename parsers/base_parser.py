import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup, Tag


# Általános reklám- és hirdetésminták
COMMON_AD_PATTERNS = [
    r"advert",
    r"banner",
    r"sponsor",
    r"promot",
    r"native-?ad",
    r"gemius",
    r"google-?ad",
    r"dfp",
    r"outbrain",
    r"taboola",
    r"hirdetes",
    r"pr-cikk",
    r"reklam",
    r"ad-box",
    r"ad-slot",
    r"ad-wrapper",
    r"commercial",
]
AD_REGEX = re.compile("|".join(COMMON_AD_PATTERNS), re.IGNORECASE)

COMMON_IGNORED_PATHS = [
    r"^javascript:",
    r"^mailto:",
    r"^tel:",
    r"^#",
    r"/adatvedel",
    r"/impresszum",
    r"/aszf",
    r"/privacy",
    r"/terms",
    r"/cookie",
    r"/login",
    r"/regisztrac",
    r"/elofizet",
    r"/hirlevel",
    r"/szerzoi-jogi",
    r"/rolunk",
    r"/kuldetes",
]
IGNORED_PATH_REGEX = re.compile("|".join(COMMON_IGNORED_PATHS), re.IGNORECASE)


def clean_text(text: Optional[str]) -> str:
    """Többszörös szóközök, sortörések és felesleges karakterek eltávolítása."""
    if not text:
        return ""
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_url(url: str, base_url: str = "") -> str:
    """URL abszolutizálása és tisztítása (tracking query paraméterek eltávolítása)."""
    if not url:
        return ""
    if url.startswith("//"):
        url = f"https:{url}"
    elif base_url:
        url = urljoin(base_url, url)
    # Töröljük a #-et és az általános utm_ paramétereket
    parsed = urlparse(url)
    clean_path = parsed.path
    # Ha a protokoll hiányzik:
    if not parsed.scheme and parsed.netloc:
        url = f"https://{parsed.netloc}{clean_path}"
        parsed = urlparse(url)
    elif not parsed.scheme and not parsed.netloc:
        return url
    return f"{parsed.scheme}://{parsed.netloc}{clean_path}".rstrip("/")


class BaseArticleParser(ABC):
    """Közös alaposztály az oldalspecifikus parserekhez."""

    site_name: str = "Generic"
    default_base_url: str = ""

    def __init__(self, soup: BeautifulSoup, source_file: str = ""):
        self.soup = soup
        self.source_file = source_file
        self.seen_links: set[str] = set()

    def is_ad(self, tag: Tag) -> bool:
        """Megvizsgálja, hogy a tag vagy közvetlen szülei hirdetésnek minősülnek-e."""
        current = tag
        steps = 0
        while current and steps < 4:
            classes = " ".join(current.get("class", [])) if current.get("class") else ""
            elem_id = current.get("id", "")
            role = current.get("role", "")
            aria_label = current.get("aria-label", "")
            test_str = f"{classes} {elem_id} {role} {aria_label}"
            if AD_REGEX.search(test_str):
                return True
            current = current.parent
            steps += 1
        return False

    def is_valid_article_url(self, url: str) -> bool:
        """Alapértelmezett URL szűrés: nem horgony, nem jogi/menü oldal."""
        if not url:
            return False
        if IGNORED_PATH_REGEX.search(url):
            return False
        return True

    def extract_media(self, container: Tag) -> tuple[str, str, str]:
        """Kép vagy videó kinyerése a kártyából: (media_type, media_url, media_alt)."""
        # 1. Videó keresése
        video = container.find(["video", "iframe"])
        if video:
            src = video.get("src") or video.get("data-src") or ""
            if src:
                return "video", src, ""

        # 2. Kép keresése
        img = container.find("img")
        if img:
            src = (
                img.get("src")
                or img.get("data-src")
                or img.get("data-lazy-src")
                or img.get("data-original")
                or ""
            )
            # Ha srcset van és nincs src
            if not src and img.get("srcset"):
                srcset = img.get("srcset", "").split(",")
                if srcset:
                    src = srcset[-1].strip().split(" ")[0]
            if src and not src.startswith("data:image"):
                alt = clean_text(img.get("alt", ""))
                return "image", src, alt

        return "none", "", ""

    def build_record(
        self,
        order: int,
        link: str,
        title: str,
        authors: Optional[List[str]] = None,
        section: str = "",
        tags: Optional[List[str]] = None,
        lead: str = "",
        media_type: str = "none",
        media_url: str = "",
        media_alt: str = "",
    ) -> Dict[str, Any]:
        """Egységes rekordstruktúra előállítása."""
        return {
            "site": self.site_name,
            "order": order,
            "link": link,
            "title": clean_text(title),
            "authors": authors or [],
            "section": clean_text(section),
            "tags": tags or [],
            "lead": clean_text(lead),
            "source_file": self.source_file,
            "media_type": media_type,
            "media_url": media_url,
            "media_alt": clean_text(media_alt),
        }

    @abstractmethod
    def parse(self) -> List[Dict[str, Any]]:
        """Az oldal specifikus parse logikája."""
        pass
