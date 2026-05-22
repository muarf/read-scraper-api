# 📖 Read Scraper API

**Read Scraper API** est le backend officiel (serveur) conçu pour fonctionner avec l'application mobile Android **[PressScraper](https://github.com/muarf/pressscraper)** et les extensions de navigateur.

Ce service web permet de contourner les paywalls et les murs de cookies (cookie-walls) des sites de presse, d'extraire le contenu textuel brut des articles, et d'en générer des fichiers PDF lisibles, archivés et consultables sur mobile.

## ✨ Fonctionnalités Principales

- **Extraction Intelligente (Ophirofox)** : Utilise un système d'injection JavaScript (`ophirofox`) pour simuler une navigation humaine et contourner les blocages anti-bots ou murs de consentement.
- **Scraping Europresse** : Recherche et extrait automatiquement l'article depuis les bases de données Europresse via Selenium et Chromium.
- **File d'Attente (Queue) Asynchrone** : Traitement en arrière-plan des requêtes de scraping pour éviter les timeouts HTTP. Les clients (comme l'app Android) interrogent le serveur pour suivre la progression du traitement en temps réel.
- **Conversion PDF** : Conversion des pages HTML nettoyées en fichiers PDF natifs via `pdfkit` et `wkhtmltopdf`.
- **Mécanisme de Fallback Manuel** : Si la recherche automatique échoue (par exemple, à cause de titres exotiques d'URL sans accents), l'API renvoie les termes de recherche utilisés et permet à l'application mobile de relancer manuellement une requête corrigée.
- **Authentification par Appareil** : Génération de clés API permanentes par `device_id` pour gérer simplement les clients.

## 🛠️ Stack Technique

- **Framework Web** : Python / Flask
- **Base de données** : SQLite (optimisé avec Full-Text Search `FTS5`)
- **Web Scraping** : Selenium WebDriver, Chromium, BeautifulSoup4
- **Génération PDF** : `pdfkit` (basé sur `wkhtmltopdf`)
- **Traitement NLP** : `pyspellchecker` (pour la correction grammaticale des requêtes de scraping sans accents)

## 📚 Documentation API

La documentation complète de toutes les routes de l'API (Endpoints publics, gestion de file d'attente, administration, etc.) est disponible dans le fichier :

👉 **[API_DOCUMENTATION.md](./API_DOCUMENTATION.md)**

## 🚀 Installation & Déploiement

### Pré-requis système
Vous aurez besoin d'installer localement ou sur votre serveur :
- Python 3.12+
- `wkhtmltopdf` (pour la génération des PDF)
- `chromium-browser` et `chromedriver` (pour Selenium)

### Initialisation

1. **Cloner le projet :**
   ```bash
   git clone https://github.com/muarf/read-scraper-api.git
   cd read-scraper-api
   ```

2. **Installer les dépendances Python :**
   ```bash
   pip install -r requirements.txt
   ```

3. **Lancer le serveur :**
   ```bash
   ./start_api.sh
   ```
   *L'API sera disponible par défaut sur le port 5000.*

4. **Générer la première clé Admin :**
   Lors du tout premier lancement, visitez `http://<VOTRE_DOMAINE_OU_IP>:5000/init` pour générer la clé d'administration racine.

## 📱 Lien avec l'Application Mobile

L'application Android [PressScraper](https://github.com/muarf/pressscraper) est le client principal de cette API. Elle utilise la route `POST /api/v1/register` avec un identifiant de téléphone pour obtenir une clé d'accès, puis utilise l'API de partage Android (Intent) pour envoyer les liens des articles de presse directement à l'API via `POST /api/v1/scrape`.
