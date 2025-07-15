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
        keyword_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//input[@id='password']"))
        )
        username_field = driver.find_element("id", "username")
        password_field = driver.find_element("id", "password")

        send_message_to_client(socketio, app,f"Remplissage du nom d'utilisateur", session_id)
        username_field.send_keys(username)

        send_message_to_client(socketio, app,"Remplissage du mot de passe...", session_id)
        password_field.send_keys(password)

        # Soumettre le formulaire
        send_message_to_client(socketio, app,"Soumission du formulaire de connexion...", session_id)
        password_field.send_keys(Keys.RETURN)

        # Attendre un certain temps pour que la page de redirection se charge
        wait = WebDriverWait(driver, 10)
        button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button.v-step__button-skip')))

        # Cliquer sur le bouton
        button.click()
        send_message_to_client(socketio, app,"onclique sur le bouton annué", session_id)

        # Retourner l'instance du navigateur pour une utilisation ultérieure
        send_message_to_client(socketio, app,"Connexion réussie.", session_id)
        return driver

    except Exception as e:
        driver.save_screenshot('ss.png')
        send_message_to_client(socketio, app,f"Une erreur s'est produite lors de la connexion : {e}", session_id)
        return None
