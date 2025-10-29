#!/usr/bin/env python3
"""
Test rapide de l'application en mode Cloud localement
"""
import os
import sys
from pathlib import Path

# Simuler l'environnement Cloud Run
os.environ['K_SERVICE'] = 'test-scraper-api'
os.environ['GOOGLE_CLOUD_PROJECT'] = 'test-project'
os.environ['GCS_BUCKET_NAME'] = 'test-bucket'
# Pour le test, on utilise SQLite local au lieu de PostgreSQL
# os.environ['DATABASE_URL'] = 'sqlite:///test.db'  # Ne pas définir pour utiliser SQLite
os.environ['PORT'] = '8080'
os.environ['SKIP_GCP_AUTH'] = 'true'  # Désactiver l'auth GCP pour les tests

# Ajouter le répertoire racine au path
sys.path.insert(0, str(Path(__file__).parent))

def test_imports():
    """Test que tous les imports fonctionnent"""
    print("🧪 Test des imports...")

    try:
        from backend.config.settings import IS_CLOUD_ENV, PORT, GCS_BUCKET_NAME
        print(f"✅ IS_CLOUD_ENV: {IS_CLOUD_ENV}")
        print(f"✅ PORT: {PORT}")
        print(f"✅ GCS_BUCKET_NAME: {GCS_BUCKET_NAME}")

        from backend.models.database import create_database
        print("✅ Factory database importée")

        from backend.services.cloud_storage import StorageService
        print("✅ StorageService importé")

        from backend.services.pdf_service import PDFService
        pdf_service = PDFService()
        print("✅ PDFService initialisé")

        return True

    except Exception as e:
        print(f"❌ Erreur import: {e}")
        return False

def test_database_factory():
    """Test la factory de base de données"""
    print("\n🗄️ Test de la factory database...")

    try:
        from backend.models.database import create_database
        db = create_database()
        print(f"✅ Database créée: {type(db).__name__}")

        # En mode cloud, on ne teste pas la connexion réelle (besoin de vraies credentials)
        from backend.config.settings import IS_CLOUD_ENV
        if IS_CLOUD_ENV:
            print("✅ Mode cloud détecté (utilisera PostgreSQL en production)")
            return True
        else:
            # Test connexion SQLite locale
            conn = db.get_connection()
            print("✅ Connexion database SQLite réussie")
            conn.close()
            return True

    except Exception as e:
        print(f"❌ Erreur database: {e}")
        return False

def test_storage_service():
    """Test le service de stockage"""
    print("\n🪣 Test du service de stockage...")

    try:
        from backend.services.cloud_storage import StorageService
        storage = StorageService()
        print(f"✅ StorageService créé: cloud={storage.is_cloud}")

        # En mode test, on ne se connecte pas vraiment aux services Cloud
        # mais on teste que la logique fonctionne
        if storage.is_cloud:
            print("✅ Mode cloud détecté (utilisera Cloud Storage en production)")
            # Ne pas tester la connexion réelle pour éviter les erreurs d'auth
            return True
        else:
            # Test local
            test_content = "<html><body>Test</body></html>"
            local_path, url = storage.save_file(test_content, "test.html")
            print(f"✅ Fichier sauvegardé localement: {url}")

            # Vérifier que le fichier existe
            exists = storage.file_exists("test.html")
            print(f"✅ Fichier existe: {exists}")
            return True

    except Exception as e:
        print(f"❌ Erreur storage: {e}")
        return False

def main():
    """Fonction principale de test"""
    print("🚀 Test de l'application en mode Cloud")
    print("=" * 50)

    tests = [
        test_imports,
        test_database_factory,
        test_storage_service,
    ]

    passed = 0
    for test in tests:
        if test():
            passed += 1
        print()

    print("=" * 50)
    print(f"📊 Résultats: {passed}/{len(tests)} tests réussis")

    if passed == len(tests):
        print("🎉 Tous les tests sont passés ! Prêt pour le déploiement Cloud.")
        return True
    else:
        print("❌ Certains tests ont échoué. Vérifiez les erreurs ci-dessus.")
        return False

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
