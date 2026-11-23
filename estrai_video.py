import os
import re
import time
import random
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

# 1. Inserisci qui gli URL esatti delle pagine indice
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
    "https://porn4days.pw/newest/page10/",
    "https://porn4days.pw/newest/page11/",
    "https://porn4days.pw/newest/page12/",
    "https://porn4days.pw/newest/page13/",
]

FILE_STORICO = "storico_estratti.txt"
FILE_PLAYLIST = "playlist.m3u"

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

# FASE 1: Trova i link dalle anteprime usando sempre il dominio principale come base
for i, pagina in enumerate(pagine_indice):
    try:
        # Ricava la radice del sito (es. "https://sitoesempio.com")
        parsed = urlparse(pagina)
        base_url = f"{parsed.scheme}://{parsed.netloc}/"
        
        risposta = session.get(pagina, timeout=15)
        print(f"Controllo: {pagina} (Stato HTTP: {risposta.status_code})")
        
        soup = BeautifulSoup(risposta.text, "html.parser")
        trovati_pagina = []
        
        for link in soup.find_all("a", href=True):
            if link.find("img"):
                href_pulito = link["href"].lstrip("/")
                # Unisce sempre al dominio principale (evita di attaccare "/newest/page2/")
                url_completo = urljoin(base_url, href_pulito)
                
                if url_completo not in gia_estratti and url_completo not in link_visti_in_questa_sessione:
                    nuovi_link_da_estrarre.append((url_completo, pagina))
                    link_visti_in_questa_sessione.add(url_completo)
                    trovati_pagina.append(url_completo)
                    
        print(f" -> Nuovi link trovati: {len(trovati_pagina)}")
        if trovati_pagina:
            print(f"    (Esempio link pulito: {trovati_pagina})")
            
        if i < len(pagine_indice) - 1:
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

for url_video, pagina_origine in nuovi_link_da_estrarre:
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
            titolo = " ".join(titolo.split())
            nuovi_video.append((titolo, link_trovato))
            print(f"[OK] {titolo}")
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
        for titolo, flusso in nuovi_video:
            f.write(f"#EXTINF:-1,{titolo}\n")
            f.write(f"{flusso}\n")

print(f"\nFatto! Aggiunti {len(nuovi_video)} nuovi video a '{FILE_PLAYLIST}'.")
