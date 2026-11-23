import os
import re
import time
import random
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

# 1. Inserisci qui gli URL esatti delle pagine indice / categoria
pagine_indice = [
    "https://porn4days.pw/newest",
    "https://porn4days.pw/newest/page2/",
    "https://porn4days.pw/newest/page3/",
    "https://porn4days.pw/newest/page4/",
    "https://porn4days.pw/newest/page5/",
    "https://porn4days.pw/newest/page6/",
    "https://porn4days.pw/newest/page7/",
    "https://porn4days.pw/newest/page8/",
    "https://porn4days.pw/newest/page9/",
    "https://porn4days.pw/newest/page10/",
    "https://porn4days.pw/newest/page11/",
    "https://porn4days.pw/newest/page12/",
    "https://porn4days.pw/newest/page13/",
]

FILE_STORICO = "storico_estratti.txt"
FILE_PLAYLIST = "playlist.m3u8"

def ricava_categoria_da_url(url):
    """Estrae un nome categoria pulito dall'URL (es. '/nuovi-video/page2/' -> 'Nuovi Video')"""
    percorso = urlparse(url).path.strip("/")
    if not percorso:
        return "Home"
    # Divide i segmenti dell'URL ed esclude quelli relativi alla paginazione (es. page2, page-2, p2)
    parti = [p for p in percorso.split("/") if not re.match(r'^page[-_]?\d+$', p, re.IGNORECASE)]
    if not parti:
        return "Generale"
    # Prende la categoria principale, sostituisce trattini/underscore con spazi e mette le maiuscole
    categoria = parti[-1].replace("-", " ").replace("_", " ").strip().title()
    return categoria

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
})

gia_estratti = set()
if os.path.exists(FILE_STORICO):
    with open(FILE_STORICO, "r", encoding="utf-8") as f:
        gia_estratti = {riga.strip() for riga in f if riga.strip()}

nuovi_link_da_estrarre = []
link_visti_in_questa_sessione = set()

# FASE 1: Trova i link dalle anteprime, copertina e categoria
for idx_pag, pagina in enumerate(pagine_indice, start=1):
    try:
        parsed = urlparse(pagina)
        base_url = f"{parsed.scheme}://{parsed.netloc}/"
        gruppo_categoria = ricava_categoria_da_url(pagina)
        
        risposta = session.get(pagina, timeout=15)
        print(f"Controllo: {pagina} [Gruppo: {gruppo_categoria}] (HTTP: {risposta.status_code})")
        
        soup = BeautifulSoup(risposta.text, "html.parser")
        trovati_pagina = 0
        
        for link in soup.find_all("a", href=True):
            img_tag = link.find("img")
            if img_tag:
                href_pulito = link["href"].lstrip("/")
                url_completo = urljoin(base_url, href_pulito)
                
                if url_completo not in gia_estratti and url_completo not in link_visti_in_questa_sessione:
                    trovati_pagina += 1
                    link_visti_in_questa_sessione.add(url_completo)
                    
                    raw_logo = (
                        img_tag.get("data-src")
                        or img_tag.get("data-original")
                        or img_tag.get("src")
                        or ""
                    )
                    logo_url = urljoin(base_url, raw_logo.lstrip("/")) if raw_logo and not raw_logo.startswith("data:") else ""
                    tvg_id = f"p{idx_pag}v{trovati_pagina}"
                    
                    nuovi_link_da_estrarre.append((url_completo, pagina, tvg_id, logo_url, gruppo_categoria))
                    
        print(f" -> Nuovi link trovati: {trovati_pagina}")
        if idx_pag < len(pagine_indice):
            time.sleep(random.uniform(2.0, 3.5))
    except Exception as e:
        print(f"Errore pagina indice {pagina}: {e}")

print(f"\nTotale nuovi link da analizzare: {len(nuovi_link_da_estrarre)}\n")

# FASE 2: Estrae il flusso .m3u8
nuovi_video = []
pattern_m3u8 = re.compile(r'["\'](https?://[^"\']+/hls/[^"\']+\.m3u8[^"\']*)["\']')
pattern_m3u8_fallback = re.compile(r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']')

def estrai_m3u8(html_text):
    m = pattern_m3u8.search(html_text)
    if m:
        return m.group(1)
    m2 = pattern_m3u8_fallback.search(html_text)
    if m2:
        return m2.group(1)
    return None

for url_video, pagina_origine, tvg_id, logo_url, gruppo_categoria in nuovi_link_da_estrarre:
    try:
        res = session.get(url_video, headers={"Referer": pagina_origine}, timeout=15)
        soup_video = BeautifulSoup(res.text, "html.parser")
        
        link_trovato = estrai_m3u8(res.text)
        
        if not link_trovato:
            tag_hls = soup_video.find("hlsjs-video", src=True)
            if tag_hls:
                link_trovato = tag_hls["src"]

        if link_trovato:
            titolo = soup_video.title.string.strip() if soup_video.title else "Video"
            titolo = " ".join(titolo.split()).replace(",", " -")
            
            if not logo_url:
                og_img = soup_video.find("meta", property="og:image")
                if og_img and og_img.get("content"):
                    logo_url = og_img["content"]
            
            nuovi_video.append((tvg_id, logo_url, gruppo_categoria, titolo, link_trovato))
            print(f"[OK] [{gruppo_categoria}] {tvg_id} | {titolo}")
            gia_estratti.add(url_video)
        else:
            titolo_err = soup_video.title.string.strip() if soup_video.title else "Nessun titolo"
            print(f"[NESSUN FLUSSO] {url_video} (Titolo: {titolo_err})")
            
        time.sleep(random.uniform(1.5, 2.5))
            
    except Exception as e:
        print(f"Errore su {url_video}: {e}")

# Aggiorna storico
with open(FILE_STORICO, "w", encoding="utf-8") as f:
    for url in sorted(gia_estratti):
        f.write(f"{url}\n")

# FASE 3: Accoda i nuovi video alla playlist con tutti gli attributi #EXTINF
if nuovi_video:
    playlist_esistente = os.path.exists(FILE_PLAYLIST)
    with open(FILE_PLAYLIST, "a", encoding="utf-8") as f:
        if not playlist_esistente:
            f.write("#EXTM3U\n")
        for tvg_id, logo_url, gruppo, titolo, flusso in nuovi_video:
            f.write(f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-logo="{logo_url}" group-title="{gruppo}",{titolo}\n')
            f.write(f"{flusso}\n")

print(f"\nFatto! Aggiunti {len(nuovi_video)} nuovi video a '{FILE_PLAYLIST}'.")
