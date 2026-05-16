# Clarification de l'Architecture : Modèle "Cookie-Relay" (Hybride Serveur/Mobile)

⚠️ **ATTENTION :** Ce plan ne propose PAS de faire tourner Python, Flask ou Selenium sur le téléphone mobile. Tout le code lourd reste sur le serveur Oracle.

## 1. Répartition des Rôles (Tranchée)

### 🖥️ LE SERVEUR (Oracle Cloud - Backend)
- **Rôle** : Moteur d'exécution principal.
- **Stack** : Python, Flask, Selenium, Chromedriver, WeasyPrint.
- **Responsabilité** : Reçoit une requête avec des cookies, lance le navigateur headless (Selenium) sur le serveur, extrait l'article, génère le PDF.
- **Pourquoi ?** Parce que Selenium et WeasyPrint sont impossibles/trop lourds à faire tourner proprement sur Android/iOS.

### 📱 LE TÉLÉPHONE (App Mobile - Frontend)
- **Rôle** : Interface utilisateur et "Générateur de session".
- **Stack** : Capacitor / React (Webview native).
- **Responsabilité** :
    1. L'utilisateur se connecte à ses journaux via une WebView dans l'app.
    2. L'app extrait les **Cookies de session** (ezproxy, sessions journaux).
    3. L'app envoie l'URL à scraper + les Cookies au serveur Oracle.
- **Pourquoi ?** Pour que l'utilisateur utilise ses propres comptes sans jamais confier ses mots de passe au serveur (seuls les cookies transitent).

---

## 2. Pourquoi ce n'est pas "Flask embarqué" ?
Contrairement à ce qu'un autre agent pourrait penser, il n'y a **AUCUN backend sur le mobile**.
- L'app mobile est une simple application web (HTML/JS) packagée.
- Elle communique via HTTPS avec l'API Flask qui tourne déjà sur `presse.qzz.io`.

---

## 3. Flux de travail détaillé (User Story)
1.  **L'utilisateur** ouvre l'app sur Android.
2.  **L'app** vérifie si elle a des cookies valides pour Europresse (via une WebView cachée).
3.  **L'utilisateur** partage un lien d'article vers l'app.
4.  **L'app** fait un `POST https://presse.qzz.io/api/v1/scrape` en passant les cookies dans le JSON.
5.  **Le serveur Oracle** (en prod) reçoit les cookies, les injecte dans sa session Selenium, et télécharge l'article.
6.  **Le serveur** renvoie l'ID du job.
7.  **L'app** télécharge le PDF final une fois prêt.

---

## 4. Conclusion pour les autres agents
Ne cherchez pas à porter le code Python sur mobile. Le travail consiste à :
1.  **Côté Serveur** : Permettre à l'API actuelle de recevoir et d'utiliser des cookies externes (déjà amorcé dans la branche `feature/mobile-hybrid`).
2.  **Côté Mobile** : Développer une interface simple capable de capturer les cookies d'une WebView et de les envoyer au serveur.
