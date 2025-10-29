# Refactorisation API Backend

## Nouvelle Architecture

L'application a été refactorisée pour séparer le backend API du frontend et préparer les futures extensions navigateur et application mobile.

### Structure

```
read-scraper/
├── backend/                 # Backend API
│   ├── api/                # Routes API REST
│   │   ├── routes.py       # Endpoints publics
│   │   └── admin_routes.py # Endpoints admin
│   ├── models/
│   │   └── database.py     # Modèles SQLite
│   ├── services/           # Services métier
│   │   ├── queue_manager.py      # Gestion de la queue
│   │   ├── cache_service.py     # Cache des articles
│   │   ├── scraper_service.py  # Service de scraping
│   │   └── pdf_service.py       # Génération PDF
│   ├── middleware/
│   │   ├── auth.py         # Authentification par API key
│   │   └── rate_limiter.py # Rate limiting
│   ├── config/
│   │   └── settings.py     # Configuration
│   ├── templates/
│   │   ├── index.html      # Page documentation API
│   │   └── article.html    # Page d'affichage article
│   └── main.py             # Point d'entrée
├── web_scraper/            # Code scraping existant (inchangé)
├── common/                  # Utilitaires communs
└── static/                  # Fichiers générés (PDF/HTML)
```

## Démarrer l'application

### 1. Initialiser la base de données et créer une clé API

```bash
python backend/main.py
```

Visiter dans le navigateur: `http://localhost:5000/init`

Cela créera une clé API admin que vous devrez sauvegarder.

### 2. Utiliser l'API

Toutes les requêtes nécessitent un header `X-API-Key`:

```bash
export API_KEY="votre_cle_api"
```

## Endpoints API

### Publiques

#### 1. Créer un job de scraping
```bash
curl -X POST http://localhost:5000/api/v1/scrape \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://exemple.com/article"}'
```

Réponse:
```json
{
  "job_id": "abc123...",
  "status": "pending",
  "url": "https://exemple.com/article"
}
```

#### 2. Vérifier le statut d'un job
```bash
curl http://localhost:5000/api/v1/job/{job_id} \
  -H "X-API-Key: $API_KEY"
```

#### 3. Récupérer un article
```bash
curl http://localhost:5000/api/v1/article/{article_id} \
  -H "X-API-Key: $API_KEY"
```

#### 4. Télécharger le PDF
```bash
curl http://localhost:5000/api/v1/article/{article_id}/pdf \
  -H "X-API-Key: $API_KEY" \
  -o article.pdf
```

#### 5. Lister les articles
```bash
curl "http://localhost:5000/api/v1/articles?limit=50&offset=0" \
  -H "X-API-Key: $API_KEY"
```

#### 6. Rechercher dans les articles
```bash
curl "http://localhost:5000/api/v1/search?q=mot_cle" \
  -H "X-API-Key: $API_KEY"
```

### Admin

Les endpoints admin nécessitent une clé API admin.

#### 7. Statistiques
```bash
curl http://localhost:5000/api/v1/admin/stats \
  -H "X-API-Key: $API_KEY"
```

#### 8. Créer une nouvelle clé API
```bash
curl -X POST http://localhost:5000/api/v1/admin/apikeys \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "mon_app", "is_admin": false}'
```

#### 9. Lister les clés API
```bash
curl http://localhost:5000/api/v1/admin/apikeys \
  -H "X-API-Key: $API_KEY"
```

#### 10. Supprimer un article
```bash
curl -X DELETE http://localhost:5000/api/v1/admin/article/{article_id} \
  -H "X-API-Key: $API_KEY"
```

#### 11. Nettoyer les données anciennes
```bash
curl -X POST http://localhost:5000/api/v1/admin/cleanup \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"days_articles": 90, "days_jobs": 7}'
```

## Flux complet de scraping

1. Créer un job avec `POST /api/v1/scrape`
2. Polling sur `GET /api/v1/job/{job_id}` jusqu'à ce que `status` soit `completed`
3. Récupérer l'`article_id` du job
4. Obtenir l'article avec `GET /api/v1/article/{article_id}`
5. Télécharger le PDF avec `GET /api/v1/article/{article_id}/pdf`

## Base de données SQLite

La base de données est créée automatiquement dans `data/scraper.db`.

### Tables

- **articles**: Articles scrapés (id, url, title, html_content, pdf_path, etc.)
- **scraping_jobs**: Jobs de scraping (id, url, status, article_id, etc.)
- **api_keys**: Clés API (id, key_hash, name, is_admin, etc.)
- **articles_fts**: Index de recherche full-text

## Configuration

Modifier `backend/config/settings.py` pour changer:
- Chemins de base de données
- Timeouts
- Rate limits
- Durée de cache
- etc.

## Next Steps

- [ ] Interface admin complète (dashboard avec graphiques)
- [ ] Extension Chrome/Firefox
- [ ] Progressive Web App mobile
- [ ] Scripts de migration des données existantes
- [ ] Docker Compose mis à jour




