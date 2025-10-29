#!/bin/bash

# Configuration
API_KEY=" 46Yx-2geo.:r]BU1O#3q|5x'bm.ah>V?"
BASE_URL="http://localhost:5000"
API_URL="${BASE_URL}/api/v1"

echo "🧪 Test de l'API Scraper"
echo "========================"
echo ""

# Test 1: Créer un job de scraping
echo "📝 Test 1: Création d'un job de scraping..."
URL="https://www.liberation.fr/politique/avec-eric-zemmour-et-philippe-de-villiers-le-catho-petainisme-decomplexe-20251027_C3B2DGCOSNGCTI5EXNORH6F7IE/"

RESPONSE=$(curl -s -X POST "${API_URL}/scrape" \
  -H "X-API-Key: ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d "{\"url\": \"${URL}\"}")

echo "$RESPONSE" | jq '.'
echo ""

# Extraire le job_id
JOB_ID=$(echo "$RESPONSE" | jq -r '.job_id')

if [ "$JOB_ID" == "null" ] || [ -z "$JOB_ID" ]; then
    echo "❌ Erreur: Impossible de créer le job"
    exit 1
fi

echo "✅ Job créé: ${JOB_ID}"
echo ""

# Test 2: Vérifier le statut du job
echo "🔍 Test 2: Vérification du statut du job..."
STATUS="pending"
ATTEMPTS=0
MAX_ATTEMPTS=60

while [ "$STATUS" == "pending" ] || [ "$STATUS" == "processing" ]; do
    STATUS_RESPONSE=$(curl -s -H "X-API-Key: ${API_KEY}" "${API_URL}/job/${JOB_ID}")
    STATUS=$(echo "$STATUS_RESPONSE" | jq -r '.status')
    
    echo "  Status: ${STATUS}"
    
    ATTEMPTS=$((ATTEMPTS + 1))
    
    if [ $ATTEMPTS -ge $MAX_ATTEMPTS ]; then
        echo "❌ Timeout: Le job n'a pas été complété dans les temps"
        exit 1
    fi
    
    sleep 2
done

echo ""
echo "✅ Status final: ${STATUS}"
echo ""

# Si le job est complété, afficher l'article
if [ "$STATUS" == "completed" ]; then
    ARTICLE_ID=$(echo "$STATUS_RESPONSE" | jq -r '.article_id')
    
    if [ "$ARTICLE_ID" != "null" ] && [ ! -z "$ARTICLE_ID" ]; then
        echo "📄 Test 3: Récupération de l'article..."
        ARTICLE_RESPONSE=$(curl -s -H "X-API-Key: ${API_KEY}" "${API_URL}/article/${ARTICLE_ID}")
        
        echo "  Titre: $(echo "$ARTICLE_RESPONSE" | jq -r '.title')"
        echo "  URL: $(echo "$ARTICLE_RESPONSE" | jq -r '.url')"
        echo "  Source: $(echo "$ARTICLE_RESPONSE" | jq -r '.site_source')"
        echo ""
        
        echo "✅ Article récupéré avec succès"
        echo ""
        echo "🌐 Ouvrir dans le navigateur: ${BASE_URL}/article/${ARTICLE_ID}"
    fi
else
    ERROR=$(echo "$STATUS_RESPONSE" | jq -r '.error_message')
    echo "❌ Erreur: ${ERROR}"
fi




