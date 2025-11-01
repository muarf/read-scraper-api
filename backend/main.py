"""
Application Flask principale
"""
from flask import Flask, render_template, send_from_directory, send_file
from flask_cors import CORS
import sys
from pathlib import Path

# Ajouter le répertoire racine au path Python
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config.settings import STATIC_DIR, API_PREFIX, USERNAME, PASSWORD, PORT, IS_CLOUD_ENV
from backend.models.database import create_database
from backend.services.cache_service import CacheService
from backend.services.pdf_service import PDFService
from backend.services.scraper_service import ScraperService
from backend.services.queue_manager import QueueManager
from backend.api.routes import create_api_blueprint
from backend.api.admin_routes import create_admin_blueprint
import logging
import os
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

# Configuration du logging avec rotation
# Créer le répertoire 'logs' s'il n'existe pas
log_dir = Path('logs')
log_dir.mkdir(parents=True, exist_ok=True)

# Configurer le TimedRotatingFileHandler pour une rotation quotidienne
file_handler = TimedRotatingFileHandler(
    log_dir / 'app.log',
    when='midnight',
    interval=1,  # Chaque jour
    backupCount=7,  # Garder 7 jours de logs
    encoding='utf-8'
)
file_handler.suffix = "%Y-%m-%d"  # Format du suffixe pour les fichiers de backup

# Créer un StreamHandler avec encodage UTF-8 pour éviter les erreurs Unicode
import io

# Configurer stdout/stderr pour UTF-8
try:
    if hasattr(sys.stdout, 'reconfigure'):
        # Python 3.7+
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    elif hasattr(sys.stdout, 'buffer'):
        # Pour Python < 3.7, wrapper avec TextIOWrapper
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)
except Exception:
    # Si la configuration échoue, on continue quand même (logging pas encore configuré)
    pass

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        file_handler,
        console_handler
    ]
)

logger = logging.getLogger(__name__)

app = Flask(__name__, 
            static_folder=str(STATIC_DIR), 
            static_url_path='/static',
            template_folder='templates')
CORS(app, resources={r"/*": {"origins": "*"}})

# Initialisation de la base de données
db = create_database()

# Nettoyer les anciens articles (plus de 30 jours)
logger.info("Nettoyage des articles de plus de 30 jours...")
deleted_count = db.cleanup_old_data(days_articles=30)
if deleted_count > 0:
    logger.info(f"{deleted_count} anciens articles nettoyés")
else:
    logger.info("Aucun ancien article à nettoyer")

# Initialisation des services
pdf_service = PDFService()
cache_service = CacheService(db)

# Instance globale du scraper pour réutiliser le navigateur
global_scraper = None

def scraper_callback(url: str, job_id: str):
    """Callback pour le service de scraping"""
    # Créer une nouvelle instance pour chaque job afin d'éviter les conflits de session Chrome
    scraper = ScraperService(db, pdf_service)
    logger.info(f"Nouvelle instance de scraper créée pour job {job_id}")

    try:
        return scraper.scrape_article(url, job_id)
    except Exception as e:
        logger.error(f"Erreur dans scraper_callback pour job {job_id}: {e}")
        # Nettoyer l'instance
        try:
            scraper.cleanup()
        except:
            pass
        raise

# Initialisation du queue manager
queue_manager = QueueManager(db, scraper_callback)
queue_manager.start()

# Fonctions pour contrôler la queue (utilisables par les routes admin)
def stop_queue_manager():
    """Arrêter le queue manager"""
    global queue_manager
    if queue_manager and queue_manager.is_running:
        queue_manager.stop()
        return True
    return False

def start_queue_manager():
    """Démarrer le queue manager"""
    global queue_manager
    if queue_manager and not queue_manager.is_running:
        queue_manager.start()
        return True
    return False

# Enregistrement des blueprints
api_bp = create_api_blueprint(db, cache_service, queue_manager)
app.register_blueprint(api_bp)

admin_bp = create_admin_blueprint(db, queue_control_functions={
    'stop': stop_queue_manager,
    'start': start_queue_manager
})
app.register_blueprint(admin_bp)

# Route principale - Frontend utilisateur
@app.route('/')
def index():
    """Frontend utilisateur"""
    from pathlib import Path
    import os
    frontend_path = Path(__file__).parent.parent / 'frontend' / 'index.html'
    return send_file(str(frontend_path))

@app.route('/read/')
@app.route('/read')
def read():
    """Alias pour la route principale - accessible via /read/"""
    return index()

@app.route('/read/<path:filename>')
def read_files(filename):
    """Servir les fichiers du frontend quand on accède via /read/"""
    from pathlib import Path
    frontend_dir = Path(__file__).parent.parent / 'frontend'
    return send_from_directory(str(frontend_dir), filename)

@app.route('/frontend/<path:filename>')
def frontend_files(filename):
    """Servir les fichiers du frontend"""
    from pathlib import Path
    frontend_dir = Path(__file__).parent.parent / 'frontend'
    return send_from_directory(str(frontend_dir), filename)

# Route admin
@app.route('/admin')
def admin():
    """Frontend admin"""
    from pathlib import Path
    admin_path = Path(__file__).parent.parent / 'admin' / 'index.html'
    return send_file(str(admin_path))

@app.route('/admin/<path:filename>')
def admin_files(filename):
    """Servir les fichiers de l'admin"""
    from pathlib import Path
    admin_dir = Path(__file__).parent.parent / 'admin'
    return send_from_directory(str(admin_dir), filename)

# Alias pour l'admin via /read/admin
@app.route('/read/admin')
def read_admin():
    """Alias vers l'interface admin accessible via /read/admin"""
    return admin()

@app.route('/read/admin/<path:filename>')
def read_admin_files(filename):
    """Servir les fichiers de l'admin via /read/admin/"""
    return admin_files(filename)

# Route pour afficher un article scrapé
@app.route('/article/<article_id>')
@app.route('/read/article/<article_id>')
def view_article(article_id):
    """Afficher un article scrapé avec possibilité de rejet"""
    article = db.get_article(article_id)

    if not article:
        return f"Article {article_id} introuvable", 404

    # Récupérer le job_id associé pour permettre le rejet
    job = db.get_job_by_article_id(article_id)
    job_id = job['id'] if job else None

    return render_template('article.html', article=article, job_id=job_id)

# Route statique pour les fichiers
@app.route('/static/<path:filename>')
def serve_static(filename):
    """Servir les fichiers statiques"""
    return send_from_directory(str(STATIC_DIR), filename)

# Route pour créer une clé API initiale (une seule fois)
@app.route('/init', methods=['GET'])
def init_admin_key():
    """Initialiser une clé API admin"""
    import hashlib
    from common.utils import generate_id
    
    # Vérifier si une clé admin existe déjà
    api_keys = db.list_api_keys()
    admin_keys = [k for k in api_keys if k.get('is_admin')]
    
    if admin_keys:
        return "Une clé admin existe déjà. Utilisez l'API pour créer de nouvelles clés.", 200
    
    # Créer une clé admin
    api_key = generate_id(32)
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    
    if db.create_api_key(key_hash, 'admin', is_admin=True):
        return f"""
        <h1>Clé API Admin créée</h1>
        <p><strong>Sauvegardez cette clé, elle ne sera plus affichée :</strong></p>
        <pre>{api_key}</pre>
        <p>Utilisez cette clé dans le header <code>X-API-Key</code> de vos requêtes API.</p>
        """, 200
    
    return "Erreur lors de la création de la clé.", 500


if __name__ == '__main__':
    logger.info("Démarrage de l'application...")
    logger.info(f"Base de données: {db.db_path}")
    logger.info(f"API prefix: {API_PREFIX}")
    logger.info(f"Queue manager démarré")
    
    app.run(host='0.0.0.0', port=PORT, debug=not IS_CLOUD_ENV)

