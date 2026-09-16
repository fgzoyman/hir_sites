from bs4 import BeautifulSoup

from parsers.blikk_parser import BlikkParser
from parsers.huszonnegy_parser import HuszonnegyParser
from parsers.nepszava_parser import NepszavaParser
from parsers.origo_parser import OrigoParser
from parsers.portfolio_parser import PortfolioParser
from parsers.vadhajtasok_parser import VadhajtasokParser


class TestOrigoParser:
    def test_parse_article_card_and_video(self):
        html = """
        <div class="articles-container">
            <article class="article-card">
                <a class="article-card-thumbnail" href="https://www.origo.hu/itthon/2026/09/fontos-origo-hirek-magyarorszagon">
                    <img src="https://kep.origo.hu/test.jpg" alt="Teszt kép" />
                    <span class="icon-video"></span>
                </a>
                <h2 class="article-card-title">Fontos origo hírek Magyarországon</h2>
                <p class="article-card-lead">Rövid bevezető szöveg az eseményekről.</p>
                <span class="article-card-tag">Belföld</span>
            </article>
            <article class="article-card">
                <a href="https://www.origo.hu/cimke/politika">Politika címke oldal</a>
                <h3 class="article-card-title">Címke gyűjtőoldal</h3>
            </article>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        parser = OrigoParser(soup=soup, source_file="origo_test.html")
        articles = parser.parse()

        assert len(articles) == 1
        art = articles[0]
        assert art["site"] == "Origo"
        assert art["title"] == "Fontos origo hírek Magyarországon"
        assert art["link"] == "https://www.origo.hu/itthon/2026/09/fontos-origo-hirek-magyarorszagon"
        assert art["media_type"] == "video"
        assert art["section"] == "Belföld"
        assert art["lead"] == "Rövid bevezető szöveg az eseményekről."


class TestNepszavaParser:
    def test_parse_valid_nepszava_article_and_abstract(self):
        html = """
        <div class="topbox__block">
            <a href="https://nepszava.hu/3332383_sopron-legszennyezettsege-a-legalacsonyabb-hazankban">
                <h2 itemprop="headline">Sopron légszennyezettsége a legalacsonyabb hazánkban</h2>
            </a>
            <p itemprop="abstract">A legfrissebb adatok szerint jó a levegő a hűség városában.</p>
            <a href="https://nepszava.hu/tag/sopron">Sopron</a>
        </div>
        <div>
            <a href="https://nepszava.hu/rolunk">Rólunk</a>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        parser = NepszavaParser(soup=soup, source_file="nepszava_test.html")
        articles = parser.parse()

        assert len(articles) == 1
        art = articles[0]
        assert art["site"] == "Nepszava"
        assert art["title"] == "Sopron légszennyezettsége a legalacsonyabb hazánkban"
        assert "3332383_sopron" in art["link"]
        assert art["lead"] == "A legfrissebb adatok szerint jó a levegő a hűség városában."
        assert "Sopron" in art["tags"]


class TestHuszonnegyParser:
    def test_parse_article_widget_and_section_from_url(self):
        html = """
        <article class="m-articleWidget__wrap">
            <div class="m-articleWidget__linkImgWrap">
                <img src="https://24.hu/media/foto.jpg" alt="Kép illusztráció" />
            </div>
            <span class="a-tag">ÉLŐ</span>
            <div class="m-articleWidget__title">
                <a href="https://24.hu/belfold/2026/09/08/kormanyinfo-elo-kozvetites/">
                    Kormányinfó percről percre
                </a>
            </div>
            <div class="m-articleWidget__lead">
                Itt követheti a mai kormányinfó legfontosabb bejelentéseit.
            </div>
        </article>
        <article class="m-articleWidget__wrap">
            <a href="https://24.hu/cimke/orban-viktor/">Címke gyűjtő</a>
        </article>
        """
        soup = BeautifulSoup(html, "html.parser")
        parser = HuszonnegyParser(soup=soup, source_file="24_test.html")
        articles = parser.parse()

        assert len(articles) == 1
        art = articles[0]
        assert art["site"] == "24.hu"
        assert art["title"] == "Kormányinfó percről percre"
        assert art["section"] == "belfold"
        assert art["tags"] == ["ÉLŐ"]
        assert art["lead"] == "Itt követheti a mai kormányinfó legfontosabb bejelentéseit."
        assert art["media_type"] == "image"


class TestBlikkParser:
    def test_parse_valid_7_char_hash_url_and_filter_ignored(self):
        html = """
        <div class="news-list">
            <div class="blikk-card">
                <a href="https://www.blikk.hu/aktualis/belfold/oriasi-vihar-csapott-le-budapestre/thv6m26">
                    <img src="https://blikk.hu/media/vihar.jpg" alt="Vihar kép"/>
                    <h2>Óriási vihar csapott le Budapestre</h2>
                    <p>Fákat döntött ki a viharos erejű szél a fővárosban.</p>
                </a>
            </div>
            <div class="blikk-card">
                <a href="https://www.blikk.hu/foto-bekuldes">
                    <span>Küldjön be fotót!</span>
                </a>
            </div>
            <div class="blikk-card">
                <a href="https://www.blikk.hu/impresszum">
                    <span>Impresszum</span>
                </a>
            </div>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        parser = BlikkParser(soup=soup, source_file="blikk_test.html")
        articles = parser.parse()

        assert len(articles) == 1
        art = articles[0]
        assert art["site"] == "Blikk"
        assert art["title"] == "Óriási vihar csapott le Budapestre"
        assert art["link"].endswith("thv6m26")
        assert art["section"] == "aktualis/belfold"
        assert art["lead"] == "Fákat döntött ki a viharos erejű szél a fővárosban."


class TestPortfolioParser:
    def test_parse_articles_and_partner_brands(self):
        html = """
        <div class="content-wrapper">
            <article class="article-block">
                <h2><a href="https://www.portfolio.hu/gazdasag/20260908/megszolalt-a-jegybank-elnoke-709876">Megszólalt a jegybank elnöke</a></h2>
                <p>Fontos kamatdöntés előtt áll a piac.</p>
            </article>
            <article class="article-block">
                <h2><a href="https://www.penzcentrum.hu/megtakaritas/20260908/uj-allampapir-erkezik-1156789">Új állampapír érkezik a magyaroknak</a></h2>
                <p>Magas hozamot ígérnek a lakossági befektetőknek.</p>
            </article>
            <article class="menu-item">
                <a href="https://www.portfolio.hu/rovat/gazdasag">Gazdaság rovat</a>
            </article>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        parser = PortfolioParser(soup=soup, source_file="portfolio_test.html")
        articles = parser.parse()

        assert len(articles) == 2
        p_art = articles[0]
        assert p_art["site"] == "Portfolio"
        assert p_art["title"] == "Megszólalt a jegybank elnöke"
        assert p_art["section"] == "gazdasag"

        pc_art = articles[1]
        assert "Pénzcentrum" in pc_art["section"]
        assert pc_art["title"] == "Új állampapír érkezik a magyaroknak"


class TestVadhajtasokParser:
    def test_parse_date_based_url_and_filter_hashtags(self):
        html = """
        <div class="post-feed">
            <article class="post">
                <h2 class="post-title">
                    <a href="https://www.vadhajtasok.hu/2026/09/08/fontos-bejelentes-tortent/">
                        Rendkívüli sajtótájékoztatót tartottak Budapesten
                    </a>
                </h2>
                <div class="post-excerpt">
                    <p>A részletekről élőben számoltak be a politikusok.</p>
                </div>
            </article>
            <article class="post">
                <a href="https://www.vadhajtasok.hu/cimke/haboru/">#háború</a>
            </article>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        parser = VadhajtasokParser(soup=soup, source_file="vadhajtasok_test.html")
        articles = parser.parse()

        assert len(articles) == 1
        art = articles[0]
        assert art["site"] == "Vadhajtasok"
        assert art["title"] == "Rendkívüli sajtótájékoztatót tartottak Budapesten"
        assert art["link"] == "https://www.vadhajtasok.hu/2026/09/08/fontos-bejelentes-tortent"
        assert art["lead"] == "A részletekről élőben számoltak be a politikusok."
