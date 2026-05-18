"""
Service de scraping Europresse utilisant les cookies BnF de l'utilisateur.
Pas de Selenium — tout passe par requests + BeautifulSoup.
"""
import os
import sys
import time
import json
import requests
from pathlib import Path
from bs4 import BeautifulSoup
from datetime import datetime
from backend.models.database import Database
from backend.config.settings import STATIC_DIR, USERNAME, PASSWORD
from backend.services.pdf_service import PDFService
from common.utils import generate_id, NoResultException, KeywordsNeededException
import logging
import re

logger = logging.getLogger(__name__)

EUROPRESSE_DOMAIN = "nouveau-europresse-com.bnf.idm.oclc.org"
EUROPRESSE_BASE = f"https://{EUROPRESSE_DOMAIN}"


def sanitize_filename(filename):
    return re.sub(r'[^a-zA-Z0-9_-]', '-', filename)


def cookies_to_session(cookies_list):
    """Convertit une liste de cookies [{name, value, domain, ...}] en requests.Session"""
    session = requests.Session()
    for cookie in cookies_list:
        domain = cookie.get('domain', EUROPRESSE_DOMAIN)
        session.cookies.set(cookie['name'], cookie['value'], domain=domain)
    return session


def search_europresse(session, query, max_results=10):
    """Recherche sur Europresse via HTTP requests avec les cookies de session."""
    search_url = f"{EUROPRESSE_BASE}/Search/Result"

    params = {
        'searchTerms': query,
        'page': 1,
        'pageSize': max_results,
    }

    logger.info(f"Recherche Europresse: {query}")
    resp = session.get(search_url, params=params, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, 'html.parser')

    results = []
    # Parser les résultats de recherche
    for item in soup.select('.result-item, .search-result, [class*="result"]'):
        title_el = item.select_one('.title, .result-title, h3, h2')
        link_el = item.select_one('a[href]')
        if title_el and link_el:
            title = title_el.get_text(strip=True)
            href = link_el.get('href', '')
            if href and not href.startswith('http'):
                href = EUROPRESSE_BASE + href
            results.append({'title': title, 'url': href})

    # Fallback : chercher les liens de documents
    if not results:
        for link in soup.find_all('a', href=True):
            href = link['href']
            if 'Document' in href or 'docKey' in href:
                title = link.get_text(strip=True)
                if title:
                    if not href.startswith('http'):
                        href = EUROPRESSE_BASE + href
                    results.append({'title': title, 'url': href})

    logger.info(f"Trouvé {len(results)} résultats")
    return results


def download_europresse_article(session, doc_url_or_id, save_dir=None):
    """Télécharge un article Europresse via HTTP requests."""
    if save_dir is None:
        save_dir = str(STATIC_DIR)

    os.makedirs(save_dir, exist_ok=True)

    # Construire l'URL du document
    if doc_url_or_id.startswith('http'):
        url = doc_url_or_id
    else:
        url = f"{EUROPRESSE_BASE}/Document/ViewMobile?docKey={doc_url_or_id}&fromBasket=false&viewEvent=1&invoiceCode="

    logger.info(f"Téléchargement article: {url}")
    resp = session.get(url, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, 'html.parser')

    # Extraire le titre
    title = ''
    title_el = soup.find('title') or soup.select_one('h1, .article-title, .doc-title')
    if title_el:
        title = title_el.get_text(strip=True)

    # Extraire le contenu
    content = ''
    content_el = soup.select_one('.article-content, .doc-content, #content, .content, article, main')
    if content_el:
        content = str(content_el)
    else:
        content = resp.text

    # Sauvegarder le HTML
    article_id = generate_id(12)
    html_path = os.path.join(save_dir, f"{article_id}.html")
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(f"<html><head><title>{title}</title></head><body>{content}</body></html>")

    logger.info(f"Article sauvegardé: {html_path}")

    return {
        'id': article_id,
        'title': title,
        'html_path': html_path,
        'url': url,
    }


class ScraperService:
    """Service de scraping Europresse sans Selenium — utilise les cookies BnF de l'utilisateur."""

    def __init__(self, db: Database, pdf_service: PDFService):
        self.db = db
        self.pdf_service = pdf_service

    def process_job(self, job_id: str):
        """Traite un job de scraping."""
        job = self.db.get_job(job_id)
        if not job:
            logger.error(f"Job {job_id} introuvable")
            return

        self.db.update_job_status(job_id, 'processing')
        logger.info(f"Traitement job {job_id}")

        try:
            # Récupérer les cookies et search_terms du job
            job_data = {}
            if job.get('data'):
                try:
                    job_data = json.loads(job['data'])
                except json.JSONDecodeError:
                    pass

            user_cookies = job_data.get('user_cookies', [])
            search_terms = job_data.get('custom_search_terms', '')
            url = job.get('url', '')

            if not user_cookies:
                raise Exception("Pas de cookies BnF — l'utilisateur doit se connecter à Europresse dans l'app")

            session = cookies_to_session(user_cookies)

            # Si c'est une URL Europresse, télécharger directement
            # Sinon, rechercher d'abord par titre
            is_europresse = EUROPRESSE_DOMAIN in url or url.startswith(EUROPRESSE_BASE)
            if url and is_europresse:
                self.db.update_job_status(job_id, 'processing')
                article = download_europresse_article(session, url)
            else:
                # URL d'un site de presse → extraire le titre et rechercher sur Europresse
                if not search_terms:
                    # Extraire un terme de recherche depuis l'URL (le slug de l'article)
                    from urllib.parse import urlparse
                    path = urlparse(url).path
                    # Prendre le dernier segment du path (le slug)
                    slug = path.rstrip('/').split('/')[-1] if path else ''
                    # Nettoyer : enlever l'extension .php/.html, remplacer les tirets par des espaces
                    search_terms = re.sub(r'\.(php|html|htm|asp)$', '', slug)
                    search_terms = search_terms.replace('-', ' ').replace('_', ' ')
                    # Limiter à 80 chars
                    search_terms = search_terms[:80].strip()
                    logger.info(f"Search terms extraits de l'URL: {search_terms}")
                if not search_terms:
                    raise Exception("Pas de termes de recherche ni d'URL Europresse")

                self.db.update_job_status(job_id, 'processing')
                results = search_europresse(session, search_terms)

                if not results:
                    raise NoResultException(f"Aucun résultat pour: {search_terms}")

                # Prendre le premier résultat
                first = results[0]
                self.db.update_job_status(job_id, 'processing')
                article = download_europresse_article(session, first['url'])

            # Générer le PDF
            self.db.update_job_status(job_id, 'processing')
            pdf_path = ''
            html_path = article.get('html_path', '')
            if html_path and os.path.exists(html_path):
                html_content = open(html_path, encoding='utf-8').read()
                pdf_result = self.pdf_service.generate_pdf(html_content, article.get('url', ''), article['id'])
                if isinstance(pdf_result, tuple):
                    pdf_path = pdf_result[0] if pdf_result else ''
                else:
                    pdf_path = str(pdf_result) if pdf_result else ''

            # Sauvegarder l'article en BDD
            article_id = article['id']
            self.db.create_article(
                article_id=article_id,
                url=article.get('url', url),
                title=article.get('title', search_terms or url),
                html_content=open(html_path, encoding='utf-8').read() if html_path and os.path.exists(html_path) else '',
                pdf_path=pdf_path or '',
                site_source='europresse'
            )

            self.db.update_job_status(job_id, 'completed', article_id=article_id)
            logger.info(f"Job {job_id} terminé — article {article_id}")
            return article_id, article

        except NoResultException as e:
            logger.warning(f"Job {job_id}: {e}")
            self.db.update_job_status(job_id, 'failed', error=str(e))
        except Exception as e:
            logger.error(f"Job {job_id} erreur: {e}", exc_info=True)
            self.db.update_job_status(job_id, 'failed', error=str(e))
