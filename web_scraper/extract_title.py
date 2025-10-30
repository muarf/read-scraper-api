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
            response = requests.get(url, headers=headers, timeout=5)
            response.raise_for_status()

            print(f"Réponse obtenue via requests en {time.time() - start:.2f} secondes")

            # Parser uniquement le tag <title>
            soup = BeautifulSoup(response.text, 'html.parser', parse_only=SoupStrainer("title"))
            title_element = soup.find('title')

            if title_element:
                title = title_element.text.strip()
            else:
                return None

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
        # Liste de ponctuation étendue
        extra_punct = "…–—«»\"\"''"
        punctuation_chars = string.punctuation + extra_punct
        # Remplacer les ponctuations par des espaces
        title_no_punct = title.translate(str.maketrans(punctuation_chars, ' ' * len(punctuation_chars)))

        # Découper en mots
        words = title_no_punct.split()

        # Mots à retirer
        words_to_remove = {"libération", "mediapart", "et", "ou", "sauf"}
        filtered_words = [word for word in words if word.lower() not in words_to_remove]

        # Recomposer la chaîne filtrée
        query = ' '.join(filtered_words[:max_words])

        return query, title

    except Exception as e:
        print(f"Une erreur s'est produite lors de l'extraction du titre : {e}")
        return None
