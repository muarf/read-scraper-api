# API Backend - Guide Rapide

## 🚀 Démarrage rapide

### 1. Démarrer l'API

```bash
./start_api.sh
```

Ou manuellement:
```bash
python3 run_api.py
```

### 2. Créer une clé API

Visitez dans votre navigateur:
```
http://localhost:5000/init
```

Sauvegardez la clé affichée.

### 3. Tester l'API

Votre clé API: `8a2hL:9o*.g8&*>;^2GP5Q;tT}-n]^Nl`

```bash
# Créer un job de scraping
curl -X POST http://localhost:5000/api/v1/scrape \
  -H "X-API-Key: 8a2hL:9o*.g8&*>;^2GP5Q;tT}-n]^Nl" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.liberation.fr/politique/avec-eric-zemmour-et-philippe-de-villiers-le-catho-petainisme-decomplexe-20251027_C3B2DGCOSNGCTI5EXNORH6F7IE/"}'
```

## 📝 Endpoints disponibles

- `GET /` - Documentation API
- `GET /init` - Créer une clé API admin
- `POST /api/v1/scrape` - Créer un job de scraping
- `GET /api/v1/job/{job_id}` - Statut du job
- `GET /api/v1/article/{article_id}` - Récupérer un article
- `GET /api/v1/article/{article_id}/pdf` - Télécharger le PDF
- `GET /article/{article_id}` - Afficher l'article dans le navigateur

## 🔧 Configuration

Fichier: `backend/config/settings.py`

- `CHROMEDRIVER_PATH` - Chemin vers chromedriver (défaut: `./chromedriver_local`)
- `HEADLESS` - Mode sans interface (défaut: `true`)
- `USERNAME` / `PASSWORD` - Credentials pour le site cible

## 📋 Structure

```
backend/
├── api/                    # Routes API
├── models/                 # Modèles BDD
├── services/               # Services métier
├── middleware/             # Auth, rate limiting
├── config/                 # Configuration
└── main.py                 # Point d'entrée

data/scraper.db            # Base SQLite
static/                     # Fichiers générés
logs/                       # Logs application
```

## ⚠️ Notes importantes

- Port par défaut: **5000**
- Base de données: SQLite dans `data/scraper.db`
- Chromedriver doit être exécutable: `chmod +x chromedriver_local`
- Voir les logs: `tail -f logs/api.log`

## 🐛 Dépannage

Si l'erreur "Module not found":
```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

Si le port est déjà utilisé:
```bash
pkill -f "python.*run_api.py"
```




