import argparse
import random
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from seleniumbase import Driver


def simulate_human_reading(driver):
    """
    Kiegyensúlyozott, gyorsabb görgetési viselkedés:
    - Cookie/hozzájárulási bannerek gyors kezelése
    - Hatékonyabb, nagyobb lépésközű görgetés a lazy loading tartalom aktiválására
    - Minimális, célzott várakozások a folyamat pörgősebbé tételéhez
    """
    # 1. Cookie / adatvédelmi sávok és felugró ablakok gyors ellenőrzése
    cookie_button_selectors = [
        "#didomi-notice-agree-button",
        ".cmp-agree",
        "button[id*='accept']",
        "button[class*='accept']",
        "button[id*='agree']",
        "button[class*='agree']",
        "button[aria-label*='Elfogad']",
        "button[aria-label*='Accept']",
        "a[class*='agree']",
        ".cookie-accept",
        "#accept-cookies",
        ".modal-close",
        ".close-popup",
    ]
    for selector in cookie_button_selectors:
        try:
            if driver.is_element_visible(selector):
                driver.click(selector)
                time.sleep(random.uniform(0.2, 0.4))
                break
        except Exception:
            pass

    # 2. Dinamikusabb, lendületesebb görgetés lefelé a tartalmak betöltéséhez
    total_height = driver.execute_script("return document.body.scrollHeight")
    current_scroll = 0
    max_scroll_attempts = 12
    attempts = 0

    while current_scroll < total_height and attempts < max_scroll_attempts:
        attempts += 1
        scroll_step = random.randint(900, 1500)
        current_scroll += scroll_step
        driver.execute_script(f"window.scrollBy(0, {scroll_step});")
        time.sleep(random.uniform(0.15, 0.35))

        new_total_height = driver.execute_script("return document.body.scrollHeight")
        if new_total_height > total_height:
            total_height = new_total_height

    # 3. Lap aljának gyors ellenőrzése
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(random.uniform(0.3, 0.6))

    # 4. Gyors visszagörgetés a lap tetejére
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(random.uniform(0.2, 0.4))


def slugify_rovat_name(name: str) -> str:
    """Rovat nevének normalizálása biztonságos fájlnév-komponenssé."""
    import unicodedata

    n = unicodedata.normalize("NFKD", name)
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = re.sub(r"[^\w\s-]", "", n).strip().lower()
    return re.sub(r"[-\s]+", "_", n)


def load_rovatok_urls(txt_path: Path = None) -> dict[str, list[dict[str, str]]]:
    """
    Rovatok beolvasása a rovatok_urljei.txt fájlból portálonként.
    Visszaadja: {portal_id_name: [{'url': ..., 'name': ...}, ...]}
    """
    if txt_path is None:
        txt_path = Path(__file__).parent / "rovatok_urljei.txt"

    if not txt_path.exists():
        return {}

    rovatok_by_site: dict[str, list[dict[str, str]]] = {}
    current_site = None

    with txt_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                current_site = line[1:-1]
                rovatok_by_site.setdefault(current_site, [])
            elif current_site:
                parts = line.split("\t#")
                url = parts[0].strip()
                name = parts[1].strip() if len(parts) > 1 else ""
                if not name and "#" in line:
                    subparts = line.split("#", 1)
                    url = subparts[0].strip()
                    name = subparts[1].strip()
                rovatok_by_site[current_site].append({"url": url, "name": name})

    return rovatok_by_site


def scrape_single_page(driver: Driver, url: str, output_path: Path, max_retries: int = 2) -> bool:
    """
    Egyetlen URL (címlap vagy rovatoldal) meglátogatása, pörgős görgetése,
    linkek normalizálása és HTML mentése hibatűrő módon.
    """
    for attempt in range(1, max_retries + 1):
        try:
            time.sleep(random.uniform(0.3, 0.7))
            driver.get(url)
            driver.sleep(random.uniform(1.2, 2.0))

            # Ellenőrizzük, hogy sikerült-e valós oldalt elérni
            current_title = driver.title or ""
            print(f"    [+] Pörgős görgetés és feldolgozás: {url} (Cím: '{current_title[:40]}...')")
            simulate_human_reading(driver)

            page_source = driver.page_source
            if not page_source or len(page_source) < 500:
                raise ValueError(f"Túl rövid HTML forráskód ({len(page_source) if page_source else 0} bájt)")

            parsed_url = urlparse(url)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
            soup = BeautifulSoup(page_source, "html.parser")
            for tag in soup.find_all(href=True):
                tag["href"] = urljoin(base_url, tag["href"])
            for tag in soup.find_all(src=True):
                tag["src"] = urljoin(base_url, tag["src"])
            normalized_html = str(soup)

            output_path.write_text(normalized_html, encoding="utf-8")
            print(f"    [✓] HTML sikeresen mentve: {output_path.name} ({len(normalized_html)/1024:.1f} KB)")
            return True
        except Exception as e:
            err_str = str(e)
            print(f"    [!] Hiba ({attempt}/{max_retries}) a(z) {url} feldolgozása közben: {e}")
            if "ERR_CONNECTION_REFUSED" in err_str or "refused" in err_str.lower() or "disconnected" in err_str.lower():
                # A Chrome összeomlott vagy a CDP socket kapcsolat megszakadt: továbbdobjuk a hívónak böngésző-újraindításra
                raise
            if attempt < max_retries:
                wait_time = random.uniform(3.0, 6.0)
                print(f"    [~] Újrapróbálkozás {wait_time:.1f} mp múlva...")
                time.sleep(wait_time)
            else:
                return False
    return False


def init_driver(
    headless: bool,
    ad_block_on: bool = True,
    block_images: bool = True,
    page_load_strategy: str = "eager",
    page_load_timeout: int = 15,
) -> Driver:
    """Tiszta Chrome Driver példány indítása beépített ad-blockerrel, képletiltással és eager stratégiával."""
    driver = Driver(
        uc=True,
        headless=headless,
        ad_block_on=ad_block_on,
        block_images=block_images,
        page_load_strategy=page_load_strategy,
    )
    if page_load_timeout:
        driver.set_page_load_timeout(page_load_timeout)
    return driver


def cleanup_driver(driver) -> None:
    """Böngésző biztonságos és tiszta leállítása."""
    if driver is None:
        return
    try:
        driver.quit()
    except Exception:
        pass


def scrape_frontpages(
    output_dir: Path = None,
    headless: bool = False,
    include_rovatok: bool = False,
    rovatok_path: Path = None,
    sites_filter: list[str] = None,
    max_rovatok_per_site: int = None,
    shuffle_order: bool = True,
    skip_existing: bool = True,
    target_date_str: str = None,
    max_retries_per_run: int = 8,
    max_pages_per_session: int = 8,
) -> list[Path]:
    """
    A 6 híroldal címlapjának (és opcionálisan a rovatoldalaknak) meglátogatása,
    görgetése, linknormalizálása és HTML mentése.
    Visszaadja a frissen lementett HTML fájlok listáját.
    Ha shuffle_order=True, a letöltendő oldalak véletlenszerű sorrendben futnak.
    Ha skip_existing=True és egy célfájl már létezik és nem üres, átugorja.
    Garantálja (max_retries_per_run ellenőrző ciklussal), hogy az elvárt oldalak mindegyike
    sikeresen le legyen mentve böngésző-leállások esetén is.
    max_pages_per_session: ennyi oldal után a Chrome memória- és kapcsolatfrissítésként újraindul (alapérték: 8).
    """
    sites = [
        {"id": "1", "short_name": "Origo", "url": "https://www.origo.hu"},
        {"id": "2", "short_name": "Nepszava", "url": "https://nepszava.hu"},
        {"id": "3", "short_name": "Huszonnegy", "url": "https://24.hu"},
        {"id": "4", "short_name": "Blikk", "url": "https://www.blikk.hu"},
        {"id": "5", "short_name": "Portfolio", "url": "https://www.portfolio.hu"},
        {"id": "6", "short_name": "Vadhajtasok", "url": "https://www.vadhajtasok.hu"},
    ]

    if sites_filter:
        sites = [s for s in sites if s["id"] in sites_filter or s["short_name"].lower() in [f.lower() for f in sites_filter]]

    if output_dir is None:
        output_dir = Path(__file__).parent / "scraped_data"
    output_dir.mkdir(parents=True, exist_ok=True)

    rovatok_dict = {}
    if include_rovatok:
        rovatok_dict = load_rovatok_urls(rovatok_path)
        total_rovatok = sum(len(r) for r in rovatok_dict.values())
        print(f"[+] Rovatok beolvasva: {total_rovatok} rovat URL a listából.")

    date_str = target_date_str or datetime.now(tz=ZoneInfo("Europe/Budapest")).strftime("%Y-%m-%d_%H-%M-%S")
    saved_files: list[Path] = []

    # Letöltési feladatok összeállítása
    tasks: list[dict] = []
    for site in sites:
        site_id = site["id"]
        short_name = site["short_name"]
        url = site["url"]
        site_key = f"{site_id}_{short_name}"
        base_filename = f"{site_id}_{short_name}_{date_str}.html"
        tasks.append({
            "type": "címlap",
            "site_id": site_id,
            "short_name": short_name,
            "name": f"{short_name} címlap",
            "url": url,
            "output_path": output_dir / base_filename,
        })

        if include_rovatok and site_key in rovatok_dict:
            rovat_list = rovatok_dict[site_key]
            if max_rovatok_per_site:
                rovat_list = rovat_list[:max_rovatok_per_site]

            for r_idx, rovat in enumerate(rovat_list, 1):
                rovat_url = rovat["url"]
                rovat_name = rovat.get("name", "")
                slug = slugify_rovat_name(rovat_name) if rovat_name else f"rovat_{r_idx}"
                rovat_filename = f"{site_id}_{short_name}_rovat_{slug}_{date_str}.html"
                tasks.append({
                    "type": "rovat",
                    "site_id": site_id,
                    "short_name": short_name,
                    "name": f"{short_name} / {rovat_name or slug}",
                    "url": rovat_url,
                    "output_path": output_dir / rovat_filename,
                })

    if skip_existing:
        tasks_to_run = [t for t in tasks if not (t["output_path"].exists() and t["output_path"].stat().st_size > 0)]
        skipped_count = len(tasks) - len(tasks_to_run)
        if skipped_count > 0:
            print(f"[i] {skipped_count} már korábban sikeresen lementett fájl átugorva.")
            for t in tasks:
                if t["output_path"].exists() and t["output_path"].stat().st_size > 0:
                    saved_files.append(t["output_path"])
        tasks = tasks_to_run

    if shuffle_order:
        random.shuffle(tasks)

    print(f"[+] Letöltési folyamat indítása: {output_dir.resolve()}")
    print(f"    - Időbélyeg: {date_str}")
    print(f"    - Összes céloldal: {len(tasks)} db ({'véletlenszerű sorrendben' if shuffle_order else 'sorrendben'})")
    print(f"    - Böngésző mód: {'headless' if headless else 'ablakos (uc=True)'}")
    print(f"    - Rovatok letöltése: {'Igen' if include_rovatok else 'Nem'}")

    attempt_cycle = 0
    while attempt_cycle < max_retries_per_run:
        attempt_cycle += 1
        pending_tasks = [t for t in tasks if not (t["output_path"].exists() and t["output_path"].stat().st_size > 0)]
        if not pending_tasks:
            print(f"[✓] Minden céloldal ({len(tasks)} db) hiánytalanul le van mentve!")
            break

        if attempt_cycle > 1:
            print("\n" + "-" * 60)
            print(f"[!] {len(pending_tasks)} oldal még hiányzik vagy sikertelen volt. Pótlási kör indítása ({attempt_cycle}/{max_retries_per_run})...")
            print("-" * 60)
            time.sleep(2.0)

        tasks_to_execute = list(pending_tasks)
        if shuffle_order and attempt_cycle == 1:
            random.shuffle(tasks_to_execute)

        driver = init_driver(headless)
        pages_processed = 0

        try:
            for idx, task in enumerate(tasks_to_execute, 1):
                if pages_processed >= max_pages_per_session:
                    print(f"\n[~] Tervezett böngésző-frissítés ({max_pages_per_session} oldal után a memóriaszivárgás megelőzésére)...")
                    cleanup_driver(driver)
                    time.sleep(1.0)
                    driver = init_driver(headless)
                    pages_processed = 0

                print(f"\n[{idx}/{len(tasks_to_execute)}] {task['type'].upper()}: {task['name']} ({task['url']})")
                success = False
                try:
                    success = scrape_single_page(driver, task["url"], task["output_path"])
                    pages_processed += 1
                except Exception as outer_e:
                    print(f"    [!] Hiba a böngészőben ({outer_e}). Böngésző újraindítása...")
                    cleanup_driver(driver)
                    time.sleep(1.5)
                    driver = init_driver(headless)
                    pages_processed = 0
                    try:
                        success = scrape_single_page(driver, task["url"], task["output_path"])
                        pages_processed += 1
                    except Exception as retry_e:
                        print(f"    [!] Újraindítás után sem sikerült: {retry_e}")

                if success and task["output_path"] not in saved_files:
                    saved_files.append(task["output_path"])

        finally:
            print("\n[+] Böngésző bezárása az aktuális kör után...")
            cleanup_driver(driver)

    # Záró ellenőrzés
    final_missing = [t for t in tasks if not (t["output_path"].exists() and t["output_path"].stat().st_size > 0)]
    if final_missing:
        print(f"\n[!] FIGYELEM: {max_retries_per_run} kör után is hiányzik még {len(final_missing)} oldal:")
        for fm in final_missing:
            print(f"    - {fm['name']}: {fm['url']}")
    else:
        print(f"\n[✓] Teljes siker: mind a {len(tasks)} oldal érvényes mérettel mentve.")

    # Csak azokat a fájlokat adjuk vissza, amelyek léteznek és érvényesek a feladatok közül
    valid_saved = [t["output_path"] for t in tasks if t["output_path"].exists() and t["output_path"].stat().st_size > 0]
    return valid_saved


def main():
    parser = argparse.ArgumentParser(description="Híroldalak címlapjainak és rovatainak letöltése SeleniumBase segítségével.")
    parser.add_argument("--headless", action="store_true", help="Böngésző futtatása háttérben (fej nélküli mód)")
    parser.add_argument("--include-rovatok", action="store_true", help="A rovatok_urljei.txt-ben található rovatok letöltése is")
    parser.add_argument("--rovatok-file", type=str, default="rovatok_urljei.txt", help="A rovatok URL-jeit tartalmazó fájl elérési útja")
    parser.add_argument("--site", type=str, nargs="*", help="Csak adott portál(ok) letöltése (pl. 1, Origo, Blikk)")
    parser.add_argument("--max-rovatok", type=int, default=None, help="Legfeljebb ennyi rovat letöltése portálonként (teszteléshez)")
    parser.add_argument("--output-dir", type=str, default="scraped_data", help="Kimeneti HTML könyvtár")
    parser.add_argument("--no-shuffle", action="store_true", help="Ne keverje össze véletlenszerűen a letöltendő oldalak sorrendjét")
    parser.add_argument("--no-skip-existing", action="store_true", help="Ne ugorja át a már meglévő fájlokat")
    parser.add_argument("--target-date", type=str, default=None, help="Megadott időbélyeg használata (pl. elmaradt oldalak pótlásához)")
    parser.add_argument("--max-retries", type=int, default=8, help="Maximális pótlási körök száma (alapérték: 8)")
    parser.add_argument("--max-pages-per-session", type=int, default=8, help="Hány oldalanként induljon újra a böngésző memóriatisztítás céljából")

    args = parser.parse_args()

    scrape_frontpages(
        output_dir=Path(args.output_dir),
        headless=args.headless,
        include_rovatok=args.include_rovatok,
        rovatok_path=Path(args.rovatok_file) if args.rovatok_file else None,
        sites_filter=args.site,
        max_rovatok_per_site=args.max_rovatok,
        shuffle_order=not args.no_shuffle,
        skip_existing=not args.no_skip_existing,
        target_date_str=args.target_date,
        max_retries_per_run=args.max_retries,
        max_pages_per_session=args.max_pages_per_session,
    )


if __name__ == "__main__":
    main()
