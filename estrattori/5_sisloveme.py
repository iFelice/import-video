import os, re, time, random, subprocess, requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs, quote_plus
from playwright.sync_api import sync_playwright

# 1. Pagine principali (dopo il primo giro completo, lascia SOLO la Pagina 1)
pagine_indice = [
    "https://porn4days.pw/search/?s=SisLovesMe",
    "https://porn4days.pw/search/page2/?s=SisLovesMe",
    "https://porn4days.pw/search/page3/?s=SisLovesMe",
    "https://porn4days.pw/search/page4/?s=SisLovesMe",
    "https://porn4days.pw/search/page5/?s=SisLovesMe",
]
# 2. Siti alternativi veloci (senza Playwright) usando il segnaposto QUERY_QUI
SITI_ALTERNATIVI = [
    "https://horny69.com/search?q=/{query}",
    
]

FILE_STORICO = "archivio_storico/sisloveme.txt"
FILE_MANCANTI = "archivio_storico/da_recuperare_sisloveme.txt"
FILE_PLAYLIST = "output_m3u8/5_sisloveme.m3u8"

os.makedirs("archivio_storico", exist_ok=True)
os.makedirs("output_m3u8", exist_ok=True)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def ricava_categoria_da_url(url):
    parsed = urlparse(url)
    parametri = parse_qs(parsed.query)
    if "s" in parametri and parametri["s"]:
        return parametri["s"][0].replace("+", " ").strip().title()
    percorso = parsed.path.strip("/")
    if not percorso:
        return "Home"
    parti = [p for p in percorso.split("/") if not re.match(r'^page[-_]?\d+$', p, re.IGNORECASE)]
    return parti[-1].replace("-", " ").replace("_", " ").strip().title() if parti else "Generale"

def pulisci_titolo_per_ricerca(titolo_grezzo):
    for sep in [" - ", " | ", " – ", " — "]:
        if sep in titolo_grezzo:
            titolo_grezzo = titolo_grezzo.split(sep)[0]
    return titolo_grezzo.strip()

session = requests.Session()
session.headers.update({
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
})

gia_estratti = set()
if os.path.exists(FILE_STORICO):
    with open(FILE_STORICO, "r", encoding="utf-8") as f:
        gia_estratti = {riga.strip() for riga in f if riga.strip()}

nuovi_link, link_visti = [], set()

for idx_pag, pagina in enumerate(pagine_indice, start=1):
    try:
        parsed = urlparse(pagina)
        base_url = f"{parsed.scheme}://{parsed.netloc}/"
        gruppo_cat = ricava_categoria_da_url(pagina)
        risposta = session.get(pagina, timeout=15)
        print(f"Controllo: {pagina} [Gruppo: {gruppo_cat}] (HTTP: {risposta.status_code})")
        soup = BeautifulSoup(risposta.text, "html.parser")
        trovati = 0
        for link in soup.find_all("a", href=True):
            img_tag = link.find("img")
            if img_tag:
                raw_logo = img_tag.get("data-src") or img_tag.get("data-original") or img_tag.get("src") or ""
                if "favicon" in raw_logo.lower() or "graphics/" in raw_logo.lower():
                    continue
                href_orig = link["href"].strip()
                url_completo = urljoin(pagina, href_orig) if href_orig.startswith("..") else urljoin(base_url, href_orig.lstrip("/"))
                if url_completo.rstrip("/") == base_url.rstrip("/"):
                    continue
                if url_completo not in gia_estratti and url_completo not in link_visti:
                    link_visti.add(url_completo)
                    trovati += 1
                    logo_url = urljoin(pagina, raw_logo) if raw_logo and not raw_logo.startswith("data:") else ""
                    nuovi_link.append((url_completo, pagina, f"p{idx_pag}v{trovati}", logo_url, gruppo_cat))
        print(f" -> Nuovi link trovati: {trovati}")
        if idx_pag < len(pagine_indice):
            time.sleep(random.uniform(2.0, 3.5))
    except Exception as e:
        print(f"Errore pagina {pagina}: {e}")

print(f"\nTotale nuovi link da analizzare: {len(nuovi_link)}\n")

pat_srv = re.compile(r'([A-Z0-9_]*SERVER[A-Z0-9_]*)\s*=\s*["\'](https?://[^"\']+)["\']', re.IGNORECASE)
pat_m3u8 = re.compile(r'["\'](https?://[^"\']+\.(?:m3u8|mp4)[^"\']*)["\']', re.IGNORECASE)

def verifica_link_reale(url_flusso, referer):
    try:
        if ".m3u8" in url_flusso.lower():
            r = session.get(url_flusso, headers={"User-Agent": USER_AGENT, "Referer": referer}, timeout=10)
            if r.status_code != 200 or "#EXTM3U" not in r.text[:200]:
                return False
        cmd = [
            "ffprobe", "-v", "error", "-user_agent", USER_AGENT,
            "-headers", f"Referer: {referer}\r\n",
            "-show_entries", "stream=codec_type",
            "-of", "default=noprint_wrappers=1:nokey=1", url_flusso
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return "video" in res.stdout
    except Exception:
        return False

def trova_server(html_text, soup_video, url_pagina):
    candidati, visti = [], set()
    for nome, link in pat_srv.findall(html_text):
        if link not in visti:
            candidati.append((nome, link))
            visti.add(link)
    tag_hls = soup_video.find("hlsjs-video", src=True)
    if tag_hls and tag_hls["src"] not in visti:
        candidati.append(("HLSJS_TAG", tag_hls["src"]))
        visti.add(tag_hls["src"])
    for link in pat_m3u8.findall(html_text):
        if link not in visti:
            candidati.append(("FALLBACK_M3U8", link))
            visti.add(link)
    for nome, link in candidati:
        if verifica_link_reale(link, url_pagina):
            return nome, link
    return None, None
def cerca_con_playwright(page, titolo_ricerca):
    query = quote_plus(titolo_ricerca)
    js_find = "() => { for (const a of document.querySelectorAll('a[href]')) { if (a.querySelector('img') && !a.href.includes('logo') && a.href !== window.location.href) return a.href; } return null; }"
    for template in SITI_ALTERNATIVI:
        url_ric = template.format(query=query)
        dom = urlparse(url_ric).netloc
        print(f"   -> Cerco '{titolo_ricerca}' su {dom}...")
        try:
            page.goto(url_ric, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(2000)
            primo = page.evaluate(js_find)
            if not primo:
                continue
            flusso = None

            def on_resp(resp):
                nonlocal flusso
                if (".m3u8" in resp.url.lower() or ".mp4" in resp.url.lower()) and resp.status in (200, 206) and not flusso:
                    flusso = resp.url

            page.on("response", on_resp)
            page.goto(primo, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(3000)
            if not flusso:
                try:
                    page.mouse.click(640, 360)
                    page.wait_for_timeout(4000)
                except Exception:
                    pass
            page.remove_listener("response", on_resp)
            if flusso and verifica_link_reale(flusso, primo):
                return dom, flusso, primo
        except Exception as e:
            print(f"   -> Errore su {dom}: {e}")
    return None, None, None



nuovi_video, mancanti = [], []

with sync_playwright() as p:
    browser = None
    page = None
    try:
        for url_video, pag_orig, tvg_id, logo_url, gruppo in nuovi_link:
            try:
                res = session.get(url_video, headers={"Referer": pag_orig}, timeout=15)
                soup_v = BeautifulSoup(res.text, "html.parser")
                titolo_raw = soup_v.title.get_text(strip=True) if soup_v.title else "Video"
                titolo = " ".join(titolo_raw.split()).replace(",", " -")
                if not logo_url:
                    og = soup_v.find("meta", property="og:image")
                    if og and og.get("content"):
                        logo_url = og["content"]

                srv, link_ok = trova_server(res.text, soup_v, url_video)
                ref_vlc = url_video if link_ok else None

                if not link_ok and SITI_ALTERNATIVI:
                    if browser is None:
                        browser = p.chromium.launch(headless=True)
                        page = browser.new_context(user_agent=USER_AGENT).new_page()
                    tit_clean = pulisci_titolo_per_ricerca(titolo)
                    print(f"[FALLBACK] '{tit_clean}' -> Uso Playwright...")
                    dom, link_ok, ref_vlc = cerca_con_playwright(page, tit_clean)
                    if link_ok:
                        srv = f"ALT:{dom}"

                if link_ok:
                    nuovi_video.append((tvg_id, logo_url, gruppo, titolo, link_ok, ref_vlc))
                    print(f"[OK - {srv}] [{gruppo}] {tvg_id} | {titolo}")
                    gia_estratti.add(url_video)
                else:
                    mancanti.append((gruppo, logo_url, titolo, url_video))
                    print(f"[FALLITO OVUNQUE] {url_video} (Titolo: {titolo})")

                time.sleep(random.uniform(1.5, 2.5))
            except Exception as e:
                print(f"Errore su {url_video}: {e}")
    finally:
        if browser:
            browser.close()

with open(FILE_STORICO, "w", encoding="utf-8") as f:
    for u in sorted(gia_estratti):
        f.write(f"{u}\n")

if mancanti:
    gia_mancanti = set()
    if os.path.exists(FILE_MANCANTI):
        with open(FILE_MANCANTI, "r", encoding="utf-8") as f:
            gia_mancanti = {r.strip() for r in f if r.strip()}
    with open(FILE_MANCANTI, "a", encoding="utf-8") as f:
        for grp, logo, tit, u_orig in mancanti:
            riga = f"TITOLO: {tit} | GRUPPO: {grp} | LOGO: {logo} | ORIGINE: {u_orig}"
            if riga not in gia_mancanti:
                f.write(f"{riga}\n")
                gia_mancanti.add(riga)

if nuovi_video:
    esiste = os.path.exists(FILE_PLAYLIST) and os.path.getsize(FILE_PLAYLIST) > 0
    with open(FILE_PLAYLIST, "a", encoding="utf-8") as f:
        if not esiste:
            f.write("#EXTM3U\n")
        for tid, logo, grp, tit, fls, ref in nuovi_video:
            f.write(f'#EXTINF:-1 tvg-id="{tid}" tvg-logo="{logo}" group-title="{grp}",{tit}\n')
            f.write(f"#EXTVLCOPT:http-user-agent={USER_AGENT}\n")
            if ref:
                f.write(f"#EXTVLCOPT:http-referrer={ref}\n")
            f.write(f"{fls}\n")

print(f"\nFatto! Aggiunti {len(nuovi_video)} nuovi video a '{FILE_PLAYLIST}'.")
