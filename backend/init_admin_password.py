"""
Script pour initialiser le mot de passe admin par défaut
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.database import Database
import hashlib

def init_default_password():
    """Initialiser le mot de passe admin par défaut"""
    db = Database()
    
    # Vérifier s'il y a déjà un mot de passe
    count = db.get_active_admin_password_count()
    
    if count == 0:
        # Créer le mot de passe par défaut
        default_password = 'admin123'
        db.create_admin_password(default_password)
        print(f"Mot de passe admin par défaut créé: {default_password}")
    else:
        print("Un mot de passe admin existe déjà")

if __name__ == '__main__':
    init_default_password()

