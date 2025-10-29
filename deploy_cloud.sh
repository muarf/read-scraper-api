#!/bin/bash

# Script de déploiement complet pour Google Cloud Run
# Usage: ./deploy_cloud.sh [project-name]

set -e

# Configuration
PROJECT_NAME=${1:-"article-scraper-$(date +%s)"}
REGION="europe-west1"
SERVICE_NAME="scraper-api"
BUCKET_NAME="${PROJECT_NAME}-files"
DB_INSTANCE_NAME="${PROJECT_NAME//-/_}_db"
DB_NAME="scraper_db"
DB_USER="scraper_user"

echo "🚀 Déploiement Article Scraper sur Google Cloud Platform"
echo "===================================================="
echo "Projet: $PROJECT_NAME"
echo "Région: $REGION"
echo ""

# Vérifier gcloud
if ! command -v gcloud &> /dev/null; then
    echo "❌ gcloud CLI n'est pas installé. Installez-le depuis https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Se connecter à gcloud
echo "🔐 Connexion à Google Cloud..."
gcloud auth login

# Créer le projet
echo "📁 Création du projet: $PROJECT_NAME"
gcloud projects create $PROJECT_NAME --name="Article Scraper"

# Activer les APIs nécessaires
echo "🔧 Activation des APIs..."
gcloud config set project $PROJECT_NAME
gcloud services enable run.googleapis.com
gcloud services enable sqladmin.googleapis.com
gcloud services enable storage.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable secretmanager.googleapis.com

# Créer Cloud SQL PostgreSQL
echo "🗄️ Création de Cloud SQL PostgreSQL..."
gcloud sql instances create $DB_INSTANCE_NAME \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=$REGION \
  --root-password="$(openssl rand -base64 12)"

# Créer la base de données
echo "📊 Création de la base de données..."
gcloud sql databases create $DB_NAME --instance=$DB_INSTANCE_NAME

# Créer l'utilisateur de base de données
echo "👤 Création de l'utilisateur base de données..."
DB_PASSWORD="$(openssl rand -base64 16)"
gcloud sql users create $DB_USER \
  --instance=$DB_INSTANCE_NAME \
  --password=$DB_PASSWORD

# Créer le bucket Cloud Storage
echo "🪣 Création du bucket Cloud Storage..."
gsutil mb -p $PROJECT_NAME -c regional -l $REGION gs://$BUCKET_NAME

# Configurer CORS pour le bucket
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
rm cors-config.json

# Créer les secrets
echo "🔒 Création des secrets..."

# Générer une clé API admin
ADMIN_API_KEY="$(openssl rand -hex 32)"
echo -n "$ADMIN_API_KEY" | gcloud secrets create admin-api-key --data-file=-

# Stocker le mot de passe de la DB
echo -n "$DB_PASSWORD" | gcloud secrets create db-password --data-file=-

echo "📝 Construction de l'image Docker..."
gcloud builds submit --tag gcr.io/$PROJECT_NAME/$SERVICE_NAME --timeout=1200

echo "🚀 Déploiement sur Cloud Run..."
gcloud run deploy $SERVICE_NAME \
  --image gcr.io/$PROJECT_NAME/$SERVICE_NAME \
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
  --set-env-vars="CLOUD_SQL_CONNECTION_NAME=$PROJECT_NAME:$REGION:$DB_INSTANCE_NAME" \
  --set-env-vars="K_SERVICE=$SERVICE_NAME" \
  --set-secrets="DATABASE_URL=projects/$PROJECT_NAME/secrets/db-password:latest" \
  --set-secrets="ADMIN_API_KEY=projects/$PROJECT_NAME/secrets/admin-api-key:latest"

# Récupérer l'URL du service
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format='value(status.url)')

echo ""
echo "✅ Déploiement terminé avec succès!"
echo "====================================="
echo "🌐 URL du service: $SERVICE_URL"
echo "🔑 Clé API admin: $ADMIN_API_KEY"
echo "🗄️ Instance DB: $DB_INSTANCE_NAME"
echo "🪣 Bucket: $BUCKET_NAME"
echo ""
echo "📚 Test rapide:"
echo "curl -H \"X-API-Key: $ADMIN_API_KEY\" \"$SERVICE_URL/api/v1/articles\""
echo ""
echo "💰 Coûts estimés:"
echo "• Cloud Run: ~15-25€/mois"
echo "• Cloud SQL: ~10€/mois"
echo "• Cloud Storage: ~1€/mois"
echo "• Total: ~25-40€/mois"
echo ""
echo "🧹 Pour nettoyer:"
echo "gcloud projects delete $PROJECT_NAME"
