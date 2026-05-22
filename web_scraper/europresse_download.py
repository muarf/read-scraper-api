import os
import requests
from bs4 import BeautifulSoup
from common.utils import send_message_to_client, sanitize_filename

def download_europresse_article(doc_id, cookies_list, session_id, save_dir='downloads'):
    """
    Télécharge et formate le HTML d'un article Europresse en utilisant requests et les cookies de session.
    """
    domain = "nouveau-europresse-com.bnf.idm.oclc.org"
    
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
        
    session = requests.Session()
    for cookie in cookies_list:
        session.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain', ''))
        
    try:
        url = f"https://{domain}/Document/ViewMobile?docKey={doc_id}&fromBasket=false&viewEvent=1&invoiceCode="
        send_message_to_client(f"Téléchargement du document {doc_id}...", session_id)
        
        response = session.get(url, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        content_div = soup.find(class_='docOcurrContainer')
        if not content_div:
            send_message_to_client("Erreur: Contenu spécifique 'docOcurrContainer' introuvable.", session_id)
            return None
            
        send_message_to_client("Article trouvé, nettoyage des entêtes...", session_id)
        
        # Le titre sur Europresse mobile n'est pas forcément complet dans docOcurrContainer
        title_elem = soup.find(class_='titreArticleVisu')
        title_text = title_elem.get_text(strip=True) if title_elem else ''
        
        html_content = str(content_div)
        if title_text:
            html_content = f"<h1>{title_text}</h1>{html_content}"
            
        return html_content

    except Exception as e:
        send_message_to_client(f"Erreur lors du téléchargement : {e}", session_id)
        return None
