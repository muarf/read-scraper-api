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
from web_scraper.europresse_login import login_to_europresse_bnf
from web_scraper.europresse_search import search_europresse_target
from web_scraper.europresse_download import download_europresse_article, sanitize_filename
from web_scraper.extract_title import extract_title, extract_metadata
from common.utils import generate_id, file_exists, NoResultException, KeywordsNeededException
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
        self._cookies = []
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
        """S'assurer que le navigateur est initialisé (seulement si pas de cookies utilisateur)"""
        # Si on a déjà des cookies utilisateur, pas besoin du navigateur
        if self._cookies and len(self._cookies) > 0:
            return
        if not self._browser_initialized:
            logger.info("Initialisation lazy du navigateur")
            self._init_browser()
            self._browser_initialized = True

    def _update_ophirofox(self):
        """Mise à jour automatique des scripts Ophirofox via Git"""
        try:
            import subprocess
            op_path = Path(__file__).resolve().parent.parent.parent / "web_scraper" / "ophirofox"
            if op_path.exists() and (op_path / ".git").exists():
                logger.info("[OPHIROFOX] Mise à jour des scripts via git pull...")
                subprocess.run(["git", "pull"], cwd=str(op_path), check=True, capture_output=True)
                logger.info("[OPHIROFOX] Scripts mis à jour avec succès.")
            else:
                logger.warning(f"[OPHIROFOX] Dossier git introuvable à {op_path}, mise à jour impossible.")
        except Exception as e:
            logger.warning(f"[OPHIROFOX] Erreur lors de la mise à jour : {e}")

    def _ensure_login(self):
        """S'assurer qu'on est connecté à Europresse"""
        if not hasattr(self, '_logged_in') or not self._logged_in:
            logger.info("Connexion à Europresse...")
            self._login()
            self._logged_in = True

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
        import platform
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
        
        # Liste des chemins de drivers à tenter
        drivers_to_try = [CHROMEDRIVER_PATH]
        
        # Sur ARM64 (aarch64), si Chromium est un Snap, privilégier le binaire DIRECT
        # pour éviter les erreurs de confinement Snap (Status code 1)
        if platform.machine() == 'aarch64':
            direct_snap_driver = "/snap/chromium/current/usr/lib/chromium-browser/chromedriver"
            wrapper_snap_driver = "/snap/bin/chromium.chromedriver"
            
            # Ajouter le binaire direct en PREMIER
            if os.path.exists(direct_snap_driver):
                drivers_to_try.insert(0, direct_snap_driver)
                logger.info(f"[BROWSER_INIT] ARM64: Priorité au binaire Snap DIRECT: {direct_snap_driver}")
            elif os.path.exists(wrapper_snap_driver):
                drivers_to_try.insert(0, wrapper_snap_driver)
                logger.info(f"[BROWSER_INIT] ARM64: Utilisation du wrapper Snap: {wrapper_snap_driver}")

        last_exception = None
        for driver_path in drivers_to_try:
            try:
                logger.info(f"[BROWSER_INIT] Tentative avec le pilote: {driver_path}")
                from selenium.webdriver.chrome.service import Service
                service = Service(executable_path=driver_path)
                self.browser = webdriver.Chrome(service=service, options=chrome_options)
                logger.info(f"[BROWSER_INIT] Succès avec {driver_path}")
                return # Succès !
            except Exception as e:
                logger.warning(f"[BROWSER_INIT] Échec avec {driver_path}: {e}")
                last_exception = e
        
        # Tentative de repli via chromedriver-autoinstaller si tout a échoué
        logger.info("[BROWSER_INIT] Tentatives directes échouées, essai via chromedriver-autoinstaller...")
        try:
            import chromedriver_autoinstaller
            autopath = chromedriver_autoinstaller.install()
            if autopath:
                from selenium.webdriver.chrome.service import Service
                service = Service(executable_path=autopath)
                self.browser = webdriver.Chrome(service=service, options=chrome_options)
                logger.info(f"[BROWSER_INIT] Succès via autoinstaller: {autopath}")
                return
            else:
                logger.error("[BROWSER_INIT] Autoinstaller n'a pas retourné de chemin valide.")
        except Exception as e2:
            logger.error(f"[BROWSER_INIT] Échec de l'autoinstaller: {e2}")
            # On garde l'exception initiale si l'autoinstaller échoue aussi
        
        if last_exception:
            raise last_exception
        else:
            raise Exception("Impossible d'initialiser le navigateur Chrome (toutes les méthodes ont échoué)")
    
    def _login(self, user_cookies=None):
        """
        Se connecter à Europresse via EZProxy BnF.
        Si user_cookies est fourni, les utiliser directement (cookie-relay depuis l'app).
        Sinon, faire le login BnF avec les credentials .env.
        """
        if user_cookies and len(user_cookies) > 0:
            logger.info(f"[LOGIN] Utilisation des cookies utilisateur ({len(user_cookies)} cookies)")
            self._cookies = user_cookies
            return

        try:
            logger.info("[LOGIN] Début connexion BnF CAS (credentials .env)")
            logger.info(f"[LOGIN] Navigateur: {self.browser}")
            _, cookies = login_to_europresse_bnf(None, None, self.browser, USERNAME, PASSWORD, "bg_session")
            if cookies:
                self._cookies = cookies
                logger.info("[LOGIN] Connexion BnF réussie, cookies extraits")
            else:
                logger.warning("[LOGIN] Connexion BnF échouée, pas de cookies retournés")
            logger.info(f"[LOGIN] Navigateur après connexion: {self.browser}")
            self.browser.quit()
            self.browser = None
            self._browser_initialized = False
        except Exception as e:
            logger.warning(f"[LOGIN] Erreur connexion BnF, on continue: {e}")


    def _get_browser(self):
        """Récupérer ou initialiser le navigateur"""
        logger.info(f"[BROWSER] Vérification navigateur existant: {self.browser is not None}")
        if self.browser is None:
            logger.info("[BROWSER] Aucun navigateur, initialisation...")
            self._init_browser()
            logger.info(f"[BROWSER] Navigateur initialisé: {self.browser is not None}")
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
        # S'assurer que le navigateur est initialisé
        self._ensure_browser()

        try:
            logger.info(f"[{job_id}] === DÉBUT DU SCRAPING ===")
            logger.info(f"[{job_id}] URL: {url}")

            browser = None  # Navigateur potentiel pour l'extraction du titre

            # Vérifier si des termes de recherche personnalisés ont été fournis
            job = self.db.get_job(job_id)
            if job and job.get('status') == 'completed':
                self._cleanup_job_screenshots(job_id)
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
            
            # Utiliser le navigateur déjà initialisé
            browser = self.browser

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
                # Étape 1: Extraire le titre (utilise le navigateur initialisé mais pas encore connecté)
                logger.info(f"[{job_id}] === ÉTAPE 1: Extraction du titre ===")
                logger.info(f"[{job_id}] Appel de extract_title pour URL: {url}")
                
                # Mettre à jour l'étape actuelle
                self.db.update_job_data(job_id, {
                    'current_step': 'extracting_title',
                    'step_description': 'Analyse de l\'URL et extraction du titre...'
                })
                
                # Utiliser le navigateur déjà initialisé pour extraire le titre et la date du site source
                browser = self.browser
                result = extract_metadata(url, browser)
                logger.info(f"[{job_id}] Résultat extract_metadata Ophirofox: {result}")

                if result is None or not result[0]:
                    error_msg = f"Impossible d'extraire des mots-clés de l'URL {url} via Ophirofox. Veuillez essayer en fournissant directement des mots-clés de recherche."
                    logger.error(f"[{job_id}] {error_msg}")
                    raise KeywordsNeededException(error_msg)

                query, title, published_date = result
                logger.info(f"[{job_id}] Titre: '{title}', Date: '{published_date}', Query: '{query}'")
                
                # Stocker la date dans les données du job pour Europresse
                if published_date:
                    self.db.update_job_data(job_id, {'published_date': published_date})

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

            # Étape 3: Recherche sur Europresse HttpRequest
            logger.info(f"[{job_id}] === ÉTAPE 3: Recherche Europresse HTTP ===")

            # Récupérer les cookies utilisateur si fournis (cookie-relay depuis l'app)
            user_cookies = job_data.get('user_cookies', [])

            # S'assurer d'être connecté à Europresse (CAS BnF) AVANT la recherche
            logger.info(f"[{job_id}] Appel de _ensure_login...")
            self._ensure_login(user_cookies=user_cookies if user_cookies else None)
            logger.info(f"[{job_id}] _ensure_login terminé. Cookies présents: {len(self._cookies) > 0}")

            try:
                # Mettre à jour les données du job avec l'étape actuelle
                self.db.update_job_data(job_id, {
                    'search_terms': query,
                    'extracted_title': title,
                    'current_step': 'searching',
                    'step_description': 'Recherche d\'articles similaires en cours...'
                })
            except Exception as ss_error:
                logger.warning(f"[{job_id}] Erreur update state: {ss_error}")

            logger.info(f"[{job_id}] ENVOI À LA RECHERCHE HTTP - Query: '{query}' (len={len(query)}), Title: '{title[:50]}...'")
            
            # Récupérer la date de publication si disponible
            published_date = job_data.get('published_date')
            
            articles = search_europresse_target(None, None, self._cookies, query, title, job_id, published_date)
            logger.info(f"[{job_id}] Résultat recherche ({len(articles) if articles else 0} résultats)")
            
            if not articles:
                logger.warning(f"[{job_id}] Liste d'articles vide après search_europresse_target")

            # Mettre à jour les données de debug avec les résultats de recherche
            if articles and isinstance(articles, list) and len(articles) > 0:
                # Calculer les statistiques de recherche
                total_articles = len(articles)
                try:
                    best_match = max(articles, key=lambda x: x.get('percentage', 0))
                except (ValueError, TypeError):
                    best_match = articles[0]

                self.db.update_job_data(job_id, {
                    'search_results_count': total_articles,
                    'best_match_title': best_match.get('title') if best_match else None,
                    'best_match_percentage': best_match.get('percentage', 0) if best_match else 0,
                    'best_match_source': best_match.get('logo') if best_match else None
                })
            else:
                articles = None
                best_match = None

            if not articles:
                logger.warning(f"[{job_id}] Aucun résultat retourné de HTTP search.")
                raise NoResultException("Aucun résultat trouvé pour cet article")
            
            results_data = articles
            
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
                'www.lesjours.fr': 'les jours',
                'lesjours.fr': 'les jours',
                'www.leparisien.fr': 'le parisien',
                'leparisien.fr': 'le parisien',
                'www.lexpress.fr': 'l\'express',
                'lexpress.fr': 'l\'express',
                'www.lefigaro.fr': 'le figaro',
                'lefigaro.fr': 'le figaro',
            }
            
            source_key = None
            for domain, source in site_mapping.items():
                if domain in site_domain:
                    source_key = source
                    break
            
            # Scoring intelligent : Combiner similarité, longueur et correspondance de source
            scored_results = []
            for result in results_data:
                logo_lower = result.get('logo', '').lower()
                similarity = result.get('percentage', 0)
                length = result.get('length', 0)
                
                # Bonus pour la correspondance de source
                source_bonus = 0
                if source_key and (source_key in logo_lower or logo_lower in source_key):
                    source_bonus = 30
                    logger.info(f"[{job_id}] Bonus source (+30) pour: {logo_lower}")
                
                # Bonus pour la longueur (max 20 points pour 2000 mots)
                length_bonus = min(20, (length / 100))
                
                total_score = similarity + source_bonus + length_bonus
                result['total_score'] = total_score
                scored_results.append(result)
            
            # Trier par le score total
            scored_results = sorted(scored_results, key=lambda x: x['total_score'], reverse=True)
            
            if scored_results:
                best_match = scored_results[0]
                logger.info(f"[{job_id}] Meilleur match sélectionné: {best_match.get('title')} (Score: {best_match['total_score']:.1f}, %: {best_match['percentage']}, Source: {best_match.get('logo')})")
            else:
                logger.warning(f"[{job_id}] Aucun résultat retourné après scoring.")
                raise NoResultException("Aucun résultat trouvé pour cet article")
            
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
            
            # Étape 4: Télécharger le contenu de l'article HTTP
            logger.info(f"[{job_id}] Téléchargement du contenu (HTTP)...")
            html_content = download_europresse_article(None, None, link, self._cookies, job_id)

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
                    screenshot_path = STATIC_DIR / f"debug_screenshot_{job_id}_{int(time.time())}.png"
                    self.browser.save_screenshot(str(screenshot_path))
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

