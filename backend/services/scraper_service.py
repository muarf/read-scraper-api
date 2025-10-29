"""
Service de scraping intégrant le code existant
"""
import os
import sys
from pathlib import Path
from urllib.parse import urlparse
from backend.models.database import Database
from backend.config.settings import STATIC_DIR, HEADLESS, CHROME_PATH, CHROMEDRIVER_PATH, USERNAME, PASSWORD
from backend.services.pdf_service import PDFService
import logging
import re

# Ajouter le chemin des modules existants
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from web_scraper.chrome_driver_login import login_to_target_site
from web_scraper.chrome_driver_search import search_target_site
from web_scraper.extract_title import extract_title
from web_scraper.download_article import download_article, sanitize_filename
from common.utils import generate_id, file_exists
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import os

logger = logging.getLogger(__name__)


class ScraperService:
    """Service de scraping d'articles"""
    
    def __init__(self, db: Database, pdf_service: PDFService):
        self.db = db
        self.pdf_service = pdf_service
        self.browser = None
        self._init_browser()
        # Se connecter au site après l'initialisation du navigateur
        self._login()

    def remove_highlight_tags(self, html: str) -> str:
        """Supprime les balises mark/highlight du HTML tout en gardant le contenu"""
        # Supprimer récursivement toutes les balises mark (y compris imbriquées)
        max_iterations = 10  # Éviter les boucles infinies
        iteration = 0
        while '<mark' in html and iteration < max_iterations:
            html = re.sub(r'<mark[^>]*>(.*?)</mark>', r'\1', html, flags=re.DOTALL)
            iteration += 1
        # Supprimer les classes hlterms restantes
        html = re.sub(r'class="hlterms"', '', html)
        return html

    def _init_browser(self):
        """Initialiser le navigateur Chrome"""
        logger.info("[BROWSER_INIT] Début initialisation navigateur")
        chrome_options = Options()
        chrome_options.binary_location = CHROME_PATH
        logger.info(f"[BROWSER_INIT] Chrome path: {CHROME_PATH}")
        
        # Utiliser le chromedriver local
        chromedriver_path = CHROMEDRIVER_PATH
        logger.info(f"Tentative d'utilisation du chromedriver: {chromedriver_path}")
        if os.path.exists(chromedriver_path) and os.path.isfile(chromedriver_path):
            from selenium.webdriver.chrome.service import Service
            logger.info(f"Chromedriver trouvé: {chromedriver_path}")
            service = Service(CHROMEDRIVER_PATH)
            
            # NE PAS mettre headless pour voir ce qui se passe
            if HEADLESS:
                chrome_options.add_argument('--headless')
            chrome_options.add_argument('--window-size=1920x1080')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            
            try:
                self.browser = webdriver.Chrome(service=service, options=chrome_options)
                logger.info("Navigateur Chrome initialisé avec chromedriver_local (headless={})".format(HEADLESS))
            except Exception as e:
                logger.error(f"Erreur initialisation Chrome avec chromedriver_local: {e}")
                raise
        else:
            # Fallback si chromedriver_local n'existe pas
            if HEADLESS:
                chrome_options.add_argument('--headless')
            chrome_options.add_argument('--window-size=1920x1080')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            
            try:
                self.browser = webdriver.Chrome(options=chrome_options)
                logger.info("[BROWSER_INIT] Navigateur Chrome initialisé avec succès")
                logger.info(f"[BROWSER_INIT] Navigateur object: {self.browser}")
            except Exception as e:
                logger.error(f"[BROWSER_INIT] Erreur initialisation Chrome: {e}")
                raise
    
    def _login(self):
        """Se connecter au site cible"""
        try:
            logger.info("[LOGIN] Début connexion au site cible")
            logger.info(f"[LOGIN] Navigateur: {self.browser}")
            login_to_target_site(None, None, self.browser, USERNAME, PASSWORD, None)
            logger.info("[LOGIN] Connexion réussie")
            logger.info(f"[LOGIN] Navigateur après connexion: {self.browser}")
        except Exception as e:
            logger.warning(f"[LOGIN] Erreur connexion, on continue: {e}")
    
    def _get_browser(self):
        """Récupérer ou initialiser le navigateur"""
        logger.info(f"[BROWSER] Vérification navigateur existant: {self.browser is not None}")
        if self.browser is None:
            logger.info("[BROWSER] Aucun navigateur, initialisation...")
            self._init_browser()
            logger.info(f"[BROWSER] Navigateur initialisé: {self.browser is not None}")
            self._login()
            logger.info("[BROWSER] Connexion effectuée")
        else:
            logger.info("[BROWSER] Navigateur existant réutilisé")
        return self.browser
    
    def scrape_article(self, url: str, job_id: str) -> tuple:
        """
        Scraper un article depuis une URL

        Args:
            url: URL de l'article à scraper
            job_id: ID du job en cours

        Returns:
            tuple: (article_id, article_data) ou None en cas d'erreur
        """
        try:
            logger.info(f"[{job_id}] === DÉBUT DU SCRAPING ===")
            logger.info(f"[{job_id}] URL: {url}")

            browser = None  # Navigateur potentiel pour l'extraction du titre

            # Étape 1: Extraire le titre (essaie sans navigateur d'abord)
            logger.info(f"[{job_id}] === ÉTAPE 1: Extraction du titre ===")
            result = extract_title(url)  # Essaie sans navigateur d'abord
            logger.info(f"[{job_id}] Résultat extract_title sans navigateur: {result}")

            # Si échec, essayer avec un navigateur
            if result is None:
                logger.info(f"[{job_id}] Échec sans navigateur, création pour titre")
                browser = self._get_browser()
                result = extract_title(url, browser)
                logger.info(f"[{job_id}] Résultat extract_title avec navigateur: {result}")

            if result is None:
                raise Exception(f"Impossible d'extraire le titre de l'URL {url}")

            query, title = result
            logger.info(f"[{job_id}] Titre extrait: '{title}'")
            logger.info(f"[{job_id}] Query généré: '{query}'")

            # Étape 2: Générer le nom du fichier à partir du query (titre nettoyé)
            logger.info(f"[{job_id}] === ÉTAPE 2: Génération du nom de fichier ===")
            query_ = query.replace(" ", "_")
            name = (lambda u: urlparse(u).path.split('/')[-1][:90])(query_)
            logger.info(f"[{job_id}] Query_: '{query_}'")
            logger.info(f"[{job_id}] Nom généré: '{name}'")

            # Vérifier si le fichier existe déjà
            # Forcer le bon chemin static (correction temporaire du bug STATIC_DIR)
            from pathlib import Path
            correct_static_dir = Path(__file__).resolve().parent.parent.parent / "static"
            html_path = correct_static_dir / f"{name}.html"
            pdf_path = correct_static_dir / f"{name}.pdf"
            logger.info(f"[{job_id}] PDF path corrigé: {pdf_path}")
            logger.info(f"[{job_id}] Chemins: HTML={html_path}, PDF={pdf_path}")

            article_id = generate_id(10)
            logger.info(f"[{job_id}] Article ID généré: {article_id}")

            # Si le fichier existe, on le récupère
            if file_exists(name):
                logger.info(f"[{job_id}] Fichier déjà existant, récupération...")
                logger.info(f"[{job_id}] Chemin HTML: {html_path}")

                with open(html_path, 'r', encoding='utf-8') as f:
                    html_content = f.read()

                logger.info(f"[{job_id}] Contenu HTML chargé: {len(html_content)} caractères")

                # Utiliser l'article_id pour stocker dans la BDD
                article_id = name  # Utiliser le nom comme ID

                # Vérifier si déjà en BDD
                existing_article = self.db.get_article(article_id)
                if existing_article:
                    logger.info(f"[{job_id}] Article déjà en BDD, retour du cache")
                    return (article_id, {
                        'id': article_id,
                        'url': url,
                        'title': title,
                        'html_content': html_content,
                        'pdf_path': str(pdf_path)
                    })

            # Étape 3: Rechercher l'article sur le site cible
            logger.info(f"[{job_id}] === ÉTAPE 3: Recherche sur le site cible ===")
            # Utiliser le navigateur existant si déjà ouvert pour le titre, sinon en créer un nouveau
            if browser is None:
                browser = self._get_browser()  # Connexion seulement maintenant pour la recherche
                logger.info(f"[{job_id}] Navigateur initialisé pour recherche: {browser is not None}")
            else:
                logger.info(f"[{job_id}] Réutilisation navigateur existant: {browser is not None}")
            search_result = search_target_site(None, None, browser, query, title, job_id)
            logger.info(f"[{job_id}] Résultat recherche: {search_result}")
            
            if search_result is None:
                raise Exception("Aucun résultat trouvé pour cet article")
            
            _, results_data = search_result
            
            if not results_data or len(results_data) == 0:
                raise Exception("Aucun résultat trouvé")
            
            # Déterminer le site source depuis l'URL
            parsed_url = urlparse(url)
            site_domain = parsed_url.netloc.lower()
            
            # Mapping des domaines aux noms de sources (doivent correspondre aux logos affichés)
            site_mapping = {
                'www.liberation.fr': 'libération',
                'liberation.fr': 'libération',
                'www.mediapart.fr': 'mediapart',
                'mediapart.fr': 'mediapart',
                'www.lemonde.fr': 'le monde',
                'lemonde.fr': 'le monde',
                'www.lesjours.fr': 'lesjours.fr',
                'lesjours.fr': 'lesjours.fr',
            }
            
            source_key = None
            for domain, source in site_mapping.items():
                if domain in site_domain:
                    source_key = source
                    break
            
            # Collecter tous les résultats du même site source
            site_results = []
            if source_key:
                for result in results_data:
                    logo_lower = result.get('logo', '').lower()
                    logger.info(f"[{job_id}] Vérification du résultat: {logo_lower} (cherche: {source_key}) - Longueur: {result.get('length', 0)} mots")
                    if source_key in logo_lower or logo_lower in source_key:
                        site_results.append(result)
                        logger.info(f"[{job_id}] Résultat du site source trouvé!")

            # Si on a des résultats du site source, prendre celui avec le plus de mots
            if site_results:
                best_match = max(site_results, key=lambda x: x.get('length', 0))
                logger.info(f"[{job_id}] Sélection du résultat le plus long: {best_match.get('length', 0)} mots - Site: {best_match.get('logo', 'inconnu')}")
            else:
                # Si pas de correspondance exacte, prendre le meilleur résultat
                best_match = results_data[0]
                logger.warning(f"[{job_id}] Aucune correspondance exacte trouvée, utilisation du meilleur résultat")
            
            link = best_match['link']
            percentage = best_match['percentage']
            
            logger.info(f"[{job_id}] Article trouvé avec probabilité {percentage}% - Site: {best_match.get('logo', 'inconnu')}")
            
            # Étape 4: Télécharger le contenu de l'article
            logger.info(f"[{job_id}] Téléchargement du contenu...")
            html_content = download_article(None, None, browser, link, job_id)

            if html_content is None:
                raise Exception("Impossible de télécharger le contenu de l'article")

            # Nettoyer les balises de surlignement AVANT de générer PDF/HTML et sauvegarder en BDD
            logger.info(f"[{job_id}] Nettoyage des balises <mark> du contenu HTML...")
            html_content = self.remove_highlight_tags(html_content)
            logger.info(f"[{job_id}] Balises <mark> nettoyées")

            # Étape 5: Générer le PDF
            logger.info(f"[{job_id}] Génération du PDF...")
            pdf_path, html_path = self.pdf_service.generate_pdf(html_content, query_, job_id)
            
            # Étape 6: Sauvegarder dans la BDD
            site_source = urlparse(url).netloc
            
            logger.info(f"[{job_id}] Sauvegarde dans la BDD...")
            self.db.create_article(
                article_id=article_id,
                url=url,
                title=title,
                html_content=html_content,
                pdf_path=str(pdf_path),
                site_source=site_source,
                tags=None,
                metadata=None
            )
            
            logger.info(f"[{job_id}] Scraping terminé avec succès")
            
            return (article_id, {
                'id': article_id,
                'url': url,
                'title': title,
                'html_content': html_content,
                'pdf_path': str(pdf_path),
                'site_source': site_source,
                'percentage': percentage
            })
        
        except Exception as e:
            logger.error(f"[{job_id}] Erreur scraping: {e}")
            raise
    
    def cleanup(self):
        """Nettoyer le navigateur"""
        logger.info("[CLEANUP] Début nettoyage navigateur")
        logger.info(f"[CLEANUP] Navigateur existant: {self.browser is not None}")
        if self.browser:
            try:
                logger.info("[CLEANUP] Fermeture du navigateur...")
                self.browser.quit()
                self.browser = None
                logger.info("[CLEANUP] Navigateur fermé avec succès")
            except Exception as e:
                logger.error(f"[CLEANUP] Erreur fermeture navigateur: {e}")
        else:
            logger.info("[CLEANUP] Aucun navigateur à fermer")

