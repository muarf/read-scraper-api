# 📚 Documentation de l'API Read Scraper

## Vue d'ensemble

L'API Read Scraper permet de scraper des articles depuis différentes sources, de les convertir en PDF et de les stocker en base de données. L'API est basée sur Flask et utilise une architecture de queue pour le traitement asynchrone des articles.

**URL de base:** `http://104.244.74.191:5000` (ou votre domaine)

**Version API:** v1  
**Préfixe API:** `/api/v1`

---

## 🔐 Authentification

Toutes les requêtes API nécessitent un header `X-API-Key` contenant une clé API valide.

### Obtenir une clé API temporaire

Vous pouvez obtenir une clé API temporaire (valide 24h) sans authentification :

```bash
GET /api/v1/get-temp-key
```

**Réponse:**
```json
{
  "api_key": "temp_abc123...",
  "expires_in": 86400,
  "message": "Clé API temporaire créée (valide 24h)"
}
```

### Clé API permanente

Pour créer une clé API permanente, vous devez d'abord créer une clé admin via `/init`, puis utiliser les endpoints admin pour créer d'autres clés.

---

## 📊 Endpoints publics

### 1. Créer un job de scraping

Crée un nouveau job de scraping pour une URL donnée.

```http
POST /api/v1/scrape
Headers: X-API-Key: votre_cle_api
Content-Type: application/json
```

**Body - Option 1 : Avec une URL**
```json
{
  "url": "https://exemple.com/article"
}
```

**Body - Option 2 : Avec des termes de recherche uniquement**
```json
{
  "search_terms": "titre article, mots-clés"
}
```

**Body - Option 3 : URL + termes de recherche personnalisés**
```json
{
  "url": "https://exemple.com/article",
  "search_terms": "termes de recherche personnalisés"
}
```

**Paramètres:**
- `url` (optionnel): URL de l'article à scraper. Si fourni, le titre sera extrait automatiquement depuis l'URL.
- `search_terms` (optionnel): Termes de recherche personnalisés. Si fourni, ces termes seront utilisés directement pour la recherche au lieu d'extraire automatiquement le titre depuis l'URL.

**⚠️ Important:** Vous devez fournir **au moins** soit `url`, soit `search_terms`. Les deux peuvent être combinés si vous souhaitez forcer l'utilisation de termes personnalisés même avec une URL.

**Réponse (201):**
```json
{
  "job_id": "abc123def456",
  "status": "pending",
  "url": "https://exemple.com/article",
  "search_terms": null,
  "message": "Job de scraping créé avec succès"
}
```

**Réponse avec search_terms uniquement:**
```json
{
  "job_id": "abc123def456",
  "status": "pending",
  "url": null,
  "search_terms": "titre article",
  "message": "Job de scraping créé avec succès"
}
```

**Réponse si en cache (seulement si URL fournie):**
```json
{
  "job_id": null,
  "status": "completed",
  "article_id": "article_existant",
  "cached": true
}
```

**Comportement:**
- Si seul `url` est fourni : Le système extrait automatiquement le titre depuis l'URL et l'utilise pour la recherche.
- Si seul `search_terms` est fourni : Le système utilise directement ces termes pour la recherche (pas d'extraction de titre).
- Si les deux sont fournis : Le système utilise `search_terms` (priorité) au lieu d'extraire le titre depuis l'URL.

**Erreurs:**
- `400`: Paramètres manquants (ni URL ni search_terms fournis)
- `500`: Erreur lors de la création du job
- `429`: Limite de taux dépassée

---

### 2. Obtenir le statut d'un job

Récupère le statut détaillé d'un job de scraping.

```http
GET /api/v1/job/{job_id}
Headers: X-API-Key: votre_cle_api
```

**Réponse (200):**
```json
{
  "id": "abc123def456",
  "url": "https://exemple.com/article",
  "status": "processing",
  "created_at": "2024-01-15T10:30:00",
  "started_at": "2024-01-15T10:30:05",
  "completed_at": null,
  "error_message": null,
  "current_step": "searching",
  "step_description": "Recherche d'articles similaires en cours...",
  "search_terms": "titre article",
  "extracted_title": "Titre complet de l'article",
  "search_results_count": 5,
  "best_match_title": "Meilleur résultat trouvé",
  "best_match_percentage": 95,
  "best_match_source": "liberation",
  "article_id": "article_123"
}
```

**Statuts possibles:**
- `pending`: En attente de traitement
- `processing`: En cours de traitement
- `extracting_title`: Extraction du titre en cours
- `preparing`: Préparation des fichiers
- `searching`: Recherche d'articles similaires en cours
- `downloading`: Téléchargement du contenu de l'article
- `generating_pdf`: Génération du PDF en cours
- `completed`: Terminé avec succès
- `failed`: Échec du traitement

**Champs supplémentaires dans la réponse:**
- `current_step`: Étape actuelle du traitement (si disponible)
- `step_description`: Description détaillée de l'étape en cours
- `search_terms`: Termes de recherche utilisés
- `extracted_title`: Titre extrait de l'URL
- `search_results_count`: Nombre de résultats trouvés
- `best_match_title`: Titre du meilleur résultat trouvé
- `best_match_percentage`: Pourcentage de similarité du meilleur résultat
- `best_match_source`: Source du meilleur résultat (ex: "liberation", "mediapart")

**Gestion des erreurs "Aucun résultat":**
Si un job échoue avec le message "Aucun résultat trouvé" ou "Aucun résultat trouvé pour cet article", le système ne tentera **pas** de relancer automatiquement le job (contrairement aux autres erreurs techniques qui peuvent être relancées jusqu'à 3 fois). Dans ce cas, vous pouvez créer un nouveau job avec le paramètre `search_terms` personnalisé.

**Erreurs:**
- `404`: Job introuvable

---

### 3. Obtenir un article

Récupère le contenu complet d'un article par son ID.

```http
GET /api/v1/article/{article_id}
Headers: X-API-Key: votre_cle_api
```

**Réponse (200):**
```json
{
  "id": "article_123",
  "url": "https://exemple.com/article",
  "title": "Titre de l'article",
  "html_content": "<article>Contenu HTML complet...</article>",
  "pdf_path": "/path/to/article.pdf",
  "site_source": "liberation.fr",
  "created_at": "2024-01-15T10:30:00",
  "scraped_at": "2024-01-15T10:32:00"
}
```

**Erreurs:**
- `404`: Article introuvable

---

### 4. Télécharger le PDF

Télécharge le fichier PDF d'un article.

```http
GET /api/v1/article/{article_id}/pdf
Headers: X-API-Key: votre_cle_api
```

**Réponse (200):**
Fichier PDF binaire

**Erreurs:**
- `404`: Article ou PDF introuvable

---

### 5. Lister les articles

Liste les articles disponibles avec pagination et filtres.

```http
GET /api/v1/articles?limit=50&offset=0&search=query&site_source=liberation.fr
Headers: X-API-Key: votre_cle_api (optionnel)
```

**Paramètres de requête:**
- `limit`: Nombre d'articles à retourner (défaut: 50)
- `offset`: Nombre d'articles à sauter (défaut: 0)
- `search`: Terme de recherche dans le titre et le contenu
- `site_source`: Filtrer par source (ex: liberation.fr)

**Réponse (200):**
```json
{
  "articles": [
    {
      "id": "article_123",
      "title": "Titre",
      "url": "https://...",
      "site_source": "liberation.fr",
      "created_at": "2024-01-15T10:30:00"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

---

### 6. Rechercher dans les articles

Recherche des articles par termes.

```http
GET /api/v1/search?q=query
Headers: X-API-Key: votre_cle_api
```

**Paramètres de requête:**
- `q`: Terme de recherche (requis)

**Réponse (200):**
```json
{
  "articles": [...],
  "query": "query",
  "total": 10
}
```

**Erreurs:**
- `400`: Paramètre de recherche manquant

---

### 7. Lister les screenshots de debug

Liste les screenshots de debug disponibles pour un job.

```http
GET /api/v1/debug/screenshots
Headers: X-API-Key: votre_cle_api
```

**Réponse (200):**
```json
{
  "screenshots": [
    {
      "filename": "debug_before_search_abc123_1234567890.png",
      "url": "/static/debug_before_search_abc123_1234567890.png",
      "type": "before_search",
      "job_id": "abc123",
      "timestamp": 1234567890,
      "datetime": "2024-01-15T10:30:00",
      "size": 245678
    }
  ],
  "total": 5
}
```

---

## 🔧 Endpoints admin

Tous les endpoints admin nécessitent une clé API avec droits administrateur.

### 1. Obtenir les statistiques

```http
GET /api/v1/admin/stats
Headers: X-API-Key: votre_cle_api_admin
```

**Réponse (200):**
```json
{
  "total_articles": 150,
  "unique_sources": 4,
  "pending_jobs": 2,
  "processing_jobs": 1
}
```

---

### 2. Lister tous les articles (admin)

```http
GET /api/v1/admin/articles?limit=100&offset=0
Headers: X-API-Key: votre_cle_api_admin
```

**Réponse:** Identique à `/api/v1/articles` mais avec plus de détails

---

### 3. Supprimer un article

```http
DELETE /api/v1/admin/article/{article_id}
Headers: X-API-Key: votre_cle_api_admin
```

**Réponse (200):**
```json
{
  "message": "Article abc123 supprimé avec succès"
}
```

**Erreurs:**
- `500`: Erreur lors de la suppression

---

### 4. Lister tous les jobs

```http
GET /api/v1/admin/jobs
Headers: X-API-Key: votre_cle_api_admin
```

**Réponse (200):**
```json
{
  "jobs": [
    {
      "id": "abc123",
      "url": "https://...",
      "status": "completed",
      "created_at": "2024-01-15T10:30:00",
      ...
    }
  ],
  "total": 50
}
```

---

### 5. Créer une clé API

```http
POST /api/v1/admin/apikeys
Headers: X-API-Key: votre_cle_api_admin
Content-Type: application/json
```

**Body:**
```json
{
  "name": "Clé API pour mon app",
  "is_admin": false
}
```

**Réponse (201):**
```json
{
  "message": "Clé API créée avec succès",
  "api_key": "abc123def456...",
  "name": "Clé API pour mon app",
  "is_admin": false,
  "warning": "Sauvegardez cette clé, elle ne sera plus affichée"
}
```

⚠️ **Important:** Notez la clé immédiatement, elle ne sera plus jamais affichée !

---

### 6. Lister les clés API

```http
GET /api/v1/admin/apikeys
Headers: X-API-Key: votre_cle_api_admin
```

**Réponse (200):**
```json
{
  "api_keys": [
    {
      "id": 1,
      "name": "Clé API pour mon app",
      "is_admin": false,
      "created_at": "2024-01-15T10:00:00",
      "last_used": "2024-01-15T15:30:00",
      "is_active": true
    }
  ],
  "total": 3
}
```

---

### 7. Révoquer une clé API

```http
DELETE /api/v1/admin/apikeys/{api_key_id}
Headers: X-API-Key: votre_cle_api_admin
```

**Réponse (200):**
```json
{
  "message": "Clé API 1 révoquée avec succès"
}
```

---

### 8. Nettoyer les données anciennes

```http
POST /api/v1/admin/cleanup
Headers: X-API-Key: votre_cle_api_admin
Content-Type: application/json
```

**Body:**
```json
{
  "days_articles": 90,
  "days_jobs": 7
}
```

**Réponse (200):**
```json
{
  "message": "Nettoyage effectué",
  "articles_deleted": 45,
  "days_articles": 90,
  "days_jobs": 7
}
```

---

### 9. Relancer un job échoué

```http
POST /api/v1/admin/job/{job_id}/retry
Headers: X-API-Key: votre_cle_api_admin
```

**Réponse (200):**
```json
{
  "message": "Job abc123 relancé avec succès",
  "status": "pending"
}
```

---

### 10. Obtenir les paramètres système

```http
GET /api/v1/admin/settings
Headers: X-API-Key: votre_cle_api_admin
```

**Réponse (200):**
```json
{
  "chrome_path": "/usr/bin/google-chrome",
  "chromedriver_path": "/usr/local/bin/chromedriver",
  "headless": true,
  "available_browsers": [
    {
      "path": "/usr/bin/google-chrome",
      "name": "google-chrome",
      "available": true
    }
  ]
}
```

---

### 11. Mettre à jour les paramètres système

```http
POST /api/v1/admin/settings
Headers: X-API-Key: votre_cle_api_admin
Content-Type: application/json
```

**Body:**
```json
{
  "chrome_path": "/usr/bin/google-chrome"
}
```

**Réponse (200):**
```json
{
  "message": "Navigateur mis à jour: /usr/bin/google-chrome",
  "note": "La configuration a été sauvegardée. Le prochain scraping utilisera ce navigateur.",
  "chrome_path": "/usr/bin/google-chrome"
}
```

---

### 12. Contrôler la queue

#### Arrêter le queue manager

```http
POST /api/v1/admin/queue/stop
Headers: X-API-Key: votre_cle_api_admin
```

#### Démarrer le queue manager

```http
POST /api/v1/admin/queue/start
Headers: X-API-Key: votre_cle_api_admin
```

**Réponse (200):**
```json
{
  "message": "Queue manager arrêté"
}
```

---

## 🔄 Flux de travail typique

### Scraper un article depuis l'API

#### Scénario 1 : Avec une URL (extraction automatique du titre)

1. **Créer un job de scraping avec URL**
```bash
curl -X POST http://104.244.74.191:5000/api/v1/scrape \
  -H "X-API-Key: votre_cle_api" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://exemple.com/article"}'
```

2. **Polling du statut du job**
```bash
curl -X GET http://104.244.74.191:5000/api/v1/job/{job_id} \
  -H "X-API-Key: votre_cle_api"
```

Continuez à interroger jusqu'à ce que `status` soit `completed` ou `failed`.

3. **Récupérer l'article**
```bash
curl -X GET http://104.244.74.191:5000/api/v1/article/{article_id} \
  -H "X-API-Key: votre_cle_api"
```

4. **Télécharger le PDF**
```bash
curl -X GET http://104.244.74.191:5000/api/v1/article/{article_id}/pdf \
  -H "X-API-Key: votre_cle_api" \
  -o article.pdf
```

#### Scénario 2 : Avec des termes de recherche uniquement

Si vous connaissez les termes de recherche mais n'avez pas d'URL spécifique :

```bash
curl -X POST http://104.244.74.191:5000/api/v1/scrape \
  -H "X-API-Key: votre_cle_api" \
  -H "Content-Type: application/json" \
  -d '{"search_terms": "titre article, mots-clés"}'
```

Le système utilisera directement ces termes pour la recherche, sans extraire de titre depuis une URL.

#### Scénario 3 : Relancer avec des termes personnalisés

Si un job échoue avec "Aucun résultat trouvé", vous pouvez créer un nouveau job avec des termes de recherche personnalisés :

```bash
curl -X POST http://104.244.74.191:5000/api/v1/scrape \
  -H "X-API-Key: votre_cle_api" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://exemple.com/article",
    "search_terms": "mes termes de recherche personnalisés"
  }'
```

Ou simplement avec les termes uniquement :

```bash
curl -X POST http://104.244.74.191:5000/api/v1/scrape \
  -H "X-API-Key: votre_cle_api" \
  -H "Content-Type: application/json" \
  -d '{"search_terms": "mes termes de recherche personnalisés"}'
```

Le système utilisera ces termes directement pour la recherche au lieu d'extraire automatiquement le titre depuis l'URL.

---

## ⚠️ Gestion des erreurs

Tous les endpoints retournent un JSON standardisé en cas d'erreur :

```json
{
  "error": "Type d'erreur",
  "message": "Description détaillée de l'erreur"
}
```

**Codes HTTP:**
- `200`: Succès
- `201`: Créé
- `400`: Requête invalide
- `401`: Non autorisé (clé API invalide)
- `403`: Interdit (droits insuffisants)
- `404`: Ressource introuvable
- `429`: Limite de taux dépassée
- `500`: Erreur serveur

---

## 🚦 Limitation de taux

Les endpoints sont protégés par une limitation de taux pour éviter les abus. La limite par défaut est de 60 requêtes par minute.

En cas de dépassement, une erreur `429` est retournée.

---

## 📝 Notes importantes

1. **Clés API temporaires** : Valides 24h, idéales pour les tests
2. **Cache** : Les articles déjà scrapés sont retournés immédiatement
3. **Queue** : Le traitement est asynchrone, utilisez le polling pour suivre la progression
4. **Screenshots de debug** : Disponibles uniquement pendant le traitement (supprimés automatiquement après completion)
5. **PDFs** : Générés automatiquement pour tous les articles scrapés
6. **Nettoyage automatique** : Les articles de plus de 30 jours sont supprimés automatiquement
7. **Termes de recherche personnalisés** : Utilisez le paramètre `search_terms` si l'extraction automatique échoue ou ne trouve aucun résultat
8. **Retry automatique** : Les erreurs techniques sont automatiquement relancées jusqu'à 3 fois, sauf les erreurs "Aucun résultat trouvé" qui échouent immédiatement

---

## 🔗 Routes spéciales

### Initialisation

```http
GET /init
```

Crée la première clé API admin. Doit être appelé une seule fois au démarrage.

### Frontend utilisateur

- `/` ou `/read/` : Interface utilisateur principale
- `/read/article/{article_id}` : Afficher un article
- `/article/{article_id}` : Alias pour afficher un article

### Frontend admin

- `/admin` ou `/read/admin` : Interface admin

---

## 📞 Support

Pour toute question ou problème, consultez les logs système dans le répertoire `logs/`.

**Logs disponibles:**
- `logs/app.log`: Logs principaux de l'application
- Console: Logs en temps réel

---

## 🔄 Mise à jour

Cette documentation est mise à jour régulièrement. Dernière mise à jour : Novembre 2024

**Nouvelles fonctionnalités ajoutées:**
- **Détection automatique** : L'API accepte soit une URL, soit des termes de recherche directement (sans URL)
- Support des termes de recherche personnalisés via le paramètre `search_terms` dans `/api/v1/scrape`
- Interface utilisateur avec détection en temps réel du type d'input (URL ou termes de recherche)
- Gestion intelligente des erreurs "Aucun résultat" (pas de retry automatique)
- Statuts détaillés avec `current_step` et `step_description` pour suivre précisément l'évolution du traitement
- Nettoyage automatique des screenshots de debug après completion des jobs
- UI améliorée pour modifier les termes de recherche en cas d'échec

