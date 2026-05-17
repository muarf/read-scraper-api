
import json
import re
import os
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class OphirofoxEngine:
    def __init__(self, op_dir="/app/web_scraper/ophirofox/ophirofox"):
        self.op_dir = Path(op_dir)
        self.manifest_path = self.op_dir / "manifest.json"
        self.mappings = []
        self._load_manifest()

    def _load_manifest(self):
        try:
            if not self.manifest_path.exists():
                logger.error(f"Manifest Ophirofox introuvable: {self.manifest_path}")
                return

            with open(self.manifest_path, 'r') as f:
                data = json.load(f)
            
            for entry in data.get("content_scripts", []):
                matches = entry.get("matches", [])
                js_files = entry.get("js", [])
                
                # Convertir les patterns Ophirofox (globs) en regex Python
                regexes = [self._glob_to_regex(m) for m in matches]
                self.mappings.append({
                    "regexes": regexes,
                    "js_files": js_files
                })
            logger.info(f"Ophirofox Engine chargé avec {len(self.mappings)} mappings.")
        except Exception as e:
            logger.error(f"Erreur lors du chargement du manifest Ophirofox: {e}")

    def _glob_to_regex(self, pattern):
        # Conversion simplifiée des match patterns d'extensions Chrome
        # https://developer.chrome.com/docs/extensions/mv3/match_patterns/
        p = pattern.replace(".", "\\.").replace("*", ".*").replace("?", "\\?")
        if p.startswith("http"):
            return re.compile(f"^{p}$")
        return re.compile(p)

    def get_scripts_for_url(self, url):
        scripts = []
        for mapping in self.mappings:
            if any(regex.match(url) for regex in mapping["regexes"]):
                scripts.extend(mapping["js_files"])
        
        # Enlever les doublons tout en gardant l'ordre
        unique_scripts = []
        for s in scripts:
            if s not in unique_scripts:
                unique_scripts.append(s)
        
        return unique_scripts

    def get_js_injection(self, url):
        scripts = self.get_scripts_for_url(url)
        if not scripts:
            return None

        full_js = []
        # 1. SHIM pour mocker l'environnement d'extension
        shim = """
        window.ophirofox_results = null;
        window.chrome = window.chrome || {};
        window.chrome.storage = {
            local: {
                get: (keys, cb) => cb({}),
                set: (data, cb) => { if(cb) cb(); },
                remove: (keys, cb) => { if(cb) cb(); }
            }
        };
        window.chrome.runtime = {
            getManifest: () => ({ browser_specific_settings: { ophirofox_metadata: { partners: [{ name: "Default", AUTH_URL: "" }] } } })
        };
        
        // Mock de ophirofoxEuropresseLink pour capturer les données
        window.ophirofoxEuropresseLink = async function(keywords, options) {
            console.log("Ophirofox captured keywords:", keywords);
            let date = "";
            if (options && options.publishedTime) {
                date = options.publishedTime;
            }
            
            window.ophirofox_results = {
                keywords: keywords,
                published_time: date,
                url: window.location.href
            };
            return document.createElement("a");
        };

        // Bypass des cookie walls (CMPS)
        function bypassCookieWalls() {
            const selectors = [
                '#didomi-host', '.didomi-popup-container', '[id^="sp_message_container"]',
                '#onetrust-banner-sdk', '#consent_blackbar', '.qc-cmp2-container',
                '.sd-cmp-container', '#cmp-container-id', '.cookie-banner'
            ];
            selectors.forEach(s => {
                const el = document.querySelector(s);
                if (el) {
                    console.log("Ophirofox Bridge: Removing cookie wall", s);
                    el.remove();
                }
            });
            document.body.style.overflow = 'auto';
            document.documentElement.style.overflow = 'auto';
            document.body.classList.remove('didomi-popup-open');
        }
        bypassCookieWalls();
        """
        full_js.append(shim)

        # 2. Charger le contenu des scripts
        for script_rel_path in scripts:
            script_path = self.op_dir / script_rel_path
            if script_path.exists():
                with open(script_path, 'r') as f:
                    full_js.append(f"// --- {script_rel_path} ---\n" + f.read())
            else:
                logger.warning(f"Script Ophirofox manquant: {script_path}")

        # 3. Code pour attendre et retourner les résultats
        # On définit un wrapper qui tente d'extraire les données après le chargement des scripts
        wrapper = """
        (async () => {
            // Bypass immédiat et répété
            const bypass = () => {
                const selectors = ['#didomi-host', '.didomi-popup-container', '.sp_message_container', '#onetrust-banner-sdk'];
                selectors.forEach(s => document.querySelectorAll(s).forEach(el => el.remove()));
                document.body.style.overflow = 'auto';
                document.documentElement.style.overflow = 'auto';
                document.body.classList.remove('didomi-popup-open');
            };
            
            for(let i=0; i<5; i++) { 
                bypass();
                await new Promise(r => setTimeout(r, 1000));
                
                if (window.ophirofox_results && !window.ophirofox_results.keywords.toLowerCase().includes("continu")) break;
                
                console.log("Ophirofox: Tentative d'extraction...");
                let keywords = "";
                
                // 1. Essayer le spécifique extractKeywords() défini par Ophirofox
                if (typeof extractKeywords === 'function') {
                    try { keywords = extractKeywords(); } catch(e) {}
                }
                
                // 2. Fallback intelligent si Keywords est vide ou générique
                if (!keywords || keywords.toLowerCase().includes("continu") || keywords.length < 10) {
                    // Sélecteurs spécifiques pour Ouest-France et autres sites récalcitrants
                    const specificSelectors = [
                        'h1.title-news', 'h1.ser-article-title', 'article h1', 
                        '.article-header h1', 'h1.main-title',
                        'meta[property="og:title"]', 'meta[name="twitter:title"]'
                    ];
                    
                    for (let sel of specificSelectors) {
                        let el = sel.startsWith('meta') ? document.querySelector(sel) : document.querySelector(sel);
                        if (el) {
                            keywords = sel.startsWith('meta') ? el.content : el.textContent.trim();
                            if (keywords && !keywords.toLowerCase().includes("continu")) break;
                        }
                    }
                }

                if (keywords && keywords.length > 15 && !keywords.toLowerCase().includes("continu")) {
                    window.ophirofox_results = {
                        keywords: keywords,
                        published_time: document.querySelector("meta[property='article:published_time']")?.content || "",
                        url: window.location.href,
                        captured_via: "bridge_persistent"
                    };
                    break;
                }
            }
        })();
        """
        full_js.append(wrapper)
        
        return "\n".join(full_js)
