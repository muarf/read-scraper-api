#!/usr/bin/env python3
"""
Script de démarrage de l'API
"""
import sys
from pathlib import Path

# Ajouter le répertoire racine au PYTHONPATH
root_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(root_dir))

# Importer et lancer l'application
if __name__ == '__main__':
    from backend.main import app
    import logging
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger = logging.getLogger(__name__)
    logger.info("Demarrage de l'API Scraper")
    logger.info(f"Repertoire: {root_dir}")
    
    app.run(host='0.0.0.0', port=5000, debug=True)




