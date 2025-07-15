import os
import time
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from common.utils import send_message_to_client

def sanitize_filename(filename):
    # Remplace les caractères non alphanumériques par des tirets
    return re.sub(r'[^a-zA-Z0-9_-]', '-', filename)

def download_article(socketio, app, driver, link, session_id, save_dir='downloads'):
    try:
        # Créer le répertoire s'il n'existe pas
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
        
        # Étape 1: Accéder au lien
        driver.get(link)
        send_message_to_client(socketio, app, "Lien chargé avec succès", session_id)
        
        # Attendre quelques secondes pour que le JavaScript se charge
        time.sleep(10)  # Attendre 5 secondes (ajustez si nécessaire)

        # Enregistrer la source HTML de la page
        page_source = driver.page_source
        sanitized_session_id = sanitize_filename(session_id)
        filename = os.path.join(save_dir, f"page_source_{sanitized_session_id}.html")
        with open(filename, "w", encoding="utf-8") as file:
            file.write(page_source)
        send_message_to_client(socketio, app, f"Source HTML enregistrée sous {filename}", session_id)
        
        # Étape 2: Vérifier la présence du div 'content'
        content_div = WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'div.content'))
        )
        send_message_to_client(socketio, app, "Div 'content' trouvé", session_id)
        
        # Étape 3: Obtenez le HTML du div
        html_content = content_div.get_attribute('outerHTML')
        send_message_to_client(socketio, app, "Contenu HTML récupéré avec succès", session_id)
        
        return html_content
    except Exception as e:
        send_message_to_client(socketio, app, f"Une erreur s'est produite lors du téléchargement : {e}", session_id)
        return None
