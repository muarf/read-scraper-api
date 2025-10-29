# 🚀 Déploiement sur Google Cloud Run

Guide complet pour déployer l'application Article Scraper sur Google Cloud Platform.

## 📋 Prérequis

- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) installé
- Compte Google Cloud avec facturation activée
- Droits pour créer des ressources GCP

## 🚀 Déploiement automatique

### Option 1: Script automatisé (Recommandé)

```bash
# Rendre le script exécutable
chmod +x deploy_cloud.sh

# Lancer le déploiement
./deploy_cloud.sh [nom-du-projet]

# Exemple
./deploy_cloud.sh mon-scraper-articles
```

Le script va automatiquement :
- Créer un projet GCP
- Configurer Cloud SQL PostgreSQL
- Créer un bucket Cloud Storage
- Configurer les secrets
- Builder et déployer sur Cloud Run

### Option 2: Déploiement manuel

#### 1. Préparation GCP

```bash
# Variables (adaptez selon vos besoins)
PROJECT_NAME="article-scraper-prod"
REGION="europe-west1"
SERVICE_NAME="scraper-api"
BUCKET_NAME="${PROJECT_NAME}-files"

# Créer le projet
gcloud projects create $PROJECT_NAME
gcloud config set project $PROJECT_NAME

# Activer les APIs
gcloud services enable run.googleapis.com
gcloud services enable sqladmin.googleapis.com
gcloud services enable storage.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable secretmanager.googleapis.com
```

#### 2. Cloud SQL (Base de données)

```bash
# Créer l'instance PostgreSQL
gcloud sql instances create scraper-db \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=$REGION

# Créer la base de données
gcloud sql databases create scraper_db --instance=scraper-db

# Créer l'utilisateur
DB_PASSWORD="$(openssl rand -base64 16)"
gcloud sql users create scraper_user \
  --instance=scraper-db \
  --password=$DB_PASSWORD
```

#### 3. Cloud Storage (Fichiers)

```bash
# Créer le bucket
gsutil mb -p $PROJECT_NAME -c regional -l $REGION gs://$BUCKET_NAME

# Configurer CORS
cat > cors-config.json << EOF
[
  {
    "origin": ["*"],
    "method": ["GET"],
    "responseHeader": ["Content-Type"],
    "maxAgeSeconds": 3600
  }
]
EOF
gsutil cors set cors-config.json gs://$BUCKET_NAME
```

#### 4. Secrets

```bash
# Générer et stocker la clé API admin
ADMIN_API_KEY="$(openssl rand -hex 32)"
echo -n "$ADMIN_API_KEY" | gcloud secrets create admin-api-key --data-file=-

# Stocker le mot de passe DB
echo -n "$DB_PASSWORD" | gcloud secrets create db-password --data-file=-
```

#### 5. Build et déploiement

```bash
# Builder l'image
gcloud builds submit --tag gcr.io/$PROJECT_NAME/scraper-api

# Déployer sur Cloud Run
gcloud run deploy $SERVICE_NAME \
  --image gcr.io/$PROJECT_NAME/scraper-api \
  --platform managed \
  --region=$REGION \
  --allow-unauthenticated \
  --port=8080 \
  --cpu=2 \
  --memory=2Gi \
  --max-instances=10 \
  --timeout=900 \
  --concurrency=1 \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=$PROJECT_NAME" \
  --set-env-vars="GCS_BUCKET_NAME=$BUCKET_NAME" \
  --set-env-vars="CLOUD_SQL_CONNECTION_NAME=$PROJECT_NAME:$REGION:scraper-db" \
  --set-env-vars="K_SERVICE=$SERVICE_NAME" \
  --set-secrets="DATABASE_URL=projects/$PROJECT_NAME/secrets/db-password:latest" \
  --set-secrets="ADMIN_API_KEY=projects/$PROJECT_NAME/secrets/admin-api-key:latest"
```

## 🔧 Configuration

### Variables d'environnement

| Variable | Description | Valeur par défaut |
|----------|-------------|-------------------|
| `DATABASE_URL` | URL de connexion PostgreSQL | Défini par secret |
| `GCS_BUCKET_NAME` | Nom du bucket Cloud Storage | `article-scraper-files` |
| `GOOGLE_CLOUD_PROJECT` | ID du projet GCP | Auto-détecté |
| `CLOUD_SQL_CONNECTION_NAME` | Nom de l'instance Cloud SQL | Défini par secret |
| `ADMIN_API_KEY` | Clé API admin | Défini par secret |
| `K_SERVICE` | Nom du service Cloud Run | Auto-détecté |

### Secrets requis

- `admin-api-key` : Clé API pour l'administration
- `db-password` : Mot de passe de la base de données

## 🧪 Tests post-déploiement

```bash
# Récupérer l'URL du service
SERVICE_URL=$(gcloud run services describe scraper-api --region=europe-west1 --format='value(status.url)')

# Tester l'API
curl "$SERVICE_URL/health"

# Tester avec la clé API
curl -H "X-API-Key: $ADMIN_API_KEY" "$SERVICE_URL/api/v1/articles"
```

## 📊 Monitoring et logs

### Logs Cloud Run
```bash
# Voir les logs en temps réel
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=scraper-api" --limit=50
```

### Métriques Cloud Run
```bash
# Accéder à Cloud Monitoring
open "https://console.cloud.google.com/monitoring?project=$PROJECT_NAME"
```

## 💰 Coûts estimés

| Service | Configuration | Coût/mois |
|---------|---------------|-----------|
| **Cloud Run** | 2 CPU, 2GB RAM, 10 instances max | ~15-25€ |
| **Cloud SQL** | PostgreSQL db-f1-micro | ~10€ |
| **Cloud Storage** | 10GB stockage + trafic | ~1€ |
| **Secrets Manager** | Stockage clés API | ~0.10€ |
| **Cloud Build** | Builds gratuits (2h/mois) | 0€ |

**Total estimé : 25-40€/mois**

## 🧹 Nettoyage

Pour supprimer toutes les ressources :

```bash
# Supprimer le projet entier
gcloud projects delete $PROJECT_NAME

# Ou supprimer les ressources une par une
gcloud run services delete scraper-api --region=$REGION
gcloud sql instances delete scraper-db
gsutil rm -r gs://$BUCKET_NAME
```

## 🔍 Dépannage

### Problèmes courants

1. **Timeout Cloud Run** : Les scrapes peuvent dépasser 15min
   - Solution : Utiliser Cloud Tasks pour les jobs longs

2. **Mémoire insuffisante** : Chrome consomme beaucoup de RAM
   - Solution : Augmenter la mémoire ou utiliser `--memory=4Gi`

3. **Connexion Cloud SQL** : Problèmes de réseau
   - Vérifier `CLOUD_SQL_CONNECTION_NAME`
   - S'assurer que l'instance est dans la même région

4. **Cloud Storage** : Problèmes d'accès
   - Vérifier les permissions IAM
   - S'assurer que le bucket existe

### Debug

```bash
# Logs détaillés
gcloud logging read "resource.type=cloud_run_revision" --limit=100 --format="table(timestamp,severity,textPayload)"

# Status du service
gcloud run services describe scraper-api --region=$REGION
```

## 🎯 Optimisations futures

- **Cloud Tasks** : Pour les jobs de scraping asynchrones
- **Memorystore** : Cache Redis pour améliorer les performances
- **Load Balancer** : Pour un domaine personnalisé
- **CDN** : Cloud CDN pour accélérer la distribution des PDFs

---

## 📞 Support

En cas de problème :
1. Vérifier les logs Cloud Run
2. Tester localement avec `docker-compose up`
3. Ouvrir une issue sur GitHub
