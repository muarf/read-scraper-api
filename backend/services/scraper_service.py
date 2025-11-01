"""
Service de scraping intégrant le code existant
"""
import os
import sys
import time
import json
from pathlib import Path
import urllib.parse as urlp
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
from common.utils import generate_id, file_exists, NoResultException
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
        # Initialisation lazy - seulement quand nécessaire
        self._browser_initialized = False

    def _cleanup_job_screenshots(self, job_id: str):
        """Supprime les screenshots de debug associés à un job_id (mais pas les page_source)."""
        try:
            static_dir = Path(__file__).resolve().parent.parent.parent / "static"
            pattern = f"debug_*_{job_id}_*.png"
            for f in static_dir.glob(pattern):
                os.remove(f)
                logger.info(f"Fichier de debug supprimé: {f}")

        except Exception as e:
            logger.warning(f"Erreur lors du nettoyage des fichiers de debug pour le job {job_id}: {e}")

    def _ensure_browser(self):
        """S'assurer que le navigateur est initialisé"""
        if not self._browser_initialized:
            logger.info("Initialisation lazy du navigateur")
            self._init_browser()
            self._login()
            self._browser_initialized = True

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

    def _clean_search_terms(self, terms: str) -> str:
        """
        Nettoie les termes de recherche personnalisés de la même manière que extract_title.
        Supprime la ponctuation et normalise les caractères spéciaux.
        """
        import string
        
        # 1) Normaliser les apostrophes et guillemets typographiques (comme extract_title)
        # Remplacer les apostrophes typographiques par des apostrophes simples
        terms_cleaned = (
            terms
            .replace("'", "'")
            .replace("'", "'")
            .replace(""", '"')
            .replace(""", '"')
        )
        
        # 2) Supprimer la ponctuation (y compris les slashes) - exactement comme extract_title
        extra_punct = "…–—«»\"\"''/"
        punctuation_chars = string.punctuation + extra_punct
        terms_no_punct = terms_cleaned.translate(str.maketrans(punctuation_chars, ' ' * len(punctuation_chars)))
        
        # 3) Nettoyer les espaces multiples et trim
        terms_cleaned = ' '.join(terms_no_punct.split())
        
        return terms_cleaned

    def _init_browser(self):
        """Initialiser le navigateur Chrome"""
        logger.info("[BROWSER_INIT] Début initialisation navigateur")
        
        # Recharger dynamiquement CHROME_PATH depuis le fichier de config pour utiliser la configuration mise à jour
        import backend.config.settings as settings_module
        from backend.config.settings import load_browser_config
        
        # Recharger depuis le fichier si disponible
        saved_path = load_browser_config()
        if saved_path:
            settings_module.CHROME_PATH = saved_path
            logger.info(f"[BROWSER_INIT] Configuration rechargée depuis le fichier: {saved_path}")
        
        current_chrome_path = settings_module.CHROME_PATH
        
        chrome_options = Options()
        chrome_options.binary_location = current_chrome_path
        logger.info(f"[BROWSER_INIT] Chrome path: {current_chrome_path}")
        
        # Utiliser le chromedriver local
        chromedriver_path = settings_module.CHROMEDRIVER_PATH
        logger.info(f"Tentative d'utilisation du chromedriver: {chromedriver_path}")
        if os.path.exists(chromedriver_path) and os.path.isfile(chromedriver_path):
            from selenium.webdriver.chrome.service import Service
            logger.info(f"Chromedriver trouvé: {chromedriver_path}")
            service = Service(chromedriver_path)
            
            # Mode headless activé pour éviter les problèmes d'affichage en environnement serveur
            if HEADLESS:
                chrome_options.add_argument('--headless')
            chrome_options.add_argument('--window-size=1920x1080')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-web-security')
            chrome_options.add_argument('--disable-features=VizDisplayCompositor')
            chrome_options.add_argument('--disable-background-timer-throttling')
            chrome_options.add_argument('--disable-backgrounding-occluded-windows')
            chrome_options.add_argument('--disable-renderer-backgrounding')
            chrome_options.add_argument('--remote-debugging-port=0')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--disable-software-rasterizer')
            
            try:
                self.browser = webdriver.Chrome(service=service, options=chrome_options)
                logger.info("Navigateur Chrome initialisé avec chromedriver_local (headless={})".format(HEADLESS))
            except Exception as e:
                logger.error(f"Erreur initialisation Chrome avec chromedriver_local: {e}")
                raise
        else:
            # Fallback si chromedriver_local n'existe pas
            # Mode headless activé pour éviter les problèmes d'affichage en environnement serveur
            if HEADLESS:
                chrome_options.add_argument('--headless')
            chrome_options.add_argument('--window-size=1920x1080')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-web-security')
            chrome_options.add_argument('--disable-features=VizDisplayCompositor')
            chrome_options.add_argument('--disable-background-timer-throttling')
            chrome_options.add_argument('--disable-backgrounding-occluded-windows')
            chrome_options.add_argument('--disable-renderer-backgrounding')
            chrome_options.add_argument('--remote-debugging-port=0')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--disable-software-rasterizer')
            
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

    def _try_direct_scraping(self, browser, url, parsed_url, job_id):
        """Tenter un scraping direct depuis l'URL pour les sites supportés"""
        try:
            logger.info(f"[{job_id}] Tentative de scraping direct: {url}")

            # Utiliser le navigateur existant ou en créer un nouveau
            if browser is None:
                browser = self._get_browser()
                if not browser:
                    return None

            # Accéder directement à l'URL
            browser.get(url)

            # Attendre que la page se charge
            time.sleep(3)

            # Chercher le contenu principal (différent selon le site)
            domain = urlp.urlparse(url).netloc

            content_selectors = {
                'leparisien.fr': 'div.content',
                'lemonde.fr': 'article',
                'liberation.fr': '.article-body',
                'mediapart.fr': '.content'
            }

            selector = content_selectors.get(domain, 'div.content')

            try:
                from selenium.webdriver.common.by import By
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC

                content_element = WebDriverWait(browser, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )

                html_content = content_element.get_attribute('outerHTML')

                # Générer un ID d'article et sauvegarder
                article_id = generate_id(10)
                title = browser.title or f"Article {article_id}"

                # Sauvegarder dans la base de données
                self.db.save_article(article_id, title, html_content, url, job_id)

                logger.info(f"[{job_id}] Article scrapé directement: {article_id}")

                return (article_id, {
                    'id': article_id,
                    'url': url,
                    'title': title,
                    'html_content': html_content
                })

            except Exception as e:
                logger.warning(f"[{job_id}] Échec extraction contenu avec selector {selector}: {e}")
                return None

        except Exception as e:
            logger.warning(f"[{job_id}] Échec scraping direct: {e}")
            return None

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
        # Nettoyer les screenshots du job précédent
        self._cleanup_job_screenshots(job_id)

        # S'assurer que le navigateur est initialisé
        self._ensure_browser()

        try:
            logger.info(f"[{job_id}] === DÉBUT DU SCRAPING ===")
            logger.info(f"[{job_id}] URL: {url}")

            browser = None  # Navigateur potentiel pour l'extraction du titre

            # Vérifier si des termes de recherche personnalisés ont été fournis
            job = self.db.get_job(job_id)
            job_data = json.loads(job.get('data', '{}')) if job and job.get('data') else {}
            custom_search_terms = job_data.get('custom_search_terms')
            
            # Détecter si c'est un job avec seulement des search_terms (URL placeholder)
            is_search_terms_only = url.startswith('search_terms:') if url else False
            
            # Extraire les termes depuis l'URL placeholder si nécessaire
            if is_search_terms_only and not custom_search_terms:
                # Extraire depuis le placeholder "search_terms:termes..."
                custom_search_terms = url.replace('search_terms:', '', 1) if url.startswith('search_terms:') else ''
                # Stocker dans les données du job
                if custom_search_terms:
                    self.db.update_job_data(job_id, {'custom_search_terms': custom_search_terms})
            
            # Utiliser les termes personnalisés si fournis OU si c'est un job search_terms uniquement
            if custom_search_terms:
                logger.info(f"[{job_id}] === Utilisation de termes de recherche personnalisés ===")
                logger.info(f"[{job_id}] Termes bruts: '{custom_search_terms}'")
                
                # Mettre à jour l'étape actuelle
                self.db.update_job_data(job_id, {
                    'current_step': 'preparing',
                    'step_description': 'Préparation des termes de recherche...'
                })
                
                # Nettoyer les termes personnalisés comme extract_title le fait
                query = self._clean_search_terms(custom_search_terms)
                title = custom_search_terms  # Le titre d'affichage reste tel quel
                logger.info(f"[{job_id}] Termes personnalisés nettoyés: '{query}'")
            else:
                # Étape 1: Extraire le titre (essaie sans navigateur d'abord)
                logger.info(f"[{job_id}] === ÉTAPE 1: Extraction du titre ===")
                
                # Mettre à jour l'étape actuelle
                self.db.update_job_data(job_id, {
                    'current_step': 'extracting_title',
                    'step_description': 'Analyse de l\'URL et extraction du titre...'
                })
                
                result = extract_title(url)  # Essaie sans navigateur d'abord
                logger.info(f"[{job_id}] Résultat extract_title sans navigateur: {result}")

                # Si échec, essayer avec un navigateur
                if result is None:
                    logger.info(f"[{job_id}] Échec sans navigateur, création pour titre")
                    browser = self._get_browser()
                    result = extract_title(url, browser)
                    logger.info(f"[{job_id}] Résultat extract_title avec navigateur: {result}")

                if result is None:
                    logger.error(f"[{job_id}] Impossible d'extraire le titre de l'URL {url} - site protégé par Cloudflare ou indisponible")
                    # Essayer une approche alternative : utiliser l'URL elle-même comme titre
                    parsed_url = urlp.urlparse(url)
                    fallback_title = parsed_url.path.strip('/').replace('-', ' ').replace('_', ' ').replace('/', ' ').title()
                    # Nettoyer les espaces multiples
                    fallback_title = ' '.join(fallback_title.split())
                    if fallback_title and len(fallback_title) > 5:
                        result = (fallback_title, fallback_title)
                        logger.info(f"[{job_id}] Utilisation du titre de fallback depuis l'URL: {result}")
                    else:
                        raise Exception(f"Impossible d'extraire le titre de l'URL {url} - protection anti-bot détectée")

                query, title = result
                logger.info(f"[{job_id}] Titre extrait: '{title}'")
                logger.info(f"[{job_id}] Query généré: '{query}'")

            # Stocker les termes de recherche dans les données du job
            self.db.update_job_data(job_id, {
                'search_terms': query,
                'extracted_title': title
            })

            # Étape 2: Générer le nom du fichier à partir du query (titre nettoyé)
            logger.info(f"[{job_id}] === ÉTAPE 2: Génération du nom de fichier ===")
            
            # Mettre à jour l'étape actuelle
            self.db.update_job_data(job_id, {
                'current_step': 'preparing',
                'step_description': 'Préparation des fichiers...'
            })
            
            query_ = query.replace(" ", "_")
            name = (lambda u: urlp.urlparse(u).path.split('/')[-1][:90])(query_)
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

            # Étape 3: Recherche sur le site cible ou scraping direct
            logger.info(f"[{job_id}] === ÉTAPE 3: Recherche/scraping ===")

            # Vérifier si l'URL vient d'un site supporté pour scraping direct
            parsed_url = urlp.urlparse(url)
            supported_domains = ['leparisien.fr', 'lemonde.fr', 'liberation.fr', 'mediapart.fr']

            # Vérifier si le domaine contient un des domaines supportés
            is_supported_domain = any(domain in parsed_url.netloc for domain in supported_domains)
            logger.info(f"[{job_id}] Domaine détecté: {parsed_url.netloc}, supporté: {is_supported_domain}")

            if is_supported_domain:
                logger.info(f"[{job_id}] URL de site supporté détecté ({parsed_url.netloc}), tentative de scraping direct")
                # Essayer le scraping direct
                try:
                    direct_result = self._try_direct_scraping(browser, url, parsed_url, job_id)
                    if direct_result:
                        logger.info(f"[{job_id}] Scraping direct réussi")
                        # Mettre à jour les données de debug pour scraping direct
                        self.db.update_job_data(job_id, {
                            'scraping_method': 'direct',
                            'source_site': parsed_url.netloc
                        })
                        return direct_result
                    else:
                        logger.info(f"[{job_id}] Scraping direct échoué, fallback vers recherche Tagadoc")
                except Exception as e:
                    logger.warning(f"[{job_id}] Erreur scraping direct: {e}, fallback vers recherche")

            # Recherche Tagadoc comme fallback
            # Utiliser le navigateur existant si déjà ouvert pour le titre, sinon en créer un nouveau
            if browser is None:
                browser = self._get_browser()  # Connexion seulement maintenant pour la recherche
                logger.info(f"[{job_id}] Navigateur initialisé pour recherche: {browser is not None}")
            else:
                logger.info(f"[{job_id}] Réutilisation navigateur existant: {browser is not None}")
            # Screenshot avant la recherche
            try:
                debug_screenshot_path = f"/root/read-scraper-api/static/debug_before_search_{job_id}_{int(time.time())}.png"
                browser.save_screenshot(debug_screenshot_path)
                logger.info(f"[{job_id}] Screenshot avant recherche: {debug_screenshot_path}")

                # Mettre à jour les données du job avec l'étape actuelle
                self.db.update_job_data(job_id, {
                    'search_terms': query,
                    'extracted_title': title,
                    'current_step': 'searching',
                    'step_description': 'Recherche d\'articles similaires en cours...'
                })
            except Exception as ss_error:
                logger.warning(f"[{job_id}] Impossible de prendre screenshot avant recherche: {ss_error}")

            logger.info(f"[{job_id}] ENVOI À LA RECHERCHE - Query: '{query}' (len={len(query)}), Title: '{title[:50]}...'")
            search_result = search_target_site(None, None, browser, query, title, job_id)
            logger.info(f"[{job_id}] Résultat recherche: {search_result}")

            # Mettre à jour les données de debug avec les résultats de recherche
            if search_result and isinstance(search_result, (list, tuple)) and len(search_result) > 1:
                browser_results, articles = search_result
                # Calculer les statistiques de recherche
                total_articles = len(articles) if articles else 0
                best_match = None
                if articles and isinstance(articles, list):
                    try:
                        best_match = max(articles, key=lambda x: x.get('percentage', 0))
                    except (ValueError, TypeError):
                        best_match = articles[0] if articles else None

                self.db.update_job_data(job_id, {
                    'search_results_count': total_articles,
                    'best_match_title': best_match.get('title') if best_match else None,
                    'best_match_percentage': best_match.get('percentage', 0) if best_match else 0,
                    'best_match_source': best_match.get('logo') if best_match else None
                })

            if search_result is None:
                # Screenshot en cas d'échec de recherche
                try:
                    error_screenshot_path = f"/root/read-scraper-api/static/debug_search_failed_{job_id}_{int(time.time())}.png"
                    browser.save_screenshot(error_screenshot_path)
                    logger.info(f"[{job_id}] Screenshot d'échec de recherche: {error_screenshot_path}")
                except Exception as ss_error:
                    logger.warning(f"[{job_id}] Impossible de prendre screenshot d'échec: {ss_error}")

                raise NoResultException("Aucun résultat trouvé pour cet article")
            
            _, results_data = search_result
            
            if not results_data or len(results_data) == 0:
                raise NoResultException("Aucun résultat trouvé")
            
            # Déterminer le site source depuis l'URL
            parsed_url = urlp.urlparse(url)
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

            # Mettre à jour l'étape avec les résultats de recherche
            self.db.update_job_data(job_id, {
                'search_terms': query,
                'extracted_title': title,
                'current_step': 'downloading',
                'step_description': 'Téléchargement du contenu de l\'article...',
                'article_title': best_match.get('title', ''),
                'similarity_score': percentage,
                'source_site': best_match.get('logo', 'inconnu')
            })
            
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

            # Mettre à jour l'étape de génération PDF
            self.db.update_job_data(job_id, {
                'search_terms': query,
                'extracted_title': title,
                'current_step': 'generating_pdf',
                'step_description': 'Génération du PDF en cours...',
                'article_title': best_match.get('title', ''),
                'similarity_score': percentage,
                'source_site': best_match.get('logo', 'inconnu'),
                'content_length': len(html_content)
            })

            pdf_path, html_path = self.pdf_service.generate_pdf(html_content, query_, job_id)
            
            # Étape 6: Sauvegarder dans la BDD
            site_source = urlp.urlparse(url).netloc
            
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
            
            # Nettoyer les screenshots de debug maintenant que le job est terminé
            self._cleanup_job_screenshots(job_id)
            
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
            # Gestion sécurisée des erreurs avec caractères Unicode
            error_message = str(e).encode('utf-8', errors='replace').decode('utf-8')
            logger.error(f"[{job_id}] Erreur scraping: {error_message}")

            # Prendre un screenshot en cas d'erreur pour le debug
            try:
                if self.browser:
                    screenshot_path = f"/root/read-scraper-api/static/debug_screenshot_{job_id}_{int(time.time())}.png"
                    self.browser.save_screenshot(screenshot_path)
                    logger.info(f"[{job_id}] Screenshot d'erreur sauvegardé: {screenshot_path}")
            except Exception as screenshot_error:
                logger.warning(f"[{job_id}] Impossible de prendre le screenshot d'erreur: {screenshot_error}")

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

