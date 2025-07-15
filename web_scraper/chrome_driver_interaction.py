# web_scraper/chrome_driver_search.py
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select

import time

def search_target_site(driver, query, start_date=None, end_date=None):
    try:
        # Charger la page de recherche
        print("Chargement de la page de recherche...")
        wait = WebDriverWait(driver, 10)
        button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button.v-step__button-skip')))

        # Cliquer sur le bouton
        button.click()
        print("onclique sur le bouton annué")
        keyword_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//textarea[@data-qa-itemtype='searchQueryInput']"))
        )

        # Remplir le champ de mots clés
        print(f"Recherche avec le mot clé : {query}")
        keyword_field.clear()
        keyword_field.send_keys(query)
        
        # Sélectionner la date de début
        input_element = driver.find_element(By.CSS_SELECTOR, 'input[data-qa-itemtype="searchQueryStartInput"]')

        # Effacer le contenu actuel de l'input (au cas où il y aurait déjà quelque chose)
        input_element.clear()
        input_element.send_keys(Keys.BACKSPACE * 10)
        # Entrer la date dans l'input
        input_element.send_keys("01/01/1970")
        time.sleep(1)
        
     # Soumettre le formulaire
        print("Soumission du formulaire de recherche...")
        submit_button = driver.find_element(By.XPATH, "//button[@data-qa-itemtype='btnSubmitSearch']")
        submit_button.click()
         # Attendre un certain temps pour que les résultats de la recherche se chargent
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, 'v-virtual-scroll__item'))
        )
        # Récupérer tous les éléments de la liste des résultats
        results = driver.find_elements(By.CLASS_NAME, 'v-virtual-scroll__item')
        result_data = []
        for result in results:
             # Extraire les informations de chaque élément de la liste
            logo_label = result.find_element(By.CSS_SELECTOR, '[data-qa-itemtype="docLogo"] [aria-label]').get_attribute('aria-label')
            doc_title = result.find_element(By.CSS_SELECTOR, '[data-qa-itemtype="docTitle"]').text
            doc_date = result.find_element(By.CSS_SELECTOR, '[data-qa-itemtype="docDate"]').text
                 # Imprimer les informations ou les renvoyer à server.py
            print("Logo Title:", logo_label)
            print("Doc Title:", doc_title)
            print("Doc Date:", doc_date)
            print("-" * 50)
            result_data.append({
                 'logo': logo_label,
                 'title': doc_title,
                 'date': doc_date
            })

        # Retourner l'instance du navigateur pour une utilisation ultérieure
        print("Recherche terminée avec succès.")
        return driver, result_data

    except Exception as e:
        print(f"Une erreur s'est produite lors de la recherche : {e}")
        return None
