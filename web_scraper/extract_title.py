# web_scraper/extract_title.py

import requests
from bs4 import BeautifulSoup, SoupStrainer
import string
from collections import Counter
import re
from datetime import datetime
import time
from common.utils import send_message_to_client

def _try_google_fallback(url, browser):
    """Fallback : chercher l'URL sur Google pour récupérer le titre depuis les résultats"""
    try:
        # Nettoyer l'URL pour la recherche (enlever les paramètres de test ou de tracking)
        import urllib.parse
        parsed = urllib.parse.urlparse(url)
        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        
        print(f"Tentative de fallback Google pour l'URL : {clean_url}")
        search_url = f"https://www.google.com/search?q={urllib.parse.quote(clean_url)}"
        browser.get(search_url)
        
        # Attendre un peu pour le chargement
        time.sleep(4)
        
        # Gérer le bouton de consentement Google si présent
        try:
            # Sélecteurs variés pour le bouton d'acceptation
            consent_ids = ["L2AGLb", "introAgreeButton", "ack-button"]
            for cid in consent_ids:
                try:
                    btn = browser.find_element("id", cid)
                    if btn.is_displayed():
                        btn.click()
                        time.sleep(2)
                        break
                except: continue
                
            # Fallback par texte si les IDs échouent
            consent_texts = ["Tout accepter", "I agree", "Accepter tout", "Agree", "Tout approuver"]
            buttons = browser.find_elements("tag name", "button")
            for btn in buttons:
                if any(text in btn.text for text in consent_texts):
                    try:
                        btn.click()
                        time.sleep(2)
                        break
                    except: continue
        except Exception as e:
            print(f"Erreur lors de la gestion du consentement : {e}")

        # Chercher dans les résultats Google
        print(f"DEBUG Google Title: {browser.title}")
        if "Google" in browser.title and "Consent" in browser.title:
            print("AVERTISSEMENT: Toujours sur la page de consentement Google !")
            
        # 1. Résultats organiques standards (h3)
        results = browser.find_elements("tag name", "h3")
        print(f"DEBUG: Nombre de h3 trouvés: {len(results)}")
        for res in results:
            title_candidate = res.text.strip()
            print(f"DEBUG candidate h3: '{title_candidate}'")
            # On cherche un titre assez long et qui ne soit pas une catégorie Google
            if title_candidate and len(title_candidate) > 15:
                # Éviter les sections de service
                blacklist = ["vidéo", "recherches associées", "images", "actualités", "maps"]
                if not any(b in title_candidate.lower() for b in blacklist):
                    print(f"Titre récupéré via Google (h3) : {title_candidate}")
                    return title_candidate
        
        # 2. Section "À la une" (Top Stories)
        try:
            top_stories = browser.find_elements("css selector", "div[role='heading']")
            for story in top_stories:
                title_candidate = story.text.strip()
                if title_candidate and len(title_candidate) > 15:
                    print(f"Titre récupéré via Google (Top Stories) : {title_candidate}")
                    return title_candidate
        except: pass

        # 3. Fallback ultime : premier lien qui contient l'URL cible
        try:
            links = browser.find_elements("css selector", "div.g a")
            for link in links:
                href = link.get_attribute("href")
                if href and clean_url in href:
                    h3 = link.find_element("tag name", "h3")
                    if h3.text:
                        print(f"Titre récupéré via Google (link h3) : {h3.text}")
                        return h3.text.strip()
        except: pass

        print("Aucun titre trouvé sur Google Search")
        return None
    except Exception as e:
        print(f"Erreur lors du fallback Google : {e}")
        return None

def extract_title(url, browser=None, max_words=15):
    try:
        print(f"url : {url}")

        # Mesurer le temps de la requête
        start = time.time()

        title = None
        is_blocked = False

        # Si un browser est fourni, l'utiliser pour contourner les blocages
        if browser is not None:
            try:
                browser.get(url)
                # Attendre que la page charge et que le titre soit valide (pas la page anti-DDoS)
                max_wait = 15  # Augmenter à 15 secondes pour les sites lents
                wait_interval = 0.5  # Vérifier toutes les 0.5 secondes
                elapsed = 0

                while elapsed < max_wait:
                    time.sleep(wait_interval)
                    elapsed += wait_interval
                    current_title = browser.title
                    current_url = browser.current_url

                    if "test-google-fallback" in url:
                        print("FORCAGE DU BLOCAGE pour test google fallback")
                        is_blocked = True
                        break
                    time.sleep(wait_interval)
                    elapsed += wait_interval
                    current_title = browser.title
                    current_url = browser.current_url

                    # Si le titre est valide (pas vide, pas de pages de protection)
                    invalid_titles = ["Un instant…", "Just a moment", "Loading...", "Just a moment...",
                                    "Please wait...", "Checking your browser...", "Verifying...",
                                    "Cloudflare", "DDoS protection", "Security Check", "Access Denied"]
                    
                    # Pattern spécifique pour Libération quand on est bloqué
                    if "liberation.fr" in current_url.lower() and "bloqué" in current_title.lower():
                        print(f"Blocage Libération détecté par le titre : {current_title}")
                        is_blocked = True
                        break

                    if current_title and not any(invalid in current_title for invalid in invalid_titles):
                        title = current_title
                        print(f"Titre obtenu via browser en {time.time() - start:.2f} secondes")
                        break

                # Si le titre n'est toujours pas valide après l'attente, vérifier le body
                if not title and not is_blocked:
                    page_source = browser.page_source.lower()
                    bot_signals = ["cloudflare", "sucuri", "ddos protection", "captcha", "security check", "hcaptcha"]
                    if any(signal in page_source for signal in bot_signals):
                        print("Blocage bot détecté dans la source de la page")
                        is_blocked = True
                    
                    if not is_blocked:
                        print(f"Titre invalide obtenu après {max_wait}s : {browser.title}, passage à requests")
                        # Ne pas mettre browser à None ici car on pourrait en avoir besoin pour le fallback Google
                
            except Exception as e:
                print(f"Erreur avec browser : {e}")

        # Si bloqué par un bot, tenter le fallback Google Search si on a un browser
        if is_blocked and browser:
            print("Tentative de contournement via Google Search...")
            title = _try_google_fallback(url, browser)
        
        # Si pas encore de titre, tenter requests
        if not title:
            # On tente requests seulement si on n'a pas déjà détecté un blocage certain par browser
            # ou si on n'a pas de browser du tout
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            try:
                # Si on a déjà détecté un blocage browser, requests a peu de chances de réussir
                # mais on tente quand même au cas où (sauf si on est certain d'être bloqué)
                print("Tentative via requests...")
                response = requests.get(url, headers=headers, timeout=15)
                response.raise_for_status()

                # Parser uniquement le tag <title>
                soup = BeautifulSoup(response.text, 'html.parser', parse_only=SoupStrainer(["title", "meta"]))
                title_element = soup.find('title')

                if title_element:
                    title = title_element.text.strip()
            except Exception as e:
                print(f"Erreur requests : {e}")

            # Récupérer le nom du site si disponible
            site_name = None
            if title:
                try:
                    soup = BeautifulSoup(response.text, 'html.parser') if 'soup' not in locals() else soup
                    meta_site = soup.find('meta', attrs={'property': 'og:site_name'})
                    if meta_site and meta_site.get('content'):
                        site_name = meta_site.get('content').strip()
                except Exception:
                    site_name = None

        if not title:
            print("Aucun titre valide trouvé après toutes les tentatives")
            return None

        # Vérifier que le titre extrait semble légitime (pas trop court, pas de protection)
        if len(title.strip()) < 5:
            print(f"Titre trop court : '{title}', considéré comme invalide")
            # Tenter Google Fallback ici aussi car un titre trop court est souvent un signe de blocage/redirection
            if browser:
                print("Titre trop court, tentative de fallback Google...")
                title = _try_google_fallback(url, browser)
                if not title: return None
            else:
                return None

        # Vérifier si le titre est juste le nom du domaine
        from urllib.parse import urlparse
        import re
        parsed_url = urlparse(url)
        domain_parts = parsed_url.netloc.split('.')
        main_domain = domain_parts[-2] if len(domain_parts) >= 2 else domain_parts[0]
        
        title_clean = title.lower().strip()
        import unicodedata
        def strip_accents(s):
            return ''.join(c for c in unicodedata.normalize('NFD', s)
                          if unicodedata.category(c) != 'Mn')
        
        title_no_accents = strip_accents(title_clean)
        domain_no_accents = strip_accents(main_domain.lower())
        full_domain_no_accents = strip_accents(parsed_url.netloc.lower().replace('www.', ''))

        if (title_no_accents == domain_no_accents or 
            title_no_accents == full_domain_no_accents or
            title_no_accents == "accueil" or
            title_no_accents == "home"):
            print(f"Titre générique ou nom de domaine détecté : '{title}', probable blocage")
            # Une dernière chance via Google si on a un browser
            if browser:
                print("Titre générique détecté, tentative de fallback Google...")
                title = _try_google_fallback(url, browser)
                if not title: return None
            else:
                return None

        # Vérifier les patterns de protection Cloudflare courants
        cloudflare_patterns = [
            r'just a moment', r'checking your browser', r'please wait',
            r'verifying', r'security check', r'cloudflare', r'access denied'
        ]

        title_lower = title.lower()
        if any(pattern in title_lower for pattern in cloudflare_patterns):
            print(f"Titre indique une protection Cloudflare ou blocage : '{title}'")
            if browser:
                print("Blocage détecté via patterns, tentative de fallback Google...")
                title = _try_google_fallback(url, browser)
                if not title: return None
            else:
                return None

        # Traitement du titre pour créer la requête
        # 1) retirer les suffixes de type " - Le Parisien", " | Le Monde", etc.
        site_separators = [" - ", " | ", " — ", " · "]
        title_core = title
        for sep in site_separators:
            if sep in title_core:
                title_core = title_core.split(sep)[0]
        # 2) normaliser les apostrophes et guillemets typographiques
        title_core = (
            title_core
            .replace("’", "'")
            .replace("‘", "'")
            .replace("“", '"')
            .replace("”", '"')
        )
        # 3) supprimer la ponctuation (y compris les slashes)
        extra_punct = "…–—«»\"\"''/"
        punctuation_chars = string.punctuation + extra_punct
        title_no_punct = title_core.translate(str.maketrans(punctuation_chars, ' ' * len(punctuation_chars)))

        # Découper en mots
        words = title_no_punct.split()

        # Mots à retirer (noms de sites et stopwords FR)
        words_to_remove = {
            # médias / domaines
            "parisien", "leparisien", "leparisienfr", "leparisien.fr", "monde", "lemonde",
            "figaro", "lefigaro", "liberation", "libération", "mediapart", "telerama",
            "nouvelobs", "obs", "express", "lexpress", "france", "tv", "radio", "presse", "journal", "quotidien",
            "hebdo", "magazine", "news", "actu", "info", "actualite", "actualites",
            # stopwords FR courants
            "le", "la", "les", "du", "de", "des", "d", "au", "aux", "un", "une", "et",
            "ou", "sur", "dans", "par", "pour", "avec", "sans", "sous", "chez", "entre",
            "ce", "cet", "cette", "ces", "qui", "que", "quoi", "quel", "quelle", "quels",
            "quelles", "est", "sont", "fait", "faites", "faites", "fait", "aujourdhui",
            "ici", "lors", "contre", "ainsi", "comme", "plus", "moins", "très", "tres"
        }

        # Stopwords dynamiques à partir du domaine et du og:site_name
        try:
            from urllib.parse import urlparse
            host = urlparse(url).netloc.lower()
            host_parts = [p for p in re.split(r"[^a-zA-Z0-9]+", host) if p]
            # Ex: ['www','lexpress','fr'] -> add 'lexpress', 'express' (sans préfixes l/le/la)
            dynamic = set()
            for part in host_parts:
                dynamic.add(part)
                # variantes sans préfixe article
                if part.startswith('l') and len(part) > 1:
                    dynamic.add(part[1:])
                if part.startswith('le') and len(part) > 2:
                    dynamic.add(part[2:])
                if part.startswith('la') and len(part) > 2:
                    dynamic.add(part[2:])
            if site_name:
                # normaliser site_name -> tokens
                sn = re.sub(r'[^a-zA-Z0-9\s]', ' ', site_name.lower())
                for tok in sn.split():
                    if tok:
                        dynamic.add(tok)
                        if tok.startswith('l') and len(tok) > 1:
                            dynamic.add(tok[1:])
                        if tok.startswith('le') and len(tok) > 2:
                            dynamic.add(tok[2:])
                        if tok.startswith('la') and len(tok) > 2:
                            dynamic.add(tok[2:])
            # retirer éléments trop courts pour ne pas polluer
            dynamic = {d for d in dynamic if len(d) > 2}
            words_to_remove.update(dynamic)
        except Exception:
            pass

        # Filtrer les mots et nettoyer les caractères spéciaux
        filtered_words = []
        for word in words:
            # Nettoyer les caractères spéciaux et apostrophes
            clean_word = re.sub(r'[^\w\s]', '', word.lower())
            if clean_word and len(clean_word) > 2 and clean_word not in words_to_remove:
                filtered_words.append(clean_word)

        # Déduplication simple en conservant l'ordre
        seen = set()
        deduped_words = []
        for w in filtered_words:
            if w not in seen:
                seen.add(w)
                deduped_words.append(w)

        # Recomposer la chaîne filtrée (limiter à max_words mots significatifs)
        query = ' '.join(deduped_words[:max_words])

        # Nettoyer aussi le titre pour l'affichage (remplacer les slashes)
        clean_title = title.replace('/', ' ').replace('\\', ' ')
        # Nettoyer les espaces multiples
        clean_title = ' '.join(clean_title.split())

        return query, clean_title

    except Exception as e:
        print(f"Une erreur s'est produite lors de l'extraction du titre : {e}")
        return None
