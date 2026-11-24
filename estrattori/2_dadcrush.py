import os, re, time, random, json, shutil, subprocess, requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs, quote_plus

# 1. Pagine principali (dopo il primo giro completo, lascia SOLO la Pagina 1)
pagine_indice = [
    "https://porn4days.pw/search/?s=Dadcrush",
    "https://porn4days.pw/search/page2/?s=Dadcrush",
    "https://porn4days.pw/search/page3/?s=Dadcrush",
    "https://porn4days.pw/search/page4/?s=Dadcrush",
    "https://porn4days.pw/search/page5/?s=Dadcrush",
    "https://porn4days.pw/search/page6/?s=Dadcrush",
    "https://porn4days.pw/search/page7/?s=Dadcrush",
    "https://porn4days.pw/search/page8/?s=Dadcrush",
    "https://porn4days.pw/search/page9/?s=Dadcrush",
    "https://porn4days.pw/search/page10/?s=Dadcrush",
    "https://porn4days.pw/search/page11/?s=Dadcrush",
    "https://porn4days.pw/search/page12/?s=Dadcrush",
    "https://porn4days.pw/search/page13/?s=Dadcrush",
    "https://porn4days.pw/search/page14/?s=Dadcrush",
    "https://porn4days.pw/search/page15/?s=Dadcrush",
    "https://porn4days.pw/search/page16/?s=Dadcrush",
]
# 2. Siti alternativi veloci (senza Playwright) usando il segnaposto QUERY_QUI
SITI_ALTERNATIVI = [
    "https://horny69.com/studios/dad-crush",
]

FILE_STORICO = "archivio_storico/dadcrush.txt"
FILE_MANCANTI = "archivio_storico/da_recuperare_dadcrush.txt"
FILE_PLAYLIST = "output_m3u8/2_dadcrush.m3u8"
DURATA_MINIMA_ASSOLUTA = 180  # 3 minuti minimi anti-pubblicità

os.makedirs("archivio_storico", exist_ok=True)
os.makedirs("output_m3u8", exist_ok=True)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8"})


def ricava_categoria(url):
    parsed = urlparse(url)
    parametri = parse_qs(parsed.query)
    if "s" in parametri and parametri["s"]:
        return parametri["s"][0].replace("+", " ").strip().title()
    parti = [p for p in parsed.path.strip("/").split("/") if not re.match(r'^page[-_]?\d+$', p, re.IGNORECASE)]
    return parti[-1].replace("-", " ").replace("_", " ").strip().title() if parti else "Generale"


def estrai_durata_da_html(soup, html_text):
    for prop in ["video:duration", "og:video:duration", "duration"]:
        tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop}) or soup.find("meta", attrs={"itemprop": prop})
        if tag and tag.get("content"):
            val = tag["content"].strip()
            if val.isdigit():
                return int(val)
            m_iso = re.match(r'^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$', val, re.IGNORECASE)
            if m_iso:
                h, m, s = [int(x) if x else 0 for x in m_iso.groups()]
                return h * 3600 + m * 60 + s
    m_txt = re.search(r'(?:durata|duration|length)[^0-9]{0,15}(\d{1,2}):(\d{2})(?::(\d{2}))?', html_text, re.IGNORECASE)
    if m_txt:
        p1, p2, p3 = m_txt.groups()
        return int(p1) * 3600 + int(p2) * 60 + int(p3) if p3 else int(p1) * 60 + int(p2)
    return None


def genera_query_ricerca(titolo_grezzo):
    titolo = re.sub(r'\s+(?:-|\||–|—)\s+[^-|\–—]+$', '', titolo_grezzo).strip()
    titolo = re.sub(r'\[.*?\]|\(.*?\)', '', titolo)
    titolo_pulito = re.sub(r'\b(streaming|ita|sub\s*ita|hd|full\s*hd|4k|gratis|guarda)\b', '', titolo, flags=re.IGNORECASE)
    titolo_pulito = " ".join(titolo_pulito.split()).strip()
    queries = [titolo_pulito]
    parole = titolo_pulito.split()
    if len(parole) > 4:
        numeri = re.findall(r'\d+', titolo_pulito)
        base_corta = " ".join(parole[:4])
        if numeri and numeri[-1] not in base_corta:
            base_corta += f" {numeri[-1]}"
        if base_corta.lower() != titolo_pulito.lower():
            queries.append(base_corta)
    return queries


def verifica_flusso_reale(url_flusso, referer, durata_target=None):
    parsed_ref = urlparse(referer)
    origin = f"{parsed_ref.scheme}://{parsed_ref.netloc}"
    headers_str = f"Referer: {referer}\r\nOrigin: {origin}\r\n"

    try:
        # Pre-controllo rapido HTTP per scartare subito falsi .m3u8 (es. pagine HTML 403/404)
        if ".m3u8" in url_flusso.lower():
            r = session.get(url_flusso, headers={"Referer": referer, "Origin": origin}, timeout=10)
            if r.status_code != 200 or "#EXTM3U" not in r.text[:200]:
                return False

        if not shutil.which("ffprobe") or not shutil.which("ffmpeg"):
            return True

        # STEP 1: Controllo durata e codec con ffprobe
        cmd_probe = [
            "ffprobe", "-v", "error",
            "-user_agent", USER_AGENT,
            "-headers", headers_str,
            "-show_entries", "format=duration:stream=codec_type",
            "-of", "json", url_flusso
        ]
        res_p = subprocess.run(cmd_probe, capture_output=True, text=True, timeout=15)
        if res_p.returncode != 0 or not res_p.stdout.strip():
            return False

        dati = json.loads(res_p.stdout)
        ha_video = any(s.get("codec_type") == "video" for s in dati.get("streams", []))
        durata = float(dati.get("format", {}).get("duration", 0))

        if not ha_video or durata < DURATA_MINIMA_ASSOLUTA:
            return False
        if durata_target and durata_target > DURATA_MINIMA_ASSOLUTA:
            tolleranza = max(120, durata_target * 0.20)
            if abs(durata - durata_target) > tolleranza:
                return False

        # STEP 2: Scarica e decodifica REALMENTE i primi 2 secondi di video con ffmpeg
        cmd_decode = [
            "ffmpeg", "-v", "error",
            "-user_agent", USER_AGENT,
            "-headers", headers_str,
            "-i", url_flusso,
            "-t", "2",
            "-f", "null", "-"
        ]
        res_d = subprocess.run(cmd_decode, capture_output=True, text=True, timeout=20)
        return res_d.returncode == 0
    except Exception:
        return False


pat_srv = re.compile(r'([A-Z0-9_]*SERVER[A-Z0-9_]*)\s*=\s*["\'](https?://[^"\']+)["\']', re.IGNORECASE)
pat_flussi = re.compile(r'["\'](https?://[^"\']+\.(?:m3u8|mp4)[^"\']*)["\']', re.IGNORECASE)
parole_pub = ("ads", "vast", "preroll", "banner", "doubleclick", "googleads", "promo", "spot")


def estrai_flussi_da_pagina(html_text, soup, base_url):
    candidati, visti = [], set()
    for nome, link in pat_srv.findall(html_text):
        if link not in visti:
            candidati.append((nome, link))
            visti.add(link)
    for tag in soup.find_all(["video", "source", "hlsjs-video"], src=True):
        link = urljoin(base_url, tag["src"].strip())
        if link not in visti and not any(p in link.lower() for p in parole_pub):
            candidati.append(("VIDEO_TAG", link))
            visti.add(link)
    for link in pat_flussi.findall(html_text):
        if link not in visti and not any(p in link.lower() for p in parole_pub):
            candidati.append(("REGEX_STREAM", link))
            visti.add(link)
    return candidati


def cerca_su_siti_alternativi_veloce(titolo_grezzo, durata_target):
    queries = genera_query_ricerca(titolo_grezzo)
    for template in SITI_ALTERNATIVI:
        if "QUERY_QUI" not in template:
            continue
        for q in queries:
            url_ric = template.replace("QUERY_QUI", quote_plus(q))
            parsed_alt = urlparse(url_ric)
            base_alt = f"{parsed_alt.scheme}://{parsed_alt.netloc}/"
            try:
                r_ric = session.get(url_ric, timeout=15)
                soup_ric = BeautifulSoup(r_ric.text, "html.parser")
                risultati = []
                for a in soup_ric.find_all("a", href=True):
                    img = a.find("img")
                    if img:
                        src_img = img.get("data-src") or img.get("data-original") or img.get("src") or ""
                        if "favicon" in src_img.lower() or "logo" in src_img.lower():
                            continue
                        u_res = urljoin(url_ric, a["href"].strip())
                        if urlparse(u_res).path != "/" and u_res != url_ric and u_res not in risultati:
                            risultati.append(u_res)
                            if len(risultati) >= 3:
                                break
                for u_video_alt in risultati:
                    r_v = session.get(u_video_alt, headers={"Referer": url_ric}, timeout=15)
                    soup_v = BeautifulSoup(r_v.text, "html.parser")
                    candidati = estrai_flussi_da_pagina(r_v.text, soup_v, base_alt)
                    for _, link_flusso in candidati:
                        if verifica_flusso_reale(link_flusso, u_video_alt, durata_target):
                            return parsed_alt.netloc, link_flusso, u_video_alt
                    time.sleep(0.8)
            except Exception:
                continue
    return None, None, None
 
gia_estratti = set()
if os.path.exists(FILE_STORICO):
    with open(FILE_STORICO, "r", encoding="utf-8") as f:
        gia_estratti = {r.strip() for r in f if r.strip()}

nuovi_link, link_visti = [], set()
for idx_pag, pagina in enumerate(pagine_indice, start=1):
    try:
        parsed = urlparse(pagina)
        base_url = f"{parsed.scheme}://{parsed.netloc}/"
        gruppo = ricava_categoria(pagina)
        risposta = session.get(pagina, timeout=15)
        soup = BeautifulSoup(risposta.text, "html.parser")
        trovati = 0
        for link in soup.find_all("a", href=True):
            img = link.find("img")
            if img:
                raw_logo = img.get("data-src") or img.get("data-original") or img.get("src") or ""
                if "favicon" in raw_logo.lower() or "graphics/" in raw_logo.lower():
                    continue
                href = link["href"].strip()
                url_completo = urljoin(pagina, href)
                if url_completo.rstrip("/") == base_url.rstrip("/"):
                    continue
                if url_completo not in gia_estratti and url_completo not in link_visti:
                    link_visti.add(url_completo)
                    trovati += 1
                    logo = urljoin(pagina, raw_logo) if raw_logo and not raw_logo.startswith("data:") else ""
                    nuovi_link.append((url_completo, pagina, f"p{idx_pag}v{trovati}", logo, gruppo))
        print(f"Pagina {idx_pag} [{gruppo}]: {trovati} nuovi link")
        if idx_pag < len(pagine_indice):
            time.sleep(random.uniform(1.5, 2.5))
    except Exception as e:
        print(f"Errore pagina {pagina}: {e}")

nuovi_video, mancanti = [], []
for url_video, pag_orig, tvg_id, logo_url, gruppo in nuovi_link:
    try:
        parsed_v = urlparse(url_video)
        base_v = f"{parsed_v.scheme}://{parsed_v.netloc}/"
        res = session.get(url_video, headers={"Referer": pag_orig}, timeout=15)
        soup_v = BeautifulSoup(res.text, "html.parser")
        titolo_raw = soup_v.title.get_text(strip=True) if soup_v.title else "Video"
        titolo = " ".join(titolo_raw.split()).replace(",", " -")
        durata_orig = estrai_durata_da_html(soup_v, res.text)
        if not logo_url:
            og = soup_v.find("meta", property="og:image")
            if og and og.get("content"):
                logo_url = og["content"]

        candidati = estrai_flussi_da_pagina(res.text, soup_v, base_v)
        srv_ok, link_ok, ref_vlc = None, None, url_video
        for nome, link in candidati:
            if verifica_flusso_reale(link, url_video, durata_orig):
                srv_ok, link_ok = nome, link
                break

        if not link_ok and SITI_ALTERNATIVI:
            dom_alt, link_alt, ref_alt = cerca_su_siti_alternativi_veloce(titolo, durata_orig)
            if link_alt:
                srv_ok, link_ok, ref_vlc = f"ALT:{dom_alt}", link_alt, ref_alt

        if link_ok:
            nuovi_video.append((tvg_id, logo_url, gruppo, titolo, link_ok, ref_vlc))
            print(f"[OK - {srv_ok}] {titolo}")
        else:
            mancanti.append((gruppo, logo_url, titolo, url_video))
            print(f"[DA RECUPERARE] {titolo}")

        gia_estratti.add(url_video)
        time.sleep(random.uniform(0.8, 1.5))
    except Exception as e:
        print(f"Errore su {url_video}: {e}")

with open(FILE_STORICO, "w", encoding="utf-8") as f:
    for u in sorted(gia_estratti):
        f.write(f"{u}\n")

if mancanti:
    with open(FILE_MANCANTI, "a", encoding="utf-8") as f:
        for grp, logo, tit, u_orig in mancanti:
            f.write(f"TITOLO: {tit} | GRUPPO: {grp} | LOGO: {logo} | ORIGINE: {u_orig}\n")

if nuovi_video:
    esiste = os.path.exists(FILE_PLAYLIST) and os.path.getsize(FILE_PLAYLIST) > 0
    with open(FILE_PLAYLIST, "a", encoding="utf-8") as f:
        if not esiste:
            f.write("#EXTM3U\n")
        for tid, logo, grp, tit, fls, ref in nuovi_video:
            f.write(f'#EXTINF:-1 tvg-id="{tid}" tvg-logo="{logo}" group-title="{grp}",{tit}\n')
            f.write(f"#EXTVLCOPT:http-user-agent={USER_AGENT}\n")
            f.write(f"#EXTVLCOPT:http-referrer={ref}\n")
            f.write(f"{fls}\n")

print(f"\nCompletato! Aggiunti {len(nuovi_video)} video OK, salvati {len(mancanti)} in '{FILE_MANCANTI}'.")
