# web_scraper/extract_title.py

import requests
from bs4 import BeautifulSoup, SoupStrainer
import string
import re
from datetime import datetime
import time
import unicodedata
from common.utils import send_message_to_client
from web_scraper.ophirofox_bridge import OphirofoxEngine

# Initialisation globale du moteur Ophirofox
ophirofox = OphirofoxEngine(op_dir="/app/web_scraper/ophirofox/ophirofox")

def _process_title_to_query(title, max_words=15):
    """Nettoyage de titre pour Europresse et génération de query"""
    if not title:
        return None, None
    
    # 1) retirer les suffixes de type " - Le Parisien", " | Le Monde", etc.
    site_separators = [" - ", " | ", " — ", " · "]
    title_core = title
    for sep in site_separators:
        if sep in title_core:
            title_core = title_core.split(sep)[0]
    
    # 2) normaliser
    title_core = title_core.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    
    # 3) supprimer la ponctuation
    extra_punct = "…–—«»\"\"''/"
    punctuation_chars = string.punctuation + extra_punct
    title_no_punct = title_core.translate(str.maketrans(punctuation_chars, ' ' * len(punctuation_chars)))

    # Découper en mots
    words = title_no_punct.split()
    words_to_remove = {
        "parisien", "leparisien", "leparisienfr", "leparisien.fr", "monde", "lemonde",
        "figaro", "lefigaro", "liberation", "libération", "mediapart", "telerama",
        "nouvelobs", "obs", "express", "lexpress", "france", "tv", "radio", "presse", "journal", "quotidien",
        "hebdo", "magazine", "news", "actu", "info", "actualite", "actualites", "video", "videos", "direct",
        "continu", "ouest", "regions", "monde", "monde.fr", "le", "la", "les", "du", "de", "des", "d", "au", "aux", 
        "un", "une", "et", "en", "pour", "dans", "sur", "par", "est", "sont", "avec", "dans", "votre", "suivez", "toute"
    }

    # Filtrer les mots
    filtered_words = []
    seen = set()
    for word in words:
        clean_word = re.sub(r'[^\w\s]', '', word.lower())
        if clean_word and len(clean_word) > 2 and clean_word not in words_to_remove:
            if clean_word not in seen:
                seen.add(clean_word)
                filtered_words.append(clean_word)

    # Protection spécifique contre le slogan Ouest-France (si moins de 3 mots significatifs après filtrage)
    if not filtered_words or len(filtered_words) < 2:
        return None, None

    query = ' '.join(filtered_words[:max_words])
    clean_title = ' '.join(title.replace('/', ' ').replace('\\', ' ').split())
    return query, clean_title

def _extract_from_slug(url):
    """Extraction depuis le slug de l'URL avec nettoyage agressif des IDs techniques"""
    try:
        from urllib.parse import urlparse
        path = urlparse(url).path
        if not path or path == '/': return None
        
        # Récupérer le dernier segment (ex: israel-et-iran_6668678_3210.html)
        slug = path.split('/')[-1] or path.split('/')[-2]
        
        # 1. Supprimer l'extension .html ou .htm
        slug = re.sub(r'\.html?$', '', slug)
        
        # 2. Remplacer les séparateurs par des espaces
        title = slug.replace('-', ' ').replace('_', ' ')
        
        # 3. Supprimer les IDs techniques (suites de chiffres ou code alphanumérique long à la fin)
        # On le fait plusieurs fois car il peut y en avoir plusieurs (ex: _6668678_3210)
        title = re.sub(r'\s+[a-zA-Z0-9]{8,}\s*$', '', title)
        for _ in range(3):
            title = re.sub(r'\s+\d{2,}\s*$', '', title).strip()
            
        return title
    except: return None

def _try_google_fallback(url, browser):
    """Extraction via Google Search"""
    try:
        import urllib.parse
        search_url = f"https://www.google.com/search?q={urllib.parse.quote(url)}"
        browser.get(search_url)
        time.sleep(4)
        results = browser.find_elements("tag name", "h3")
        for res in results:
            t = res.text.strip()
            if t and len(t) > 15: return t
        return None
    except: return None

def extract_metadata(url, browser=None, max_words=15):
    """
    Extraction de métadonnées prioritaires.
    STRATÉGIE 1 : Ophirofox (Injection JS + Bypass Cookie Wall)
    STRATÉGIE 2 : Fallback classique (Browser Title / Search Engine)
    STRATÉGIE 3 : Slug URL (Dernier recours)
    """
    query = None
    title = None
    published_date = None

    # STRATÉGIE 1 : Ophirofox (Prioritaire comme demandé)
    if browser is not None:
        try:
            print(f"[OPHIROFOX] Tentative d'extraction pour {url}")
            js_code = ophirofox.get_js_injection(url)
            
            if js_code:
                if browser.current_url != url:
                    browser.get(url)
                
                # Attendre et injecter (bypass cookie wall inclus dans le bridge)
                time.sleep(3)
                browser.execute_script(js_code)
                
                # Boucle de capture (max 7s pour laisser le temps au bypass d'agir)
                start_wait = time.time()
                while time.time() - start_wait < 7:
                    results = browser.execute_script("return window.ophirofox_results;")
                    if results:
                        query_raw = results.get('keywords')
                        published_date = results.get('published_time')
                        
                        if query_raw:
                            # Rejeter si c'est encore un slogan marketing d'Ouest-France ou assimilé
                            blacklist = ["direct", "continu", "cookies", "accueil", "home", "instantané", "désolé"]
                            if any(b in query_raw.lower() for b in blacklist) or len(query_raw) < 15:
                                print(f"[OPHIROFOX] Résultat suspect, on continue d'attendre...")
                                time.sleep(1)
                                continue
                                
                            query, title = _process_title_to_query(query_raw, max_words)
                            print(f"[OPHIROFOX] Succès : Title='{title}'")
                            return query, title, published_date
                    time.sleep(0.5)
                
                print("[OPHIROFOX] Pas de résultats valides capturés via JS")
        except Exception as e:
            print(f"[OPHIROFOX] Erreur bridge : {e}")

    # STRATÉGIE 2 : Fallback Classique (Browser Title & Recherche)
    res = extract_title(url, browser, max_words)
    if res:
        f_query, f_title = res
        # Liste noire étendue pour détecter les paywalls
        paywall_blacklist = [
            "accès restreint", "abonnez-vous", "paywall", "désolé", "restreint", 
            "connexion", "s'inscrire", "offre", "abonnement", "s'abonner"
        ]
        
        # Si le titre contient un mot de la blacklist, on le rejette
        is_paywall = f_title is not None and any(word in f_title.lower() for word in paywall_blacklist)
        
        if f_query and len(f_query.split()) >= 2 and not is_paywall:
            return f_query, f_title, None
        print(f"[METADATA] Fallback a renvoyé un titre suspect ou paywall ('{f_title}'), rejeté.")
    
    # STRATÉGIE 3 : Slug URL (Vraiment le dernier recours, mais très efficace sur Le Monde)
    print("[METADATA] Tentative ultime via le slug de l'URL...")
    slug_title = _extract_from_slug(url)
    if slug_title and len(slug_title) > 10:
        query, title = _process_title_to_query(slug_title, max_words)
        print(f"[METADATA] Titre reconstruit depuis l'URL : '{title}'")
        return query, title, None

    return None, None, None

def extract_title(url, browser=None, max_words=15):
    """Méthode de secours classique"""
    try:
        title = None
        if browser is not None:
            browser.get(url)
            # Attente d'un titre qui ne ressemble pas à un slogan marketing
            for _ in range(10):
                time.sleep(1)
                t = browser.title
                if t and len(t) > 20 and not any(m in t.lower() for m in ["direct", "continu", "accueil"]):
                    title = t
                    break
            
            if not title:
                title = _try_google_fallback(url, browser)

        if not title:
            try:
                headers = {'User-Agent': 'Mozilla/5.0'}
                r = requests.get(url, headers=headers, timeout=10)
                soup = BeautifulSoup(r.text, 'html.parser')
                if soup.title: title = soup.title.text.strip()
            except: pass

        if title:
            return _process_title_to_query(title, max_words)
        return None
    except: return None
