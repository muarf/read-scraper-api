# web_scraper/extract_title.py

import requests
from bs4 import BeautifulSoup, SoupStrainer
import string
from collections import Counter
import re
from datetime import datetime
from common.utils import send_message_to_client

def extract_title(url, max_words=15):
    try:
        print(f"url : {url}")

        headers = {
            'User-Agent': 'Mozilla/5.0'
        }

        # Mesurer le temps de la requête
        import time
        start = time.time()

        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()

        print(f"Réponse obtenue en {time.time() - start:.2f} secondes")

        # Parser uniquement le tag <title>
        soup = BeautifulSoup(response.text, 'html.parser', parse_only=SoupStrainer("title"))
        title_element = soup.find('title')

        if title_element:
            title = title_element.text.strip()

            # Liste de ponctuation étendue
            punctuation_chars = string.punctuation + '…–—«»“”‘’'
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
        else:
            return None

    except Exception as e:
        print(f"Une erreur s'est produite lors de l'extraction du titre : {e}")
        return None
