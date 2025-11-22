"""
Configuration centralisée pour l'application
"""
import os
import sys
from pathlib import Path

# Chemins - répertoire racine du projet (forcé)
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "scraper.db"
STATIC_DIR = (BASE_DIR.parent / "static").resolve()
LOGS_DIR = (BASE_DIR.parent / "logs").resolve()

# Création des répertoires si nécessaire
for directory in [DB_PATH.parent, STATIC_DIR, LOGS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# Database
DATABASE_URL = f"sqlite:///{DB_PATH}"

# API
API_VERSION = "v1"
API_PREFIX = f"/api/{API_VERSION}"

# Credentials (à mettre dans .env en production)
USERNAME = os.getenv("SCRAPER_USERNAME", "demo0038")
PASSWORD = os.getenv("SCRAPER_PASSWORD", "PRESSE")

# Fichier de configuration pour le navigateur
BROWSER_CONFIG_FILE = BASE_DIR / "data" / "browser_config.json"

def load_browser_config():
    """Charger la configuration du navigateur depuis le fichier"""
    import json
    if BROWSER_CONFIG_FILE.exists():
        try:
            with open(BROWSER_CONFIG_FILE, 'r') as f:
                config = json.load(f)
                if 'chrome_path' in config and os.path.exists(config['chrome_path']) and os.access(config['chrome_path'], os.X_OK):
                    return config['chrome_path']
        except Exception as e:
            print(f"Erreur lors du chargement de la config navigateur: {e}")
    return None

def save_browser_config(chrome_path):
    """Sauvegarder la configuration du navigateur dans le fichier"""
    import json
    try:
        config = {'chrome_path': chrome_path}
        with open(BROWSER_CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        print(f"Erreur lors de la sauvegarde de la config navigateur: {e}")
        return False

# Chrome configuration - détection automatique du navigateur
def find_chrome_binary():
    """Trouve automatiquement un navigateur Chrome disponible"""
    import shutil

    # Liste des navigateurs à essayer dans l'ordre de préférence
    browsers = [
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
        "google-chrome",
        "google-chrome-stable",
        "chromium-browser",
        "chromium"
    ]

    # Essayer les chemins absolus d'abord
    for browser in browsers[:4]:  # Premiers 4 sont des chemins absolus
        if os.path.exists(browser) and os.access(browser, os.X_OK):
            return browser

    # Essayer les commandes dans le PATH
    for browser in browsers[4:]:  # Derniers sont des commandes
        if shutil.which(browser):
            return shutil.which(browser)

    # Fallback par défaut
    return "/usr/bin/google-chrome"

# Charger la configuration sauvegardée, sinon utiliser la variable d'environnement ou la détection automatique
saved_chrome_path = load_browser_config()
CHROME_PATH = os.getenv("CHROME_PATH") or saved_chrome_path or find_chrome_binary()
print(f"Using Chrome binary: {CHROME_PATH}")
# Utiliser le chromedriver local (chemin absolu depuis la racine du projet)
# BASE_DIR est backend/, donc BASE_DIR.parent est la racine du projet
CHROMEDRIVER_LOCAL = BASE_DIR.parent / "chromedriver_local" / "chromedriver"
CHROMEDRIVER_LOCAL = CHROMEDRIVER_LOCAL.resolve()
print(f"CHECKING chromedriver: {CHROMEDRIVER_LOCAL} exists={CHROMEDRIVER_LOCAL.exists()}")
if CHROMEDRIVER_LOCAL.exists():
    CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", str(CHROMEDRIVER_LOCAL))
    print(f"Using local chromedriver: {CHROMEDRIVER_PATH}")
else:
    # Fallback vers chromedriver système
    CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")
    print(f"Using system chromedriver: {CHROMEDRIVER_PATH}")
HEADLESS = True  # Mode headless désactivé pour le développement local

# Queue
MAX_CONCURRENT_JOBS = 1
JOB_TIMEOUT = 180  # seconds (augmenté)
MAX_RETRIES = 3

# Cache
CACHE_DURATION_HOURS = 24  # Nombre d'heures avant expiration du cache

# Rate limiting
RATE_LIMIT_REQUESTS = 20  # nombre de requêtes
RATE_LIMIT_WINDOW = 3600  # fenêtre en secondes (1h)
ADMIN_RATE_LIMIT_REQUESTS = 100

# Nettoyage automatique
CLEANUP_DAYS_ARTICLES = 90
CLEANUP_DAYS_JOBS = 7
CLEANUP_DAYS_LOGS = 30

# Configuration Cloud (Google Cloud Run)
IS_CLOUD_ENV = os.getenv('K_SERVICE') is not None  # Variable automatique Cloud Run

if IS_CLOUD_ENV:
    # Cloud SQL PostgreSQL
    DATABASE_URL = os.environ.get('DATABASE_URL')

    # Cloud Storage
    GCS_BUCKET_NAME = os.environ.get('GCS_BUCKET_NAME', 'article-scraper-files')

    # Chrome obligatoire headless sur Cloud Run
    HEADLESS = True

    # Timeouts adaptés à Cloud Run (15 minutes max)
    JOB_TIMEOUT = 840  # 14 minutes pour laisser de la marge
    MAX_CONCURRENT_JOBS = 1  # Un seul job à la fois sur Cloud Run

    # Logs vers stdout (Cloud Logging)
    LOG_TO_FILE = False

    # Port Cloud Run
    PORT = int(os.environ.get('PORT', 8080))

    # Variables Cloud SQL
    CLOUD_SQL_CONNECTION_NAME = os.environ.get('CLOUD_SQL_CONNECTION_NAME')

else:
    # Configuration locale (inchangée)
    DATABASE_URL = f"sqlite:///{DB_PATH}"
    GCS_BUCKET_NAME = None
    LOG_TO_FILE = True
    PORT = 5000
    CLOUD_SQL_CONNECTION_NAME = None

