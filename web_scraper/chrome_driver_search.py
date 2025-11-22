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
        # Nettoyer les termes de recherche pour éviter les erreurs d'encodage
        clean_query = query.encode('utf-8', errors='replace').decode('utf-8')

        # Remplir le champ de mots clés
        send_message_to_client(socketio, app,f"Recherche avec le mot clé : {clean_query}",session_id)
        print(f"SAISIE DES TERMES DE RECHERCHE: '{clean_query}'")
        keyword_field.clear()
        keyword_field.send_keys(clean_query)

        # Attendre un peu pour que les termes soient visibles
        time.sleep(1)

        # Screenshot après saisie des termes
        try:
            after_input_screenshot = f"/root/read-scraper-api/static/debug_after_input_{session_id}_{int(time.time())}.png"
            driver.save_screenshot(after_input_screenshot)
            print(f"Screenshot après saisie des termes: {after_input_screenshot}")
        except Exception as ss_error:
            print(f"Impossible de prendre screenshot après saisie: {ss_error}")
        
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
        driver.execute_script("arguments[0].click();", submit_button)
        
        # Attendre que les résultats de la recherche se chargent
        try:
            send_message_to_client(socketio, app,"Attente du chargement des résultats...", session_id)
            
            # Attendre que les placeholders disparaissent (skeleton loaders)
            # Les placeholders ont généralement des classes comme 'v-skeleton-loader' ou sont des divs gris
            wait = WebDriverWait(driver, 30)  # Augmenter le timeout à 30 secondes
            
            # Attendre que les résultats réels apparaissent (pas juste les placeholders)
            # On vérifie que les éléments ont du contenu réel (titre, logo, etc.)
            class ResultsLoaded:
                """Classe callable pour vérifier que les résultats sont réellement chargés"""
                def __call__(self, driver):
                    try:
                        # Chercher les éléments de résultats
                        result_items = driver.find_elements(By.CLASS_NAME, 'v-virtual-scroll__item')
                        if len(result_items) == 0:
                            return False
                        
                        # Vérifier que le premier résultat a du contenu réel (titre, logo)
                        # Les placeholders n'ont généralement pas ces attributs data-qa
                        for item in result_items[:3]:  # Vérifier les 3 premiers
                            try:
                                # Si on peut trouver un titre avec data-qa-itemtype, c'est un vrai résultat
                                title_elem = item.find_element(By.CSS_SELECTOR, '[data-qa-itemtype="docTitle"]')
                                if title_elem and title_elem.text.strip():
                                    # Vérifier aussi qu'il n'est pas vide ou juste des espaces
                                    if len(title_elem.text.strip()) > 5:  # Au moins 5 caractères
                                        return True
                            except:
                                continue
                        
                        return False
                    except:
                        return False
            
            # Attendre que les résultats soient chargés
            wait.until(ResultsLoaded())
            
            # Attendre un peu plus pour que tous les résultats se chargent
            # Augmenter le délai pour s'assurer que tout est chargé
            time.sleep(3)
            
            # Vérifier une deuxième fois que les résultats sont toujours là
            # (parfois les résultats peuvent disparaître temporairement)
            results_check = driver.find_elements(By.CLASS_NAME, 'v-virtual-scroll__item')
            if len(results_check) == 0:
                # Attendre encore un peu si aucun résultat n'est trouvé
                time.sleep(2)
                wait.until(ResultsLoaded())
            
            # Screenshot après chargement des résultats pour debug
            try:
                after_results_screenshot = f"/root/read-scraper-api/static/debug_after_results_{session_id}_{int(time.time())}.png"
                driver.save_screenshot(after_results_screenshot)
                print(f"Screenshot après chargement des résultats: {after_results_screenshot}")
            except Exception as ss_error:
                print(f"Impossible de prendre screenshot après résultats: {ss_error}")
            
            send_message_to_client(socketio, app,"Résultats chargés, extraction en cours...", session_id)

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

                    # Extraire la longueur de l'article (nombre de mots)
                    try:
                        length_element = result.find_element(By.CSS_SELECTOR, '[data-qa-itemtype="docWordCount"]')
                        length_text = length_element.text
                        # Extraire le nombre de mots (ex: "305 mots" -> 305, "1 063 mots" -> 1063)
                        # Utiliser une regex pour extraire tous les chiffres
                        import re
                        numbers = re.findall(r'\d+', length_text.replace(' ', ''))
                        doc_length = int(numbers[0]) if numbers else 0
                    except Exception as e:
                        print(f"Erreur extraction longueur: {e}, texte: '{length_text}'")
                        # Si la longueur n'est pas disponible, estimer d'après le titre
                        doc_length = len(doc_title.split()) * 10  # Estimation approximative

                    similarity_percentage = calculate_similarity(title, doc_title)

                    # Gestion sécurisée des caractères Unicode pour l'affichage
                    safe_logo = logo_label.encode('utf-8', errors='replace').decode('utf-8')
                    safe_title = doc_title.encode('utf-8', errors='replace').decode('utf-8')

                    print("Logo Title:", safe_logo)
                    print("Doc Title:", safe_title)
                    print("Doc Date:", doc_date)
                    print("Longueur:", doc_length, "mots")
                    print("Similarité:", similarity_percentage)
                    print("-" * 50)
                    if logo_label != "Twitter":
                        result_data.append({
                            'link': lien_element,
                            'logo': logo_label,
                            'title': doc_title,
                            'date': doc_date,
                            'percentage': similarity_percentage,
                            'length': doc_length
                        })
                        collected_results += 1

                    if collected_results >= max_iterations:
                        break

            # Tri des résultats par pourcentage de similarité
            result_data_sorted = sorted(result_data, key=lambda x: x['percentage'], reverse=True)

        except TimeoutException as timeout_error:
            # Screenshot pour debug en cas de timeout
            try:
                timeout_screenshot = f"/root/read-scraper-api/static/debug_timeout_{session_id}_{int(time.time())}.png"
                driver.save_screenshot(timeout_screenshot)
                print(f"Screenshot en cas de timeout: {timeout_screenshot}")
            except Exception as ss_error:
                print(f"Impossible de prendre screenshot timeout: {ss_error}")
            
            # Si l'élément v-virtual-scroll__item n'est pas présent, vérifier si l'élément no_result_element est présent
            no_result_element = driver.find_elements(By.XPATH, "//div[@data-qa-itemtype='searchResultEmpty']")
            if no_result_element:
                send_message_to_client(socketio, app, "Aucun résultat trouvé pour la requête",session_id)
                result_data_sorted = []  # Retourner une liste vide au lieu d'un dict
            else:
                # Vérifier si on a encore des placeholders (page pas finie de charger)
                placeholder_items = driver.find_elements(By.CLASS_NAME, 'v-virtual-scroll__item')
                has_real_content = False
                for item in placeholder_items[:3]:
                    try:
                        title_elem = item.find_element(By.CSS_SELECTOR, '[data-qa-itemtype="docTitle"]')
                        if title_elem and title_elem.text.strip() and len(title_elem.text.strip()) > 5:
                            has_real_content = True
                            break
                    except:
                        continue
                
                if not has_real_content and len(placeholder_items) > 0:
                    send_message_to_client(socketio, app, "La page n'a pas fini de charger. Timeout après 30 secondes.", session_id)
                    print(f"[TIMEOUT] La page n'a pas fini de charger après 30 secondes. Éléments trouvés: {len(placeholder_items)}")
                else:
                    send_message_to_client(socketio, app, "Erreur lors du chargement des résultats de recherche.", session_id)
                result_data_sorted = []


            # Retourner l'instance du navigateur pour une utilisation ultérieure
        send_message_to_client(socketio, app,"Recherche terminée avec succès.",session_id)
        return driver, result_data_sorted

    except Exception as e:
        driver.save_screenshot('ss.png')
        with open("page_source.html", "w", encoding="utf-8") as file:
            file.write(driver.page_source)
        # Gestion sécurisée des erreurs avec caractères Unicode - double protection
        try:
            error_message = str(e).encode('utf-8', errors='replace').decode('utf-8')
            send_message_to_client(socketio, app,f"Une erreur s'est produite lors de la recherche : {error_message}", session_id)
        except Exception as encoding_error:
            # Si même l'encodage échoue, envoyer un message générique
            print(f"Erreur d'encodage dans send_message_to_client: {encoding_error}")
            send_message_to_client(socketio, app,"Une erreur d'encodage s'est produite lors de la recherche", session_id)
        return None
