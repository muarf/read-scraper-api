import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from common.utils import send_message_to_client

def login_to_europresse_bnf(driver, username, password, session_id):
    """
    Se connecte à Europresse en passant par le portail d'authentification CAS de la BnF.
    Le driver ressortira connecté sur la page d'accueil avec les bons cookies de session.
    """
    try:
        bnf_auth_url = "https://bnf.idm.oclc.org/login?url=https://nouveau.europresse.com/access/ip/default.aspx?un=D000067U_1"
        
        send_message_to_client("Chargement du portail BnF...", session_id)
        driver.get(bnf_auth_url)
        
        # Sur la page d'authentification BnF, on attend que le formulaire apparaisse
        send_message_to_client("Attente du formulaire de connexion BnF...", session_id)
        
        # La plupart des formulaires CAS ont un input text pour l'utilisateur et password
        username_field = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text'], input[id*='user'], input[name*='user']"))
        )
        password_field = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
        
        send_message_to_client("Champs trouvés, remplissage...", session_id)
        
        username_field.clear()
        username_field.send_keys(username)
        
        password_field.clear()
        password_field.send_keys(password)
        
        send_message_to_client("Soumission du formulaire BnF...", session_id)
        
        # Le bouton de soumission
        submit_button = driver.find_element(By.CSS_SELECTOR, "input[type='submit'], button[type='submit']")
        submit_button.click()
        
        # On attend d'être redirigé vers Europresse EZProxy
        send_message_to_client("Attente de la redirection vers Europresse...", session_id)
        
        # Vérifier si on a un message d'erreur (ex: Invalid credentials)
        time.sleep(2) # Laisser le temps à la page de recharger si erreur
        try:
            erreurs = driver.find_elements(By.CSS_SELECTOR, ".erreur")
            if erreurs and erreurs[0].is_displayed():
                send_message_to_client(f"Erreur d'identifiants BnF : {erreurs[0].text}", session_id)
                raise Exception(f"Identifiants invalides : {erreurs[0].text}")
        except Exception as err:
            if "Identifiants invalides" in str(err):
                raise err
            pass

        wait = WebDriverWait(driver, 30)
        
        # La redirection nous emmène sur nouveau-europresse-com.bnf.idm.oclc.org
        def on_europresse(driver):
            url = driver.current_url
            return "nouveau-europresse-com.bnf.idm.oclc.org" in url and "login" not in url.lower()

        wait.until(on_europresse)
        send_message_to_client("Connexion BnF réussie et redirection effectuée.", session_id)
        
        # Extraction des cookies pour pouvoir les réutiliser dans Requests
        cookies = driver.get_cookies()
        
        return driver, cookies

    except Exception as e:
        driver.save_screenshot('error_login_bnf.png')
        current_url = driver.current_url
        page_title = driver.title
        send_message_to_client(f"Erreur de connexion BnF : {e}", session_id)
        send_message_to_client(f"URL : {current_url} | Titre : {page_title}", session_id)
        return None, None
