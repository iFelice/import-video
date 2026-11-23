import os
import re
import time
import random
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs

# 1. Inserisci qui gli URL esatti (copia dalla barra del browser anche per Pagina 2 e 3 della ricerca!)
pagine_indice = [
    "https://porn4days.pw/search/?s=carolina+guerrero",
    "https://porn4days.pw/search/page2/?s=carolina+guerrero",
    "https://porn4days.pw/search/page3/?s=carolina+guerrero",
]

FILE_STORICO = "storico_carolina_guerrero.txt"
FILE_PLAYLIST = "carolina_guerrero.m3u8"

def ricava_categoria_da_url(url):
    """Estrae la categoria dal percorso URL oppure dal parametro di ricerca ?s=..."""
    parsed = urlparse(url)
    parametri = parse_qs(parsed.query)
    
    # Se è una pagina di ricerca (?s=fred+flistones), usa la chiave di ricerca come gruppo
    if "s" in parametri and parametri["s"]:
        return parametri["s"].replace("+", " ").strip().title()
        
    percorso = parsed.path.strip("/")
    if not percorso:
        return "Home"
    parti = [p for p in percorso.split("/") if not re.match(r'^page[-_]?\d+$', p, re.IGNORECASE)]
    if not parti:
        return "Generale"
    return parti[-1].replace("-", " ").replace("_", " ").strip().title()

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

# FASE 1: Trova i link dalle anteprime
for idx_pag, pagina in enumerate(pagine_indice, start=1):
    try:
        parsed = urlparse(pagina)
        base_url = f"{parsed.scheme}://{parsed.netloc}/"
        gruppo_categoria = ricava_categoria_da_url(pagina)
        
        risposta = session.get(pagina, timeout=15)
        print(f"Controllo: {pagina} [Gruppo: {gruppo_categoria}] (HTTP: {risposta.status_code})")
        
        soup = BeautifulSoup(risposta.text, "html.parser")
        trovati_pagina = []
        
        for link in soup.find_all("a", href=True):
            img_tag = link.find("img")
            if img_tag:
                raw_logo = (
                    img_tag.get("data-src")
                    or img_tag.get("data-original")
                    or img_tag.get("src")
                    or ""
                )
                
                if "favicon" in raw_logo.lower() or "graphics/" in raw_logo.lower():
                    continue
                
                href_originale = link["href"].strip()
                # Se il link inizia con '../' usa urljoin con la pagina corrente per risalire correttamente,
                # altrimenti unisce direttamente al dominio principale (base_url)
                if href_originale.startswith(".."):
                    url_completo = urljoin(pagina, href_originale)
                else:
                    url_completo = urljoin(base_url, href_originale.lstrip("/"))
                
                if url_completo.rstrip("/") == base_url.rstrip("/"):
                    continue
                
                if url_completo not in gia_estratti and url_completo not in link_visti_in_questa_sessione:
                    link_visti_in_questa_sessione.add(url_completo)
                    trovati_pagina.append(url_completo)
                    
                    logo_url = urljoin(pagina, raw_logo) if raw_logo and not raw_logo.startswith("data:") else ""
                    tvg_id = f"p{idx_pag}v{len(trovati_pagina)}"
                    
                    nuovi_link_da_estrarre.append((url_completo, pagina, tvg_id, logo_url, gruppo_categoria))
                    
        print(f" -> Nuovi link trovati: {len(trovati_pagina)}")
        if trovati_pagina:
            print(f"    (Esempio URL costruito: {trovati_pagina})")
            
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

# FASE 3: Accoda i nuovi video alla playlist
if nuovi_video:
    playlist_esistente = os.path.exists(FILE_PLAYLIST)
    with open(FILE_PLAYLIST, "a", encoding="utf-8") as f:
        if not playlist_esistente:
            f.write("#EXTM3U\n")
        for tvg_id, logo_url, gruppo, titolo, flusso in nuovi_video:
            f.write(f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-logo="{logo_url}" group-title="{gruppo}",{titolo}\n')
            f.write(f"{flusso}\n")

print(f"\nFatto! Aggiunti {len(nuovi_video)} nuovi video a '{FILE_PLAYLIST}'.")
            f.write(f"{flusso}\n")

print(f"\nFatto! Aggiunti {len(nuovi_video)} nuovi video a '{FILE_PLAYLIST}'.")
