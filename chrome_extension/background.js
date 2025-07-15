// background.js
let openedTabId = null;
chrome.action.onClicked.addListener(function(tab) {
  // Ouvre un nouvel onglet avec l'URL 127.0.0.1:5000
    // Récupère l'URL de l'onglet actif
    chrome.tabs.query({ active: true, currentWindow: true }, function(tabs) {
      var currentTab = tabs[0];
      var currentUrl = currentTab.url;

      chrome.tabs.create({ url: 'http://104.244.74.191:5000/', active: false  }, function(newTab) {
        // Ajoute un délai de 1 seconde avant d'envoyer la requête GET
        setTimeout(function() {
          // Effectue une requête GET à http://104.244.74.191:5000/ pour charger la page
          fetch('http://104.244.74.191:5000/')
          .then(response => {
            // Effectue la requête POST après le chargement de la page
            return fetch('http://104.244.74.191:5000/', {
              method: 'POST',
              headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
              },
              body: 'url=' + encodeURIComponent(currentUrl),
            });
          })
          .then(response => {
            chrome.tabs.update(newTab.id, { active: true });
          })
          .catch(error => {
            console.error('Error:', error);
          });
        }, 1000); // Délai de 1 seconde (1000 millisecondes)
      });
    });
});


chrome.tabs.onRemoved.addListener(function(tabId, removeInfo) {
  if (tabId === openedTabId) {
    // L'onglet ouvert par l'extension a été fermé
    // Envoie une notification au serveur ici
    fetch('http://104.244.74.191:5000/close', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: 'tabId=' + encodeURIComponent(tabId),
    })
    .then(response => {
      if (!response.ok) {
        throw new Error('Network response was not ok');
      }
      return response.text();
    })
    .catch(error => {
      console.error('Error:', error);
    });
  }
});
