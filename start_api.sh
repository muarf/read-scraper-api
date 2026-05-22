#!/bin/bash

echo "🚀 Démarrage de l'API Scraper"
echo "============================"
echo ""

# Arrêter toute instance précédente
echo "⏹️  Arrêt des instances précédentes..."
pkill -f "python.*backend.main" || pkill -f "python.*main.py" || true
sleep 2

# Vérifier si la clé API existe
API_KEY_FILE=".api_key"

if [ ! -f "$API_KEY_FILE" ]; then
    echo "🔑 Création de la clé API initiale..."
    python3 -m backend.main &
    APP_PID=$!
    sleep 5
    
    # Essayer de créer la clé via /init
    curl -s http://localhost:5000/init > /tmp/init_response.html
    
    # Extraire la clé API
    API_KEY=$(grep -oP '(?<=<pre>)[^<]+' /tmp/init_response.html | head -1 | tr -d ' ')
    
    if [ ! -z "$API_KEY" ]; then
        echo "$API_KEY" > "$API_KEY_FILE"
        echo "✅ Clé API créée: $API_KEY"
        echo "   Sauvegardée dans $API_KEY_FILE"
    else
        echo "⚠️  Impossible d'extraire la clé automatiquement"
    fi
    
    kill $APP_PID 2>/dev/null || true
    sleep 2
fi

# Vérifier si le chromedriver est exécutable
if [ ! -x "chromedriver_local" ]; then
    echo "⚠️  Attention: chromedriver_local n'est pas exécutable"
    echo "   Exécutez: chmod +x chromedriver_local"
fi

# Démarrer l'application
echo ""
echo "▶️  Démarrage de l'application..."
python3 -m backend.main > logs/api.log 2>&1 &
APP_PID=$!

# Attendre que l'app démarre
sleep 3

# Vérifier que l'app est bien lancée
if kill -0 $APP_PID 2>/dev/null; then
    echo "✅ Application démarrée (PID: $APP_PID)"
    echo ""
    echo "📋 URL: http://localhost:5000"
    echo "📚 Documentation API: http://localhost:5000/"
    
    if [ -f "$API_KEY_FILE" ]; then
        API_KEY=$(cat "$API_KEY_FILE")
        echo ""
        echo "🔑 Votre clé API:"
        echo "   $API_KEY"
        echo ""
        echo "🧪 Test rapide:"
        echo "   curl -H \"X-API-Key: $API_KEY\" http://localhost:5000/api/v1/articles"
    fi
    
    echo ""
    echo "📝 Logs: tail -f logs/api.log"
    echo "⏹️  Pour arrêter: kill $APP_PID"
else
    echo "❌ Erreur lors du démarrage"
    echo "📋 Voir les logs: cat logs/api.log"
fi




