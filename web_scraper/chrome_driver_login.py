# web_scraper/chrome_driver_login.py
from selenium.webdriver.common.keys import Keys
import time
from selenium.webdriver.support.ui import WebDriverWait 
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

from common.utils import send_message_to_client

def login_to_target_site(socketio, app, driver, username, password, session_id):
    try:
        # Charger la page de connexion
        send_message_to_client(socketio, app,"Chargement de la page de connexion...", session_id)
        driver.get("https://read.tagaday.fr")
        #for cookie in example_cookies:
            #driver.add_cookie(cookie)
        # Remplir le formulaire de connexion
        send_message_to_client(socketio, app,"Attente du champ password...", session_id)
        keyword_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//input[@id='password']"))
        )
        send_message_to_client(socketio, app,"Champ password trouvé, recherche username...", session_id)
        username_field = driver.find_element("id", "username")
        send_message_to_client(socketio, app,"Champ username trouvé, récupération password...", session_id)
        password_field = driver.find_element("id", "password")
        send_message_to_client(socketio, app,"Tous les champs trouvés", session_id)

        send_message_to_client(socketio, app,f"Remplissage du nom d'utilisateur", session_id)
        username_field.send_keys(username)

        send_message_to_client(socketio, app,"Remplissage du mot de passe...", session_id)
        password_field.send_keys(password)

        # Soumettre le formulaire
        send_message_to_client(socketio, app,"Soumission du formulaire de connexion...", session_id)
        password_field.send_keys(Keys.RETURN)

        # Attendre que l'URL change pour confirmer la connexion réussie
        send_message_to_client(socketio, app,"Attente de la redirection...", session_id)
        wait = WebDriverWait(driver, 10)
        
        # Attendre soit qu'on soit sur /search soit sur la page d'accueil
        def url_contains(driver, patterns):
            current_url = driver.current_url
            return any(pattern in current_url for pattern in patterns)
        
        wait.until(lambda driver: url_contains(driver, ['/search', 'read.tagaday.fr']) and 'sso.aday.fr' not in driver.current_url)
        send_message_to_client(socketio, app,"Redirection réussie", session_id)

        # Retourner l'instance du navigateur pour une utilisation ultérieure
        send_message_to_client(socketio, app,"Connexion réussie.", session_id)
        return driver

    except Exception as e:
        driver.save_screenshot('ss.png')
        current_url = driver.current_url
        page_title = driver.title
        send_message_to_client(socketio, app,f"Erreur lors de la connexion : {e}", session_id)
        send_message_to_client(socketio, app,f"URL actuelle : {current_url}", session_id)
        send_message_to_client(socketio, app,f"Titre de la page : {page_title}", session_id)
        send_message_to_client(socketio, app,f"Screenshot sauvegardé : ss.png", session_id)
        return None
