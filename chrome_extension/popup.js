document.getElementById('sendUrl').addEventListener('click', function() {
  chrome.tabs.query({active: true, currentWindow: true}, function(tabs) {
    var currentTab = tabs[0];
    var currentUrl = currentTab.url;

    chrome.runtime.sendMessage({action: 'sendUrl', url: currentUrl});
  });
});
