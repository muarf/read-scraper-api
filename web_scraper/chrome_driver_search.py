# web_scraper/chrome_driver_search.py
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import TimeoutException
from common.utils import send_message_to_client
import time
def calculate_similarity(query, title):
    # Diviser les chaînes en ensembles de mots
    set_query = set(query.split())
    set_title = set(title.split())

    # Calculer l'intersection des ensembles de mots
    intersection = set_query.intersection(set_title)

    # Calculer la similarité en pourcentage
    similarity_percentage = round(len(intersection) / len(set_query.union(set_title)) * 100)

    return similarity_percentage
def handle_error(driver, socketio, app, session_id, message, exception=None):
    driver.save_screenshot("ss.png")
    with open("page_source.html", "w", encoding="utf-8") as f:
        f.write(driver.page_source)
    if exception:
        print(f"[ERREUR] {message} : {exception}")
    else:
        print(f"[ERREUR] {message}")
    send_message_to_client(socketio, app, message, session_id)

def search_target_site(socketio, app, driver, query, title,session_id):
    try:
        driver.get("https://read.tagaday.fr/search")
        # Charger la page de recherche

        send_message_to_client(socketio, app,"Chargement de la page de recherche...",session_id)
                
        try:
            keyword_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//textarea[@placeholder='Entrer votre recherche']"))
            )
        except TimeoutException as e:
            handle_error(driver, socketio, app, session_id, "Champ de recherche non trouvé sur la page", e)
            return None
        # Remplir le champ de mots clés
        send_message_to_client(socketio, app,f"Recherche avec le mot clé : {query}",session_id)
        keyword_field.clear()
        keyword_field.send_keys(query)
        
        # Sélectionner la date de début
        try:
            date_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((
                    By.XPATH, '//label[text()="Du"]/following::input[@class="v-field__input"]'
                ))
            )
            date_input.clear()
            date_input.send_keys(Keys.BACKSPACE * 10)
            date_input.send_keys("01/01/1970")
        except TimeoutException as e:
            handle_error(driver, socketio, app, session_id, "Champ de date 'Du' non trouvé", e)
            return None


        send_message_to_client(socketio, app,"Attente que le bouton ne soit pas désactivé...",session_id)
        wait = WebDriverWait(driver, 10)
        submit_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@data-qa-itemtype='btnSubmitSearch']")))

        # Soumettre le formulaire
        send_message_to_client(socketio, app,"Soumission du formulaire de recherche...", session_id)
        submit_button.click()
        # Attendre un certain temps pour que les résultats de la recherche se chargent
        try:
            # Attendre un certain temps pour que les résultats de la recherche se chargent
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, 'v-virtual-scroll__item'))
            )

            # Récupérer tous les éléments de la liste des résultats
            results = driver.find_elements(By.CLASS_NAME, 'v-virtual-scroll__item')
            max_iterations = 10
            result_data = []
            collected_results = 0
            while collected_results < max_iterations:
                if len(results) == 0:
                    print("Moins de résultats que prévu. Terminant la boucle.")
                    break
                for result in results:
                    # Extraire les informations de chaque élément de la liste
                    link_element = result.find_element(By.CSS_SELECTOR, 'div[data-qa-itemtype="docTitle"] a')
                    lien_element = link_element.get_attribute('href')
                    logo_label = result.find_element(By.CSS_SELECTOR, '[data-qa-itemtype="docLogo"] [aria-label]').get_attribute('aria-label')
                    doc_title = result.find_element(By.CSS_SELECTOR, '[data-qa-itemtype="docTitle"]').text
                    formatted_date= result.find_element(By.CSS_SELECTOR, '[data-qa-itemtype="docDate"]').text
                    doc_date = formatted_date[:10]

                    similarity_percentage = calculate_similarity(title, doc_title)
                    print("Logo Title:", logo_label)
                    print("Doc Title:", doc_title)
                    print("Doc Date:", doc_date)
                    print("Similarité:", similarity_percentage)
                    print("-" * 50)
                    if logo_label != "Twitter":
                        result_data.append({
                            'link': lien_element,
                            'logo': logo_label,
                            'title': doc_title,
                            'date': doc_date,
                            'percentage': similarity_percentage
                        })
                        collected_results += 1

                    if collected_results >= max_iterations:
                        break

            # Tri des résultats par pourcentage de similarité
            result_data_sorted = sorted(result_data, key=lambda x: x['percentage'], reverse=True)

        except TimeoutException:
            # Si l'élément v-virtual-scroll__item n'est pas présent, vérifier si l'élément no_result_element est présent
            no_result_element = driver.find_elements(By.XPATH, "//div[@data-qa-itemtype='searchResultEmpty']")
            if no_result_element:
                driver.save_screenshot('ss.png')
                send_message_to_client(socketio, app, "Aucun résultat trouvé pour la requête",session_id)
                result_data_sorted = {'msg': 'Aucun résultat trouvé pour la requête'}
            else:
                driver.save_screenshot('ss.png')
                send_message_to_client(socketio, app, "Erreur lors du chargement des résultats de recherche.", session_id)
                result_data_sorted = None


            # Retourner l'instance du navigateur pour une utilisation ultérieure
        send_message_to_client(socketio, app,"Recherche terminée avec succès.",session_id)
        return driver, result_data_sorted

    except Exception as e:
        driver.save_screenshot('ss.png')
        with open("page_source.html", "w", encoding="utf-8") as file:
            file.write(driver.page_source)
        send_message_to_client(socketio, app,f"Une erreur s'est produite lors de la recherche : {e}", session_id)
        return None
