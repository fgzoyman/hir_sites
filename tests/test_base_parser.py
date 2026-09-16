import pytest
from bs4 import BeautifulSoup

from parsers.base_parser import (
    BaseArticleParser,
    clean_text,
    normalize_url,
)


class DummyParser(BaseArticleParser):
    site_name = "Dummy"
    default_base_url = "https://example.com"

    def parse(self):
        return []


class TestCleanText:
    def test_clean_text_none_and_empty(self):
        assert clean_text(None) == ""
        assert clean_text("") == ""
        assert clean_text("   ") == ""

    def test_clean_text_removes_newlines_and_tabs(self):
        raw = "\t\n  Hírek a\n\r  világból   \t"
        assert clean_text(raw) == "Hírek a világból"

    def test_clean_text_collapses_multiple_spaces(self):
        raw = "Fontos    hír     jelent     meg."
        assert clean_text(raw) == "Fontos hír jelent meg."


class TestNormalizeUrl:
    def test_empty_url(self):
        assert normalize_url("") == ""
        assert normalize_url(None) == ""

    def test_relative_url_with_base(self):
        base = "https://www.origo.hu"
        assert (
            normalize_url("/itthon/2026/09/cikk", base)
            == "https://www.origo.hu/itthon/2026/09/cikk"
        )

    def test_trailing_slash_removal(self):
        base = "https://24.hu"
        assert (
            normalize_url("https://24.hu/belfold/2026/09/08/hir/", base)
            == "https://24.hu/belfold/2026/09/08/hir"
        )

    def test_strips_fragments(self):
        url = "https://nepszava.hu/3332383_cikk#comments"
        assert normalize_url(url) == "https://nepszava.hu/3332383_cikk"

    def test_adds_protocol_to_protocol_relative_url(self):
        url = "//cdn.example.com/images/pic.jpg"
        assert normalize_url(url) == "https://cdn.example.com/images/pic.jpg"


class TestBaseArticleParserHelpers:
    @pytest.fixture
    def dummy_parser(self):
        soup = BeautifulSoup("<html><body></body></html>", "html.parser")
        return DummyParser(soup=soup, source_file="dummy.html")

    def test_is_ad_detection(self, dummy_parser):
        html = """
        <div>
            <div class="native-ad-wrapper">
                <article class="ad-card">
                    <a href="https://example.com/ad-cikk" class="banner-link">Reklám</a>
                </article>
            </div>
            <article class="normal-card">
                <a href="https://example.com/cikk">Valódi hír</a>
            </article>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        ad_tag = soup.select_one(".ad-card")
        ad_link = soup.select_one(".banner-link")
        normal_card = soup.select_one(".normal-card")

        assert dummy_parser.is_ad(ad_tag) is True
        assert dummy_parser.is_ad(ad_link) is True
        assert dummy_parser.is_ad(normal_card) is False

    def test_is_valid_article_url_filters_system_paths(self, dummy_parser):
        assert dummy_parser.is_valid_article_url("https://example.com/adatvedelem") is False
        assert dummy_parser.is_valid_article_url("https://example.com/impresszum") is False
        assert dummy_parser.is_valid_article_url("javascript:void(0)") is False
        assert dummy_parser.is_valid_article_url("mailto:info@example.com") is False
        assert dummy_parser.is_valid_article_url("#top") is False
        assert dummy_parser.is_valid_article_url("https://example.com/belfold/2026/09/08/hir") is True

    def test_extract_media_video_and_image(self, dummy_parser):
        video_html = '<div class="card"><iframe src="https://video.example.com/embed/123"></iframe></div>'
        soup_v = BeautifulSoup(video_html, "html.parser")
        m_type, m_url, m_alt = dummy_parser.extract_media(soup_v.select_one(".card"))
        assert m_type == "video"
        assert m_url == "https://video.example.com/embed/123"

        img_html = '<div class="card"><img src="https://cdn.example.com/pic.jpg" alt="Hír fotó"/></div>'
        soup_img = BeautifulSoup(img_html, "html.parser")
        m_type, m_url, m_alt = dummy_parser.extract_media(soup_img.select_one(".card"))
        assert m_type == "image"
        assert m_url == "https://cdn.example.com/pic.jpg"
        assert m_alt == "Hír fotó"

    def test_build_record_structure(self, dummy_parser):
        rec = dummy_parser.build_record(
            order=1,
            link="https://example.com/cikk-1",
            title="  Teszt   hír címe  \n",
            authors=[" Teszt Szerző "],
            section=" Belföld ",
            tags=[" Élő "],
            lead=" Ez a cikk leadje. ",
            media_type="image",
            media_url="https://example.com/img.jpg",
            media_alt=" Kép leírása ",
        )
        assert rec["site"] == "Dummy"
        assert rec["order"] == 1
        assert rec["link"] == "https://example.com/cikk-1"
        assert rec["title"] == "Teszt hír címe"
        assert rec["section"] == "Belföld"
        assert rec["lead"] == "Ez a cikk leadje."
        assert rec["media_type"] == "image"
        assert rec["media_url"] == "https://example.com/img.jpg"
        assert rec["media_alt"] == "Kép leírása"
        assert rec["source_file"] == "dummy.html"
