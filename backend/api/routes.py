"""
Routes API REST pour l'application
"""
from flask import Blueprint, request, jsonify, send_file
from pathlib import Path
import json
from backend.models.database import Database
from backend.services.cache_service import CacheService
from backend.services.queue_manager import QueueManager
from backend.middleware.auth import AuthMiddleware
from backend.middleware.rate_limiter import RateLimiter
from backend.config.settings import STATIC_DIR, API_PREFIX
from common.utils import generate_id
import hashlib
import logging

logger = logging.getLogger(__name__)


def create_api_blueprint(db: Database, cache_service: CacheService, queue_manager: QueueManager):
    """Créer le blueprint API"""
    
    api_bp = Blueprint('api', __name__, url_prefix=API_PREFIX)
    
    auth = AuthMiddleware(db)
    rate_limiter = RateLimiter()
    
    # Route pour créer un job de scraping
    @api_bp.route('/scrape', methods=['POST'])
    @auth.require_api_key
    @rate_limiter.rate_limit
    def create_scrape_job():
        """Créer un nouveau job de scraping"""
        data = request.get_json()
        
        if not data or 'url' not in data:
            return jsonify({
                'error': 'URL manquante',
                'message': 'Vous devez fournir une URL à scraper'
            }), 400
        
        url = data['url']
        
        # Vérifier le cache
        cached_article = cache_service.is_cached(url)
        if cached_article:
            logger.info(f"Cache hit pour URL: {url}")
            return jsonify({
                'job_id': None,
                'status': 'completed',
                'article_id': cached_article['id'],
                'cached': True
            })
        
        # Créer un nouveau job
        job_id = generate_id(12)
        
        if not db.create_job(job_id, url):
            return jsonify({
                'error': 'Erreur création job',
                'message': 'Impossible de créer le job de scraping'
            }), 500
        
        logger.info(f"Job créé: {job_id} pour URL: {url}")
        
        return jsonify({
            'job_id': job_id,
            'status': 'pending',
            'url': url,
            'message': 'Job de scraping créé avec succès'
        }), 201
    
    # Route pour obtenir le statut d'un job
    @api_bp.route('/job/<job_id>', methods=['GET'])
    @auth.require_api_key
    def get_job_status(job_id):
        """Obtenir le statut d'un job"""
        job = db.get_job(job_id)
        
        if not job:
            return jsonify({
                'error': 'Job introuvable',
                'message': f'Le job {job_id} n\'existe pas'
            }), 404
        
        response_data = {
            'id': job['id'],
            'url': job['url'],
            'status': job['status'],
            'created_at': job['created_at'],
            'started_at': job.get('started_at'),
            'completed_at': job.get('completed_at'),
            'error_message': job.get('error_message')
        }

        # Ajouter les données JSON si elles existent
        if job.get('data'):
            try:
                job_data = json.loads(job['data'])
                response_data.update(job_data)
            except json.JSONDecodeError:
                pass  # Ignore les données JSON invalides
        
        if job['article_id']:
            response_data['article_id'] = job['article_id']
        
        return jsonify(response_data)
    
    # Route pour obtenir un article
    @api_bp.route('/article/<article_id>', methods=['GET'])
    @auth.require_api_key
    def get_article(article_id):
        """Obtenir un article par son ID"""
        article = db.get_article(article_id)
        
        if not article:
            return jsonify({
                'error': 'Article introuvable',
                'message': f'L\'article {article_id} n\'existe pas'
            }), 404
        
        return jsonify({
            'id': article['id'],
            'url': article['url'],
            'title': article['title'],
            'html_content': article['html_content'],
            'pdf_path': article['pdf_path'],
            'site_source': article['site_source'],
            'created_at': article['created_at'],
            'scraped_at': article['scraped_at']
        })
    
    # Route pour télécharger le PDF
    @api_bp.route('/article/<article_id>/pdf', methods=['GET'])
    @auth.require_api_key
    def download_pdf(article_id):
        """Télécharger le PDF d'un article"""
        article = db.get_article(article_id)
        
        if not article:
            return jsonify({
                'error': 'Article introuvable',
                'message': f'L\'article {article_id} n\'existe pas'
            }), 404
        
        pdf_path = Path(article['pdf_path'])
        
        if not pdf_path.exists():
            return jsonify({
                'error': 'PDF introuvable',
                'message': 'Le fichier PDF n\'existe pas sur le serveur'
            }), 404
        
        return send_file(str(pdf_path), mimetype='application/pdf')

    # Route pour obtenir une clé API temporaire (pour les utilisateurs anonymes)
    @api_bp.route('/get-temp-key', methods=['GET'])
    @rate_limiter.rate_limit
    def get_temp_api_key():
        """Générer une clé API temporaire pour les utilisateurs anonymes"""
        from datetime import datetime, timedelta

        # Générer une clé temporaire (valide 24h)
        temp_key = f"temp_{generate_id(16)}"
        temp_key_hash = hashlib.sha256(temp_key.encode()).hexdigest()

        # Créer la clé dans la base (expire dans 24h)
        expires_at = datetime.now() + timedelta(hours=24)

        if db.create_temp_api_key(temp_key_hash, expires_at):
            return jsonify({
                'api_key': temp_key,
                'expires_in': 86400,  # 24h en secondes
                'message': 'Clé API temporaire créée (valide 24h)'
            })

        return jsonify({
            'error': 'Erreur création clé temporaire',
            'message': 'Impossible de créer une clé API temporaire'
        }), 500

    # Route pour lister les articles (publique pour le frontend)
    @api_bp.route('/articles', methods=['GET'])
    @rate_limiter.rate_limit
    def list_articles():
        """Lister les articles avec pagination et recherche"""
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        search = request.args.get('search', None)
        site_source = request.args.get('site_source', None)
        
        articles = db.list_articles(limit=limit, offset=offset, 
                                   search=search, site_source=site_source)
        
        return jsonify({
            'articles': articles,
            'total': len(articles),
            'limit': limit,
            'offset': offset
        })
    
    # Route de recherche
    @api_bp.route('/search', methods=['GET'])
    @auth.require_api_key
    @rate_limiter.rate_limit
    def search_articles():
        """Rechercher dans les articles"""
        query = request.args.get('q')
        
        if not query:
            return jsonify({
                'error': 'Requête manquante',
                'message': 'Vous devez fournir un paramètre de recherche \'q\''
            }), 400
        
        articles = db.list_articles(limit=50, search=query)
        
        return jsonify({
            'articles': articles,
            'query': query,
            'total': len(articles)
        })

    # Route pour lister les screenshots de debug
    @api_bp.route('/debug/screenshots', methods=['GET'])
    @auth.require_api_key
    def list_debug_screenshots():
        """Lister les screenshots de debug disponibles"""
        try:
            import glob
            import os
            from datetime import datetime

            # Chercher tous les fichiers de debug dans static (au niveau racine du projet)
            static_dir = Path(__file__).resolve().parent.parent.parent / "static"
            debug_pattern = str(static_dir / "debug_*.png")
            debug_files = glob.glob(debug_pattern)

            screenshots = []
            for file_path in debug_files:
                filename = os.path.basename(file_path)
                # Extraire les informations du nom de fichier
                # Format: debug_TYPE_JOBID_TIMESTAMP.png
                name_without_ext = filename.replace('debug_', '').replace('.png', '')

                # Identifier le type (peut contenir des underscores)
                if name_without_ext.startswith('before_search_'):
                    screenshot_type = 'before_search'
                    remaining = name_without_ext.replace('before_search_', '', 1)
                elif name_without_ext.startswith('search_failed_'):
                    screenshot_type = 'search_failed'
                    remaining = name_without_ext.replace('search_failed_', '', 1)
                elif name_without_ext.startswith('screenshot_'):
                    screenshot_type = 'screenshot'
                    remaining = name_without_ext.replace('screenshot_', '', 1)
                else:
                    # Type inconnu, passer ce fichier
                    logger.warning(f"Type de screenshot inconnu: {filename}")
                    continue

                # Extraire job_id et timestamp du reste
                parts = remaining.rsplit('_', 1)  # Split sur le dernier underscore
                if len(parts) == 2:
                    job_id = parts[0]
                    try:
                        timestamp = int(parts[1])
                    except ValueError as e:
                        logger.warning(f"Timestamp invalide dans {filename}: {parts[1]} - {e}")
                        continue

                    screenshots.append({
                        'filename': filename,
                        'url': f'/static/{filename}',
                        'path': str(file_path),
                        'type': screenshot_type,
                        'job_id': job_id,
                        'timestamp': timestamp,
                        'datetime': datetime.fromtimestamp(timestamp).isoformat(),
                        'size': os.path.getsize(file_path)
                    })
                else:
                    logger.warning(f"Format invalide pour {filename}: {remaining}")

            # Trier par date décroissante (plus récent en premier)
            screenshots.sort(key=lambda x: x['timestamp'], reverse=True)

            return jsonify({
                'screenshots': screenshots,
                'total': len(screenshots)
            })

        except Exception as e:
            logger.error(f"Erreur lors de la récupération des screenshots: {e}")
            return jsonify({
                'error': 'Erreur serveur',
                'message': str(e)
            }), 500

    return api_bp

