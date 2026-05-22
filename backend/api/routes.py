"""
Routes API REST pour l'application
"""
from flask import Blueprint, request, jsonify, send_file, make_response
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
import secrets
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
    def create_scrape_job():
        """Créer un nouveau job de scraping"""
        data = request.get_json()
        
        # Accepter soit une URL, soit des search_terms
        url = data.get('url', '').strip() if data else ''
        search_terms = data.get('search_terms', '').strip() if data else ''
        cookies = data.get('cookies', []) if data else []
        
        # Vérifier qu'au moins l'un des deux est fourni
        if not url and not search_terms:
            return jsonify({
                'error': 'Paramètres manquants',
                'message': 'Vous devez fournir soit une URL, soit des termes de recherche'
            }), 400
        
        # Valider le format des cookies
        if cookies and not isinstance(cookies, list):
            return jsonify({
                'error': 'Format cookies invalide',
                'message': 'Le champ cookies doit être une liste d\'objets {name, value, domain, ...}'
            }), 400
        
        # Si on a une URL, vérifier le cache
        if url:
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
        # Si pas d'URL mais des search_terms, utiliser une URL placeholder
        job_url = url if url else f"search_terms:{search_terms[:50]}"
        job_id = generate_id(12)
        
        if not db.create_job(job_id, job_url):
            return jsonify({
                'error': 'Erreur création job',
                'message': 'Impossible de créer le job de scraping'
            }), 500
        
        # Stocker les cookies et search_terms dans les données du job
        job_data = {}
        if search_terms:
            job_data['custom_search_terms'] = search_terms
        if cookies:
            job_data['user_cookies'] = cookies
        if job_data:
            db.update_job_data(job_id, job_data)
        
        logger.info(f"Job créé: {job_id} - URL: {url or '(termes de recherche uniquement)'}, search_terms: {search_terms or '(extraction automatique)'}")
        
        return jsonify({
            'job_id': job_id,
            'status': 'pending',
            'url': url or None,
            'search_terms': search_terms or None,
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
    
    # Route pour supprimer un article (et son PDF associé)
    @api_bp.route('/article/<article_id>', methods=['DELETE'])
    @auth.require_api_key
    def delete_article(article_id):
        """Supprimer un article et son fichier PDF associé"""
        article = db.get_article(article_id)
        
        if not article:
            return jsonify({
                'error': 'Article introuvable',
                'message': f'L\'article {article_id} n\'existe pas'
            }), 404
            
        # 1. Supprimer le fichier PDF si présent
        pdf_path_str = article.get('pdf_path')
        if pdf_path_str:
            try:
                pdf_path = Path(resolve_pdf_path(pdf_path_str))
                
                if pdf_path.exists():
                    pdf_path.unlink()
                    logger.info(f"Fichier PDF supprimé: {pdf_path}")
            except Exception as e:
                logger.warning(f"Impossible de supprimer le PDF {pdf_path_str}: {e}")
                
        # 2. Mettre à jour les jobs associés
        try:
            conn = db.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE scraping_jobs 
                SET article_id = NULL, status = 'failed', 
                    error_message = 'Article supprimé par l\\'utilisateur' 
                WHERE article_id = ?
            """, (article_id,))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Impossible de mettre à jour les jobs associés: {e}")
            
        # 3. Supprimer de la BDD
        success = db.delete_article(article_id)
        
        if success:
            logger.info(f"Article {article_id} supprimé de la base de données")
            return jsonify({
                'message': f'Article {article_id} supprimé avec succès',
                'article_id': article_id
            })
        else:
            return jsonify({
                'error': 'Erreur suppression',
                'message': 'Impossible de supprimer l\'article de la base de données'
            }), 500
    
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
        
        pdf_path_str = article['pdf_path']
        
        pdf_path = Path(resolve_pdf_path(pdf_path_str))
        
        if not pdf_path.exists():
            logger.error(f"PDF introuvable: {pdf_path} (chemin original: {pdf_path_str})")
            return jsonify({
                'error': 'PDF introuvable',
                'message': 'Le fichier PDF n\'existe pas sur le serveur'
            }), 404
        
        response = make_response(send_file(str(pdf_path), mimetype='application/pdf'))
        response.headers['Content-Disposition'] = f'inline; filename="{pdf_path.name}"'
        return response

    # Route pour obtenir une clé API temporaire (pour les utilisateurs anonymes)
    @api_bp.route('/get-temp-key', methods=['GET'])
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
    @auth.require_api_key
    def list_articles():
        """Lister les articles avec pagination et recherche"""
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        search = request.args.get('search', None)
        site_source = request.args.get('site_source', None)
        
        articles = db.list_articles(limit=limit, offset=offset, 
                                   search=search, site_source=site_source)
        
        # Ne pas retourner le contenu HTML complet pour réduire la taille de la réponse
        # Le contenu HTML peut être récupéré via /api/v1/article/{article_id} si nécessaire
        articles_summary = []
        for article in articles:
            article_summary = {
                'id': article.get('id'),
                'title': article.get('title'),
                'url': article.get('url'),
                'site_source': article.get('site_source'),
                'created_at': article.get('created_at'),
                'scraped_at': article.get('scraped_at'),
                'pdf_path': article.get('pdf_path'),
                'status': article.get('status'),
                # Ne pas inclure html_content, tags, metadata pour réduire la taille
                'has_content': bool(article.get('html_content'))
            }
            articles_summary.append(article_summary)
        
        return jsonify({
            'articles': articles_summary,
            'total': len(articles_summary),
            'limit': limit,
            'offset': offset
        })
    
    # Route de recherche
    @api_bp.route('/search', methods=['GET'])
    @auth.require_api_key
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
    
    # Route pour annuler un job en cours
    @api_bp.route('/job/<job_id>/cancel', methods=['POST'])
    @auth.require_api_key
    def cancel_job(job_id):
        """Annuler un job en attente ou en cours de traitement"""
        job = db.get_job(job_id)
        
        if not job:
            return jsonify({
                'error': 'Job introuvable',
                'message': f'Le job {job_id} n\'existe pas'
            }), 404
        
        current_status = job['status']
        
        # On peut annuler seulement les jobs en attente ou en cours de traitement
        if current_status in ['pending', 'processing']:
            success = db.update_job_status(job_id, 'cancelled', error='Job annulé par l\'utilisateur')
            
            if success:
                logger.info(f"Job {job_id} annulé avec succès (statut précédent: {current_status})")
                return jsonify({
                    'message': f'Job {job_id} annulé avec succès',
                    'previous_status': current_status,
                    'new_status': 'cancelled'
                })
            else:
                return jsonify({
                    'error': 'Erreur annulation',
                    'message': 'Impossible d\'annuler le job'
                }), 500
        
        return jsonify({
            'error': 'Impossible d\'annuler',
            'message': f'Le job {job_id} ne peut pas être annulé (statut actuel: {current_status}). Seuls les jobs en attente ou en cours peuvent être annulés.'
        }), 400

    # Route pour rejeter un article (supprimer l'article associé au job)
    @api_bp.route('/job/<job_id>/reject', methods=['POST'])
    @auth.require_api_key
    def reject_job(job_id):
        """Rejeter et supprimer un article associé à un job"""
        job = db.get_job(job_id)
        
        if not job:
            return jsonify({
                'error': 'Job introuvable',
                'message': f'Le job {job_id} n\'existe pas'
            }), 404
        
        article_id = job.get('article_id')
        
        if not article_id:
            return jsonify({
                'error': 'Aucun article associé',
                'message': f'Le job {job_id} n\'a pas d\'article associé à rejeter'
            }), 400
        
        # Récupérer l'article pour obtenir le chemin du PDF
        article = db.get_article(article_id)
        
        if not article:
            return jsonify({
                'error': 'Article introuvable',
                'message': f'L\'article {article_id} associé au job n\'existe pas'
            }), 404
        
        # Supprimer le fichier PDF si il existe
        pdf_path_str = article.get('pdf_path')
        if pdf_path_str:
            try:
                pdf_path = Path(resolve_pdf_path(pdf_path_str))
                
                if pdf_path.exists():
                    pdf_path.unlink()
                    logger.info(f"Fichier PDF supprimé: {pdf_path}")
            except Exception as e:
                logger.warning(f"Impossible de supprimer le PDF {pdf_path_str}: {e}")
                # On continue quand même la suppression de l'article
        
        # Supprimer l'article de la base de données
        success = db.delete_article(article_id)
        
        if success:
            logger.info(f"Article {article_id} rejeté et supprimé (job: {job_id})")
            return jsonify({
                'message': f'Article {article_id} rejeté et supprimé avec succès',
                'job_id': job_id,
                'article_id': article_id
            })
        else:
            return jsonify({
                'error': 'Erreur suppression',
                'message': 'Impossible de supprimer l\'article'
            }), 500

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
                elif name_without_ext.startswith('after_input_'):
                    screenshot_type = 'after_input'
                    remaining = name_without_ext.replace('after_input_', '', 1)
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
            
            # Limiter le nombre de screenshots retournés pour éviter les problèmes de taille
            # Par défaut, retourner seulement les 50 plus récents
            limit = request.args.get('limit', 50, type=int)
            screenshots_limited = screenshots[:limit]

            return jsonify({
                'screenshots': screenshots_limited,
                'total': len(screenshots),
                'returned': len(screenshots_limited),
                'limit': limit
            })

        except Exception as e:
            logger.error(f"Erreur lors de la récupération des screenshots: {e}")
            return jsonify({
                'error': 'Erreur serveur',
                'message': str(e)
            }), 500

    # Route pour enregistrer un device et obtenir une clé API permanente
    @api_bp.route('/register', methods=['POST'])
    def register_device():
        """Enregistrer un device et générer une clé API permanente"""
        data = request.get_json()

        if not data or not data.get('device_id'):
            return jsonify({
                'error': 'device_id manquant',
                'message': 'Vous devez fournir un device_id dans le body JSON'
            }), 400

        device_id = data['device_id'].strip()

        if not device_id:
            return jsonify({
                'error': 'device_id vide',
                'message': 'Le device_id ne peut pas être vide'
            }), 400

        # Vérifier si ce device_id a déjà une clé API active
        existing_key = db.get_api_key_by_device(device_id)
        if existing_key:
            return jsonify({
                'error': 'Device déjà enregistré',
                'message': 'Ce device_id possède déjà une clé API active. Utilisez-la ou révoquez-la d\'abord.'
            }), 409

        # Générer une clé API permanente sécurisée
        raw_key = f"pk_{secrets.token_hex(32)}"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

        # Stocker la clé dans la base (name = device_id pour traçabilité)
        if db.create_api_key(key_hash, name=f"device:{device_id}", is_admin=False):
            logger.info(f"Device enregistré: {device_id}")
            return jsonify({
                'api_key': raw_key,
                'device_id': device_id,
                'message': 'Clé API permanente générée avec succès. Conservez-la, elle ne sera plus affichée.'
            }), 201

        return jsonify({
            'error': 'Erreur création clé',
            'message': 'Impossible de créer la clé API'
        }), 500

    return api_bp

