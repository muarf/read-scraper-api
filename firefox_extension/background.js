// background.js

// Fonction pour ouvrir un nouvel onglet avec une URL spécifique
function openNewTab(url) {
    browser.tabs.create({
        url: url,
        active: false
    }).then(newTab => {
        // Effectue une requête POST à l'URL avec l'URL de l'onglet actif en tant que corps de la requête
        browser.tabs.query({ active: true, currentWindow: true }).then(tabs => {
            var currentTab = tabs[0];
            var currentUrl = currentTab.url;

            fetch('http://ensemblevocalsaintseverin.fr:5000/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: 'url=' + encodeURIComponent(currentUrl),
            })
            .then(response => {
                // Met à jour le nouvel onglet pour le rendre actif
                browser.tabs.update(newTab.id, { active: true });
            })
            .catch(error => {
                console.error('Erreur :', error);
            });
        });
    });
}

// Écouteur d'événement déclenché lorsque l'action de l'extension est cliquée
browser.browserAction.onClicked.addListener(function(tab) {
    // Ouvre un nouvel onglet avec une URL spécifique
    openNewTab('http://ensemblevocalsaintseverin.fr:5000/');
});

// Écouteur d'événement déclenché lorsque l'onglet est fermé
browser.tabs.onRemoved.addListener(function(tabId, removeInfo) {
    // Envoie une notification au serveur
    fetch('http://ensemblevocalsaintseverin.fr:5000/close', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: 'tabId=' + encodeURIComponent(tabId),
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('La réponse réseau n\'est pas valide');
        }
        return response.text();
    })
    .catch(error => {
        console.error('Erreur :', error);
    });
});
