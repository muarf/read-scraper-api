import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from common.utils import send_message_to_client

def calculate_similarity(query, title):
    if not query or not title:
        return 0
        
    # Normalisation simple
    q = query.lower().split()
    t = title.lower().split()
    
    if not q or not t:
        return 0
        
    # Mots importants (longueur > 3)
    set_query = set([w for w in q if len(w) > 3])
    set_title = set([w for w in t if len(w) > 3])
    
    # Si trop peu de mots longs, prendre tout
    if not set_query: set_query = set(q)
    if not set_title: set_title = set(t)
    
    intersection = set_query.intersection(set_title)
    union = set_query.union(set_title)
    
    if not union:
        return 0
        
    # Score d'intersection pondéré par la longueur des mots
    # On donne plus de poids aux mots longs
    score = sum(len(w) for w in intersection)
    total = sum(len(w) for w in set_query)
    
    if total == 0: return 0
    
    similarity_percentage = round((score / total) * 100)
    # Cap à 100
    return min(similarity_percentage, 100)

def search_europresse_target(cookies_list, query, title, session_id, published_date=None):
    """
    Effectue une recherche sur Europresse via requêtes HTTP `requests` en utilisant les cookies EZProxy interceptés.
    Retourne la liste des résultats triés par pourcentage de similarité.
    """
    domain = "nouveau-europresse-com.bnf.idm.oclc.org"
    
    # Calcul du filtre de date (Ophirofox style)
    date_filter_value = "9" # Par défaut : Toutes les archives
    if published_date:
        try:
            # Nettoyage de la date ISO (ex: 2026-04-06T12:00:00Z -> 2026-04-06)
            date_str = published_date.split('T')[0]
            pub_date = datetime.strptime(date_str, "%Y-%m-%d")
            now = datetime.now()
            diff_days = (now - pub_date).days
            
            if diff_days <= 1: date_filter_value = "2"
            elif diff_days <= 3: date_filter_value = "11"
            elif diff_days <= 7: date_filter_value = "3"
            elif diff_days <= 30: date_filter_value = "4"
            elif diff_days <= 90: date_filter_value = "5"
            elif diff_days <= 180: date_filter_value = "6"
            elif diff_days <= 365: date_filter_value = "7"
            elif diff_days <= 730: date_filter_value = "8"
            else: date_filter_value = "9"
            
            print(f"[DATE FILTER] Date={date_str}, Diff={diff_days} jours, FilterValue={date_filter_value}")
        except Exception as e:
            print(f"[DATE FILTER] Erreur parsing date '{published_date}': {e}")
            date_filter_value = "9"

    # 1. Configurer la session requests
    session = requests.Session()
    for cookie in cookies_list:
        session.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain', ''))
    
    try:
        send_message_to_client("Chargement de la page de recherche (HTTP)...", session_id)
        
        # Obtenir le jeton CSRF
        url_reading = f"https://{domain}/Search/Reading"
        response = session.get(url_reading, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        token_input = soup.find('input', {'name': '__RequestVerificationToken'})
        token = token_input['value'] if token_input else ''
        
        if not token:
            send_message_to_client("Jeton de sécurité introuvable, tentative de poursuite...", session_id)

        # Nettoyage des mots-clés (proche de la regex JS d'Ophirofox)
        import re
        clean_query = " ".join(re.findall(r"[\w\d]+", query, flags=re.UNICODE))
        
        send_message_to_client(f"Recherche HTTP avancée avec : {clean_query}", session_id)

        # 2. Forge de la requête POST AdvancedSearch
        # On tente d'abord par TIT_HEAD (titre), puis en fallback par TEXT (contenu complet)
        search_strategies = [
            {"label": "TIT_HEAD", "key": "TIT_HEAD", "term": clean_query},
            {"label": "TEXT (Fallback)", "key": "TEXT", "term": clean_query},
            {"label": "TEXT (Full Title)", "key": "TEXT", "term": title[:100]}
        ]
        
        all_results = []
        for strategy in search_strategies:
            search_term = strategy['term']
            send_message_to_client(f"Recherche HTTP ({strategy['label']}) avec : {search_term}", session_id)
            
            data = {
                "Keywords": search_term,
                "CriteriaKeys[0].Operator": "&",
                "CriteriaKeys[0].Key": strategy['key'],
                "CriteriaKeys[0].Text": search_term,
                "CriteriaKeys[1].Operator": "&",
                "CriteriaKeys[1].Key": "LEAD",
                "CriteriaKeys[1].Text": "",
                "CriteriaKeys[2].Operator": "&",
                "CriteriaKeys[2].Key": "AUT_BY",
                "CriteriaKeys[2].Text": "",
                "sources": "2",
                "CriteriaSet": "-1",
                "sourcesFilter": "",
                "PostedFilters.FiltersIDs": "8001",
                "DateFilter.DateRange": date_filter_value,
                "DateFilter.DateStart": "1970-01-01",
                "DateFilter.DateStop": "2050-01-01",
                "SourcesForm": "2",
                "CriteriaExp[0].CriteriaName": "Anglais",
                "CriteriaExp[0].CriteriaId": "2",
                "CriteriaExp[0].OperatorId": "2",
                "CriteriaExp[1].CriteriaName": "Français",
                "CriteriaExp[1].CriteriaId": "1",
                "CriteriaExp[1].OperatorId": "2",
                "__RequestVerificationToken": token
            }

            url_advanced = f"https://{domain}/Search/AdvancedMobile"
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}
            
            try:
                # Augmentation du timeout à 45s car Europresse via BnF peut être très lent
                post_response = session.post(url_advanced, data=data, headers=headers, timeout=45)
                print(f"[DEBUG] strategy={strategy['key']} POST Status: {post_response.status_code}")
                
                # 3. Récupération des pages de résultats
                send_message_to_client(f"Parsing des résultats ({strategy['label']})...", session_id)

                for page_no in range(0, 3): # Limite à 3 pages pour la rapidité
                    url_page = f"https://{domain}/Search/GetPage?pageNo={page_no}&docPerPage=50"
                    page_response = session.get(url_page, timeout=45)
                    
                    if not page_response.text.strip():
                        print(f"[DEBUG] Page {page_no} vide")
                        break
                        
                    page_soup = BeautifulSoup(page_response.text, 'html.parser')
                    items = page_soup.find_all('div', class_='docListItem')
                    
                    if not items:
                        print(f"[DEBUG] Aucun 'docListItem' sur la page {page_no}")
                        if page_no == 0:
                            print(f"[DEBUG] Extrait HTML (page {page_no}): {page_response.text[:500]}")
                        break
                        
                    for item in items:
                        title_elem = item.find(class_='docList-links')
                        doc_title = title_elem.get_text(strip=True) if title_elem else ''
                        
                        source_elem = item.find(class_='source-name')
                        logo_label = source_elem.get_text(strip=True) if source_elem else 'inconnu'
                        
                        date_elem = item.find(class_='details')
                        doc_date = date_elem.get_text(strip=True).split('•')[0].strip() if date_elem else ''
                        
                        id_input = item.find('input', id='doc-name')
                        doc_id = id_input['value'] if id_input else ''
                        
                        if doc_id:
                            similarity_percentage = calculate_similarity(title, doc_title)
                            length_desc = item.find(class_='kwicResult')
                            desc_text = length_desc.get_text() if length_desc else doc_title
                            estimated_length = len(desc_text.split()) * 5
                            
                            all_results.append({
                                'link': doc_id,
                                'logo': logo_label,
                                'title': doc_title,
                                'date': doc_date,
                                'percentage': similarity_percentage,
                                'length': estimated_length
                            })
                
                if all_results:
                    print(f"[DEBUG] Résultats trouvés avec la stratégie {strategy['key']}")
                    break # On a trouvé des résultats, on s'arrête là
                else:
                    print(f"[DEBUG] Aucun résultat avec {strategy['key']}, tentative strategy suivante...")
            
            except requests.exceptions.Timeout:
                print(f"[DEBUG] Timeout lors de la recherche avec {strategy['key']}")
                continue # On tente la stratégie suivante même si timeout sur la précédente

        # Tri des résultats par similarité
        result_data_sorted = sorted(all_results, key=lambda x: x['percentage'], reverse=True)
        print(f"[DEBUG] Total résultats triés: {len(result_data_sorted)}")
        send_message_to_client(f"Recherche terminée avec {len(result_data_sorted)} résultat(s).", session_id)
        
        return result_data_sorted

    except Exception as e:
        error_message = str(e).encode('utf-8', errors='replace').decode('utf-8')
        send_message_to_client(f"Erreur lors de la recherche Europresse HTTP : {error_message}", session_id)
        return []
