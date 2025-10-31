# web_scraper/extract_title.py

import requests
from bs4 import BeautifulSoup, SoupStrainer
import string
from collections import Counter
import re
from datetime import datetime
from common.utils import send_message_to_client

def extract_title(url, browser=None, max_words=15):
    try:
        print(f"url : {url}")

        # Mesurer le temps de la requête
        import time
        start = time.time()

        title = None

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

                    # Si le titre est valide (pas vide, pas de pages de protection)
                    invalid_titles = ["Un instant…", "Just a moment", "Loading...", "Just a moment...",
                                    "Please wait...", "Checking your browser...", "Verifying...",
                                    "Cloudflare", "DDoS protection", "Security Check"]

                    if current_title and not any(invalid in current_title for invalid in invalid_titles):
                        title = current_title
                        print(f"Titre obtenu via browser en {time.time() - start:.2f} secondes")
                        break

                # Si le titre n'est toujours pas valide après l'attente, passer à requests
                if not title:
                    print(f"Titre invalide obtenu après {max_wait}s : {browser.title}, passage à requests")
                    browser = None

            except Exception as e:
                print(f"Erreur avec browser, retour à requests : {e}")
                browser = None
        
        # Si pas de browser ou si le browser a échoué, utiliser requests
        if browser is None or not title:
            headers = {
                'User-Agent': 'Mozilla/5.0'
            }
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()

            print(f"Réponse obtenue via requests en {time.time() - start:.2f} secondes")

            # Parser uniquement le tag <title>
            soup = BeautifulSoup(response.text, 'html.parser', parse_only=SoupStrainer(["title", "meta"]))
            title_element = soup.find('title')

            if title_element:
                title = title_element.text.strip()
            else:
                return None

            # Récupérer le nom du site si disponible (og:site_name) pour l'exclure ensuite
            site_name = None
            try:
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
            return None

        # Vérifier les patterns de protection Cloudflare courants
        cloudflare_patterns = [
            r'just a moment', r'checking your browser', r'please wait',
            r'verifying', r'security check', r'cloudflare'
        ]

        title_lower = title.lower()
        if any(pattern in title_lower for pattern in cloudflare_patterns):
            print(f"Titre indique une protection Cloudflare : '{title}'")
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
        # 3) supprimer la ponctuation
        extra_punct = "…–—«»\"\"''"
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

        return query, title

    except Exception as e:
        print(f"Une erreur s'est produite lors de l'extraction du titre : {e}")
        return None
