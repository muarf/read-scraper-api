# Presse Scraper APK v2 — Spécification

## Architecture

L'app est un wrapper Capacitor (WebView) autour du frontend existant (`mobile/www/`).
Le serveur Flask tourne sur `141.145.223.71:5000` et fait le scraping Europresse via Selenium.

**Flux :**
1. L'user entre ses identifiants BnF dans l'app (stockés localement, jamais envoyés au serveur)
2. L'app ouvre un WebView invisible pour se connecter à BnF → extrait les cookies de session
3. L'user colle un URL/article → l'app envoie les cookies + URL au serveur
4. Le serveur scrape Europresse et retourne l'article en HTML + PDF

## Écran 1 — Première installation / Onboarding

### 1.1 Écran BnF Login (obligatoire au premier lancement)

- Titre : **"Connexion à Europresse (BnF)"**
- Sous-titre : *"Vos identifiants BnF sont stockés sur votre appareil et ne sont jamais envoyés au serveur."*
- Champ : **Identifiant BnF** (texte)
- Champ : **Mot de passe BnF** (password)
- Bouton : **"Se connecter"**
- Lien : **"Créer un compte BnF"** → ouvre `https://bnf.idm.oclc.org/login` dans le navigateur externe
- Lien : **"Identifiants oubliés ?"** → ouvre la page de récupération BnF

**Comportement :**
- Au clic sur "Se connecter" : ouvre un WebView invisible vers le portail BnF, injecte les credentials, soumet le formulaire
- Si succès : extrait les cookies de session Europresse, les stocke dans `localStorage`, passe à l'écran principal
- Si échec : affiche le message d'erreur sous le formulaire (rouge)
- Les credentials sont sauvegardés dans `localStorage` pour ne pas les redemander
- Un indicateur de session (pastille verte/rouge) est visible en permanence dans le header

### 1.2 Écran principal (après login BnF)

## Écran 2 — Accueil (scraping)

### Layout
- **Header** : logo + titre "Presse Scraper" + pastille de session BnF (vert = connecté, rouge = expiré)
- **Bannière contenu partagé** (si l'app a été ouverte via un partage Android) : affiche le texte/URL partagé avec un bouton "Utiliser"
- **Champ de saisie** : "Collez un lien ou tapez des mots-clés..."
- **Bouton "Scraper"** : lance le scraping
- **Carte de statut** : affiche la progression (spinner + étape en cours + barre de progression)
- **Historique des articles** : liste des articles déjà scrapés (voir section Historique)

### Comportement du scraping
1. L'user entre un URL ou des mots-clés et clique "Scraper"
2. L'app vérifie que les cookies BnF sont valides (pas expirés)
3. Si cookies expirés → relance le login BnF automatiquement (WebView invisible)
4. Envoie `{url, cookies}` au serveur `POST /api/v1/scrape`
5. Le serveur crée un job et retourne un `job_id`
6. L'app poll le statut du job toutes les 3 secondes
7. Quand le job est `completed` :
   - Le statut affiche "✅ Article trouvé !"
   - Un bouton **"Ouvrir l'article"** apparaît
   - Au clic → ouvre l'article HTML dans un nouvel onglet WebView (voir section Visualisation)

## Écran 3 — Historique des articles

### Accès
- Onglet "Historique" dans la navigation bottom
- Ou scroll down sur l'écran principal

### Layout
- Liste des articles scrapés, triés par date (plus récent en haut)
- Chaque item affiche :
  - **Titre de l'article** (tronqué si trop long)
  - **Source** (ex: "Le Parisien", "Le Monde")
  - **Date du scraping**
  - **Pastille de statut** : vert = succès, rouge = échec
- Au clic sur un item → ouvre l'article HTML (voir section Visualisation)

### Persistance
- L'historique est stocké dans `localStorage` (clé : `presse_scraper_history_v2`)
- Chaque entrée : `{id, title, url, source, date, htmlPath, pdfPath, status}`

## Écran 4 — Visualisation d'un article (HTML)

### Layout
- **Header** : bouton retour + titre de l'article (tronqué) + bouton "Ouvrir le PDF"
- **Contenu** : l'article HTML rendu dans une WebView
- **Bouton PDF** (flottant, bas droite) : icône PDF rouge
  - Au clic → ouvre le PDF **dans le navigateur interne de l'app** (WebView), PAS un téléchargement
  - Le PDF est servi par `GET /api/v1/article/{id}/pdf` avec `Content-Disposition: inline`

### Intégration au menu "Partager" Android
- Quand l'user partage du texte/URL vers l'app → la bannière "Contenu partagé" apparaît
- L'user peut cliquer "Utiliser" pour remplir le champ de saisie

### Intégration à la sélection de texte (PROCESS_TEXT)
- Quand l'user sélectionne du texte dans une autre app et choisit "Presse Scraper" → l'app ouvre l'écran principal avec le texte pré-rempli

## Écran 5 — Paramètres

### Sections
1. **Session BnF**
   - Identifiant (affiché, non modifiable sans déconnexion)
   - Statut de la session (pastille + texte "Connecté" / "Expiré")
   - Bouton "Se reconnecter" (relance le login BnF)
   - Bouton "Se déconnecter" (supprime les cookies)

2. **Clé API** (pour identifier l'user côté serveur)
   - Affichage de la clé API (générée automatiquement au premier lancement)
   - Bouton "Régénérer la clé API"
   - La clé est envoyée dans le header `X-API-Key` de chaque requête

3. **Stockage**
   - Nombre d articles en cache
   - Bouton "Vider le cache" (supprime les HTML/PDF locaux mais garde l'historique)

4. **Serveur**
   - URL du serveur (par défaut : `http://141.145.223.71:5000`)
   - Bouton "Tester la connexion"

## API Backend (modifications nécessaires)

### Nouvelles routes

```
POST /api/v1/scrape
  Body: { url: string, cookies: [{name, value, domain, path}], search_terms?: string }
  Headers: X-API-Key: <user_api_key>
  Response: { job_id, status: "pending" }

GET /api/v1/job/:job_id
  Headers: X-API-Key: <user_api_key>
  Response: { job_id, status, article_id?, article_title?, error_message? }

GET /api/v1/article/:article_id
  Headers: X-API-Key: <user_api_key>
  Response: { id, title, html_content, pdf_path, source, created_at }

GET /api/v1/article/:article_id/pdf
  Headers: X-API-Key: <user_api_key>
  Response: PDF file (Content-Type: application/pdf, Content-Disposition: inline)

GET /api/v1/articles?limit=20
  Headers: X-API-Key: <user_api_key>
  Response: { articles: [...] }

POST /api/v1/register
  Body: { device_id: string }
  Response: { api_key: string }
```

### Modifications existantes
- `POST /api/v1/scrape` doit accepter les cookies BnF dans le body (en plus de l'URL)
- `GET /api/v1/article/:id/pdf` doit retourner le PDF avec `Content-Disposition: inline` (pas `attachment`)
- Ajout du middleware d'authentification API key sur toutes les routes

## Plugin natif BnfLogin (modifications)

### Méthodes existantes (à garder)
- `login({username, password})` → WebView invisible BnF → cookies
- `httpRequest({url, method, headers, body})` → requête HTTP native
- `downloadFile({url, filename})` → téléchargement fichier

### Nouvelles méthodes
- `getCookies()` → retourne les cookies stockés
- `clearCookies()` → supprime les cookies
- `isSessionValid()` → vérifie si les cookies sont encore valides (pas expirés)

## AndroidManifest.xml (modifications)

```xml
<!-- Intention de partage (recevoir du texte/URL) -->
<activity android:name=".MainActivity" android:exported="true">
    <intent-filter>
        <action android:name="android.intent.action.SEND" />
        <category android:name="android.intent.category.DEFAULT" />
        <data android:mimeType="text/plain" />
    </intent-filter>
    <intent-filter>
        <action android:name="android.intent.action.PROCESS_TEXT" />
        <category android:name="android.intent.category.DEFAULT" />
        <meta-data android:name="android.app.process_text_config"
                   android:resource="@xml/process_text_config" />
    </intent-filter>
</activity>
```

## Fichiers à modifier/créer

### Frontend
- `mobile/www/index.html` → réécriture complète de l'UI
- `mobile/www/js/app.js` → nouvelle logique (onboarding, historique, visualisation)
- `mobile/www/css/style.css` → nouveau style

### Backend
- `backend/api/routes.py` → nouvelles routes + middleware API key
- `backend/services/scraper_service.py` → accepter les cookies dans le body
- `backend/models/database.py` → table `api_keys` pour lier clé API → user

### Plugin natif
- `mobile/src/plugins/bnf-login/android/.../BnfLoginPlugin.java` → nouvelles méthodes
- `mobile/src/plugins/bnf-login/BnfLoginPlugin.ts` → interface TypeScript

### Android
- `mobile/android/app/src/main/AndroidManifest.xml` → ajouter les intent-filters
- `mobile/android/app/src/main/res/xml/process_text_config.xml` → config PROCESS_TEXT

## Build

Le build se fait via GitHub Actions (`.github/workflows/build-apk.yml`).
Le workflow :
1. Checkout du repo
2. Installation des dépendances npm
3. Build du frontend (`npx cap sync`)
4. Build de l'APK via Gradle
5. Upload de l'APK en artifact

## Points d'attention

1. **Les credentials BnF ne doivent JAMAIS être envoyés au serveur** — uniquement les cookies de session
2. **La clé API est générée côté serveur** au premier lancement et stockée dans `localStorage`
3. **Le PDF doit s'ouvrir dans une WebView** (pas téléchargé) — utiliser `Content-Disposition: inline`
4. **L'historique est local** (localStorage) — pas de sync serveur
5. **Les cookies BnF expirent** — l'app doit détecter l'expiration et relancer le login automatiquement
6. **Le serveur utilise déjà les cookies BnF** pour le scraping — pas de changement côté scraping
