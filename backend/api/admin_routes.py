"""
Routes API Admin
"""
from flask import Blueprint, request, jsonify
from backend.models.database import Database
from backend.middleware.auth import AuthMiddleware
from backend.config.settings import API_PREFIX, STATIC_DIR, LOGS_DIR
from common.utils import generate_id
import hashlib
import logging
import os
import json
import glob
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


def create_admin_blueprint(db: Database, queue_control_functions=None):
    """Créer le blueprint admin"""
    
    admin_bp = Blueprint('admin', __name__, url_prefix=f'{API_PREFIX}/admin')
    
    auth = AuthMiddleware(db)
    
    # Extraire les fonctions de contrôle de la queue
    stop_queue = queue_control_functions.get('stop') if queue_control_functions else None
    start_queue_func = queue_control_functions.get('start') if queue_control_functions else None
    
    # Route pour obtenir les stats
    @admin_bp.route('/stats', methods=['GET'])
    @auth.require_api_key
    @auth.require_admin
    def get_stats():
        """Obtenir les statistiques globales"""
        # Stats par jour
        stats = db.list_articles(limit=1000)
        
        # Calculer quelques stats
        total_articles = len(stats)
        unique_sources = len(set(a.get('site_source') for a in stats if a.get('site_source')))
        
        # Jobs en cours
        jobs = db.get_pending_jobs()
        jobs_processing = [j for j in db.list_all_jobs() if j['status'] == 'processing']
        
        return jsonify({
            'total_articles': total_articles,
            'unique_sources': unique_sources,
            'pending_jobs': len(jobs),
            'processing_jobs': len(jobs_processing)
        })
    
    # Route pour lister tous les articles (admin)
    @admin_bp.route('/articles', methods=['GET'])
    @auth.require_api_key
    @auth.require_admin
    def list_all_articles():
        """Lister tous les articles (admin)"""
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        articles = db.list_articles(limit=limit, offset=offset)
        
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
                'tags': article.get('tags'),
                'metadata': article.get('metadata'),
                # Ne pas inclure html_content pour réduire la taille
                'has_content': bool(article.get('html_content')),
                'content_length': len(article.get('html_content', '')) if article.get('html_content') else 0
            }
            articles_summary.append(article_summary)
        
        return jsonify({
            'articles': articles_summary,
            'total': len(articles_summary),
            'limit': limit,
            'offset': offset
        })
    
    # Route pour supprimer un article
    @admin_bp.route('/article/<article_id>', methods=['DELETE'])
    @auth.require_api_key
    @auth.require_admin
    def delete_article(article_id):
        """Supprimer un article"""
        if not db.delete_article(article_id):
            return jsonify({
                'error': 'Erreur suppression',
                'message': 'Impossible de supprimer l\'article'
            }), 500
        
        return jsonify({
            'message': f'Article {article_id} supprimé avec succès'
        })
    
    def _collect_job_logs(job_id: str, max_entries: int = 200):
        """Récupérer les lignes de log contenant l'identifiant du job."""
        logs = []
        try:
            log_dir = Path(LOGS_DIR)
            if not log_dir.exists():
                return logs

            log_files = sorted(
                log_dir.glob('app.log*'),
                key=lambda p: p.stat().st_mtime
            )

            for log_file in log_files:
                try:
                    with log_file.open('r', encoding='utf-8', errors='replace') as fh:
                        for line in fh:
                            if f'[{job_id}]' in line:
                                logs.append(line.strip())
                except Exception as e:
                    logger.warning(f"Impossible de lire le fichier de log {log_file}: {e}")

            if len(logs) > max_entries:
                logs = logs[-max_entries:]
        except Exception as e:
            logger.error(f"Erreur collecte logs pour job {job_id}: {e}")

        return logs

    def _collect_job_screenshots(job_id: str):
        """Lister les screenshots de debug associés à un job."""
        screenshots = []
        static_dir = Path(STATIC_DIR)

        if not static_dir.exists():
            return screenshots

        pattern = static_dir / f"debug_*_{job_id}_*.png"
        for file_path in glob.glob(str(pattern)):
            try:
                filename = os.path.basename(file_path)
                name_without_ext = filename.replace('debug_', '').replace('.png', '')

                screenshot_type = 'unknown'
                remaining = name_without_ext
                type_prefixes = [
                    'before_search_',
                    'after_input_',
                    'search_failed_',
                    'screenshot_'
                ]
                for prefix in type_prefixes:
                    if remaining.startswith(prefix):
                        screenshot_type = prefix.rstrip('_')
                        remaining = remaining.replace(prefix, '', 1)
                        break

                parts = remaining.rsplit('_', 1)
                if len(parts) != 2:
                    logger.warning(f"Format de screenshot inattendu: {filename}")
                    continue

                job_part, ts_part = parts
                try:
                    timestamp = int(ts_part)
                except ValueError:
                    logger.warning(f"Timestamp invalide dans {filename}: {ts_part}")
                    continue

                if job_part != job_id:
                    continue

                screenshots.append({
                    'filename': filename,
                    'url': f'/static/{filename}',
                    'path': file_path,
                    'type': screenshot_type,
                    'job_id': job_id,
                    'timestamp': timestamp,
                    'datetime': datetime.fromtimestamp(timestamp).isoformat(),
                    'size': os.path.getsize(file_path)
                })
            except Exception as e:
                logger.warning(f"Erreur analyse screenshot {file_path}: {e}")

        screenshots.sort(key=lambda x: x['timestamp'], reverse=True)
        return screenshots
    
    # Route pour lister les jobs
    @admin_bp.route('/jobs', methods=['GET'])
    @auth.require_api_key
    @auth.require_admin
    def list_jobs():
        """Lister tous les jobs"""
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM scraping_jobs ORDER BY created_at DESC LIMIT 100")
        rows = cursor.fetchall()
        
        jobs = [dict(row) for row in rows]
        
        conn.close()
        
        return jsonify({
            'jobs': jobs,
            'total': len(jobs)
        })

    # Route pour récupérer les détails d'un job
    @admin_bp.route('/job/<job_id>', methods=['GET'])
    @auth.require_api_key
    @auth.require_admin
    def get_job_details(job_id):
        """Obtenir les détails, logs et screenshots d'un job."""
        job = db.get_job(job_id)

        if not job:
            return jsonify({
                'error': 'Job introuvable',
                'message': f'Le job {job_id} n\'existe pas'
            }), 404

        job_detail = dict(job)
        data_field = job_detail.get('data')
        parsed_data = {}
        if data_field:
            try:
                parsed_data = json.loads(data_field)
            except json.JSONDecodeError:
                parsed_data = {'raw': data_field}
        job_detail['data'] = parsed_data

        logs = _collect_job_logs(job_id)
        screenshots = _collect_job_screenshots(job_id)

        return jsonify({
            'job': job_detail,
            'logs': logs,
            'screenshots': screenshots
        })
    
    # Route pour créer une clé API
    @admin_bp.route('/apikeys', methods=['POST'])
    @auth.require_api_key
    @auth.require_admin
    def create_api_key():
        """Créer une nouvelle clé API"""
        data = request.get_json()
        
        if not data or 'name' not in data:
            return jsonify({
                'error': 'Nom manquant',
                'message': 'Vous devez fournir un nom pour la clé API'
            }), 400
        
        name = data['name']
        is_admin = data.get('is_admin', False)
        
        # Générer une clé API aléatoire
        api_key = generate_id(32)
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        
        if not db.create_api_key(key_hash, name, is_admin):
            return jsonify({
                'error': 'Erreur création clé',
                'message': 'Impossible de créer la clé API'
            }), 500
        
        return jsonify({
            'message': 'Clé API créée avec succès',
            'api_key': api_key,  # À ne montrer qu'une seule fois !
            'name': name,
            'is_admin': is_admin,
            'warning': 'Sauvegardez cette clé, elle ne sera plus affichée'
        }), 201
    
    # Route pour lister les clés API
    @admin_bp.route('/apikeys', methods=['GET'])
    @auth.require_api_key
    @auth.require_admin
    def list_api_keys():
        """Lister les clés API"""
        api_keys = db.list_api_keys()
        
        # Ne pas retourner les hash
        safe_keys = []
        for key in api_keys:
            safe_keys.append({
                'id': key['id'],
                'name': key['name'],
                'is_admin': key['is_admin'],
                'created_at': key['created_at'],
                'last_used': key['last_used'],
                'is_active': key['is_active']
            })
        
        return jsonify({
            'api_keys': safe_keys,
            'total': len(safe_keys)
        })
    
    # Route pour révoquer une clé API
    @admin_bp.route('/apikeys/<api_key_id>', methods=['DELETE'])
    @auth.require_api_key
    @auth.require_admin
    def revoke_api_key(api_key_id):
        """Révoquer une clé API"""
        if not db.revoke_api_key(api_key_id):
            return jsonify({
                'error': 'Erreur révocation',
                'message': 'Impossible de révoquer la clé API'
            }), 500
        
        return jsonify({
            'message': f'Clé API {api_key_id} révoquée avec succès'
        })
    
    # Route pour nettoyer les données anciennes
    @admin_bp.route('/cleanup', methods=['POST'])
    @auth.require_api_key
    @auth.require_admin
    def cleanup_old_data():
        """Nettoyer les données anciennes"""
        data = request.get_json() or {}
        
        days_articles = data.get('days_articles', 90)
        days_jobs = data.get('days_jobs', 7)
        days_static = data.get('days_static', 7)
        
        cleanup_result = db.cleanup_old_data(days_articles, days_jobs, days_static)
        
        return jsonify({
            'message': 'Nettoyage effectué',
            'articles_deleted': cleanup_result.get('articles_deleted', 0),
            'jobs_deleted': cleanup_result.get('jobs_deleted', 0),
            'files_deleted': cleanup_result.get('files_deleted', 0),
            'logs_deleted': cleanup_result.get('logs_deleted', 0),
            'days_articles': days_articles,
            'days_jobs': days_jobs,
            'days_static': days_static
        })
    
    # Route pour relancer un job
    @admin_bp.route('/job/<job_id>/retry', methods=['POST'])
    @auth.require_api_key
    @auth.require_admin
    def retry_job(job_id):
        """Relancer un job échoué"""
        job = db.get_job(job_id)
        
        if not job:
            return jsonify({
                'error': 'Job introuvable',
                'message': f'Le job {job_id} n\'existe pas'
            }), 404
        
        # Si le job est en état 'failed', le remettre en 'pending'
        if job['status'] == 'failed':
            conn = db.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE scraping_jobs 
                SET status = 'pending', retry_count = 0, started_at = NULL, 
                    completed_at = NULL, error_message = NULL
                WHERE id = ?
            """, (job_id,))
            conn.commit()
            conn.close()
            
            return jsonify({
                'message': f'Job {job_id} relancé avec succès',
                'status': 'pending'
            })
        
        return jsonify({
            'error': 'Impossible de relancer',
            'message': f'Le job {job_id} n\'est pas en état failed (statut actuel: {job["status"]})'
        }), 400
    
    # Route pour vérifier le mot de passe admin
    @admin_bp.route('/check-password', methods=['POST'])
    def check_admin_password():
        """Vérifier un mot de passe admin"""
        data = request.get_json()
        
        if not data or 'password' not in data:
            return jsonify({
                'error': 'Mot de passe manquant',
                'message': 'Vous devez fournir un mot de passe'
            }), 400
        
        password = data['password']
        is_valid = db.verify_admin_password(password)
        
        return jsonify({
            'valid': is_valid
        })
    
    # Route pour changer le mot de passe admin
    @admin_bp.route('/change-password', methods=['POST'])
    def change_admin_password():
        """Changer le mot de passe admin"""
        data = request.get_json()
        
        if not data or 'new_password' not in data:
            return jsonify({
                'error': 'Nouveau mot de passe manquant',
                'message': 'Vous devez fournir un nouveau mot de passe'
            }), 400
        
        new_password = data['new_password']
        
        if len(new_password) < 6:
            return jsonify({
                'error': 'Mot de passe trop court',
                'message': 'Le mot de passe doit contenir au moins 6 caractères'
            }), 400
        
        db.create_admin_password(new_password)
        
        return jsonify({
            'message': 'Mot de passe changé avec succès'
        })
    
    # Route pour obtenir les paramètres système
    @admin_bp.route('/settings', methods=['GET'])
    @auth.require_api_key
    @auth.require_admin
    def get_settings():
        """Obtenir les paramètres système actuels"""
        from backend.config.settings import CHROME_PATH, CHROMEDRIVER_PATH, HEADLESS
        import shutil

        # Lister les navigateurs disponibles
        available_browsers = []
        browsers_to_check = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            "/usr/bin/firefox"
        ]

        for browser_path in browsers_to_check:
            if os.path.exists(browser_path) and os.access(browser_path, os.X_OK):
                browser_name = os.path.basename(browser_path)
                available_browsers.append({
                    'path': browser_path,
                    'name': browser_name,
                    'available': True
                })

        # Chercher aussi dans le PATH
        for cmd in ['google-chrome', 'google-chrome-stable', 'chromium-browser', 'chromium', 'firefox']:
            path = shutil.which(cmd)
            if path and not any(b['path'] == path for b in available_browsers):
                available_browsers.append({
                    'path': path,
                    'name': cmd,
                    'available': True
                })

        return jsonify({
            'chrome_path': CHROME_PATH,
            'chromedriver_path': CHROMEDRIVER_PATH,
            'headless': HEADLESS,
            'available_browsers': available_browsers
        })

    # Route pour mettre à jour les paramètres système
    @admin_bp.route('/settings', methods=['POST'])
    @auth.require_api_key
    @auth.require_admin
    def update_settings():
        """Mettre à jour les paramètres système"""
        data = request.get_json()

        if not data:
            return jsonify({
                'error': 'Données manquantes',
                'message': 'Vous devez fournir des données à mettre à jour'
            }), 400

        # Pour l'instant, on ne permet que la mise à jour du chemin Chrome
        # (les autres paramètres nécessiteraient un redémarrage)
        if 'chrome_path' in data:
            chrome_path = data['chrome_path']

            # Vérifier que le chemin existe et est exécutable
            if not os.path.exists(chrome_path):
                return jsonify({
                    'error': 'Chemin invalide',
                    'message': f'Le chemin {chrome_path} n\'existe pas'
                }), 400

            if not os.access(chrome_path, os.X_OK):
                return jsonify({
                    'error': 'Non exécutable',
                    'message': f'Le fichier {chrome_path} n\'est pas exécutable'
                }), 400

            # Sauvegarder la configuration dans le fichier
            from backend.config.settings import save_browser_config
            if save_browser_config(chrome_path):
                # Mettre à jour la variable CHROME_PATH pour les nouvelles instances
                import backend.config.settings as settings_module
                settings_module.CHROME_PATH = chrome_path
                
                return jsonify({
                    'message': f'Navigateur mis à jour: {chrome_path}',
                    'note': 'La configuration a été sauvegardée. Le prochain scraping utilisera ce navigateur.',
                    'chrome_path': chrome_path
                })
            else:
                return jsonify({
                    'error': 'Erreur sauvegarde',
                    'message': 'Impossible de sauvegarder la configuration'
                }), 500

        return jsonify({
            'error': 'Paramètre inconnu',
            'message': 'Seul chrome_path peut être modifié pour l\'instant'
        }), 400

    # Route pour arrêter le queue manager
    @admin_bp.route('/queue/stop', methods=['POST'])
    @auth.require_api_key
    @auth.require_admin
    def stop_queue_endpoint():
        """Arrêter le traitement de la queue"""
        if stop_queue:
            stopped = stop_queue()
            return jsonify({
                'message': 'Queue manager arrêté' if stopped else 'Queue déjà arrêtée'
            })
        return jsonify({
            'error': 'Fonction de contrôle non disponible'
        }), 500
    
    # Route pour démarrer le queue manager
    @admin_bp.route('/queue/start', methods=['POST'])
    @auth.require_api_key
    @auth.require_admin
    def start_queue_endpoint():
        """Démarrer le traitement de la queue"""
        if start_queue_func:
            started = start_queue_func()
            return jsonify({
                'message': 'Queue manager démarré' if started else 'Queue déjà démarrée'
            })
        return jsonify({
            'error': 'Fonction de contrôle non disponible'
        }), 500
    
    return admin_bp


def list_all_jobs(self):
    """Méthode helper pour lister tous les jobs"""
    conn = self.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM scraping_jobs ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# Ajouter la méthode au modèle Database
Database.list_all_jobs = list_all_jobs

