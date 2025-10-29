"""
Service Google Cloud Storage pour remplacer le stockage local
"""
import os
import tempfile
from pathlib import Path
from typing import Optional, Tuple
from google.cloud import storage
from google.api_core.exceptions import NotFound
import logging

logger = logging.getLogger(__name__)


class CloudStorageService:
    """Service pour gérer les fichiers sur Google Cloud Storage"""

    def __init__(self, bucket_name: str):
        """
        Initialise le service Cloud Storage

        Args:
            bucket_name: Nom du bucket Cloud Storage
        """
        self.bucket_name = bucket_name
        self.client = None
        self.bucket = None
        self._init_client()

    def _init_client(self):
        """Initialise le client Cloud Storage"""
        try:
            # En mode développement/test, on ne se connecte pas vraiment
            # Cela évite les erreurs d'authentification GCP
            if os.environ.get('SKIP_GCP_AUTH') == 'true':
                logger.info("Mode test: Cloud Storage simulé")
                self.client = None
                self.bucket = None
                return

            self.client = storage.Client()
            self.bucket = self.client.bucket(self.bucket_name)

            # Vérifier que le bucket existe
            if not self.bucket.exists():
                logger.warning(f"Bucket {self.bucket_name} n'existe pas, création...")
                self.bucket.create()
                logger.info(f"Bucket {self.bucket_name} créé")

        except Exception as e:
            logger.error(f"Erreur initialisation Cloud Storage: {e}")
            raise

    def upload_file(self, local_path: str, destination_name: str) -> str:
        """
        Upload un fichier vers Cloud Storage

        Args:
            local_path: Chemin du fichier local
            destination_name: Nom de destination dans le bucket

        Returns:
            URL publique du fichier
        """
        try:
            blob = self.bucket.blob(destination_name)
            blob.upload_from_filename(local_path)

            # Rendre le fichier public si c'est HTML/PDF
            if destination_name.endswith(('.html', '.pdf')):
                blob.make_public()

            public_url = blob.public_url
            logger.info(f"Fichier uploadé: {destination_name} -> {public_url}")

            return public_url

        except Exception as e:
            logger.error(f"Erreur upload {local_path}: {e}")
            raise

    def download_file(self, source_name: str, local_path: str) -> bool:
        """
        Download un fichier depuis Cloud Storage

        Args:
            source_name: Nom du fichier dans le bucket
            local_path: Chemin de destination local

        Returns:
            True si succès, False sinon
        """
        try:
            blob = self.bucket.blob(source_name)
            blob.download_to_filename(local_path)
            logger.info(f"Fichier téléchargé: {source_name} -> {local_path}")
            return True

        except NotFound:
            logger.warning(f"Fichier non trouvé: {source_name}")
            return False
        except Exception as e:
            logger.error(f"Erreur download {source_name}: {e}")
            return False

    def file_exists(self, file_name: str) -> bool:
        """
        Vérifie si un fichier existe dans le bucket

        Args:
            file_name: Nom du fichier

        Returns:
            True si le fichier existe
        """
        try:
            blob = self.bucket.blob(file_name)
            return blob.exists()
        except Exception as e:
            logger.error(f"Erreur vérification existence {file_name}: {e}")
            return False

    def delete_file(self, file_name: str) -> bool:
        """
        Supprime un fichier du bucket

        Args:
            file_name: Nom du fichier à supprimer

        Returns:
            True si succès
        """
        try:
            blob = self.bucket.blob(file_name)
            blob.delete()
            logger.info(f"Fichier supprimé: {file_name}")
            return True
        except NotFound:
            logger.warning(f"Fichier à supprimer non trouvé: {file_name}")
            return False
        except Exception as e:
            logger.error(f"Erreur suppression {file_name}: {e}")
            return False

    def get_signed_url(self, file_name: str, expiration_minutes: int = 60) -> str:
        """
        Génère une URL signée pour accès temporaire

        Args:
            file_name: Nom du fichier
            expiration_minutes: Durée de validité en minutes

        Returns:
            URL signée
        """
        try:
            blob = self.bucket.blob(file_name)
            url = blob.generate_signed_url(
                expiration_minutes * 60,
                method='GET'
            )
            return url
        except Exception as e:
            logger.error(f"Erreur génération URL signée {file_name}: {e}")
            raise

    def list_files(self, prefix: str = "") -> list:
        """
        Liste les fichiers avec un préfixe

        Args:
            prefix: Préfixe pour filtrer les fichiers

        Returns:
            Liste des noms de fichiers
        """
        try:
            blobs = self.bucket.list_blobs(prefix=prefix)
            return [blob.name for blob in blobs]
        except Exception as e:
            logger.error(f"Erreur listage fichiers prefix={prefix}: {e}")
            return []


class StorageService:
    """
    Service de stockage unifié - utilise Cloud Storage en cloud, local sinon
    """

    def __init__(self):
        from backend.config.settings import IS_CLOUD_ENV, GCS_BUCKET_NAME, STATIC_DIR

        self.is_cloud = IS_CLOUD_ENV
        self.static_dir = STATIC_DIR

        if self.is_cloud and GCS_BUCKET_NAME:
            self.cloud_storage = CloudStorageService(GCS_BUCKET_NAME)
        else:
            self.cloud_storage = None

    def save_file(self, content, filename: str) -> Tuple[str, str]:
        """
        Sauvegarde un fichier (HTML ou PDF)

        Args:
            content: Contenu du fichier (str pour HTML, bytes pour PDF)
            filename: Nom du fichier

        Returns:
            (local_path, public_url)
        """
        if self.is_cloud and self.cloud_storage:
            # Sauvegarde temporaire localement puis upload
            mode = 'wb' if isinstance(content, bytes) else 'w'
            encoding = None if isinstance(content, bytes) else 'utf-8'

            with tempfile.NamedTemporaryFile(mode=mode, suffix=f'_{filename}',
                                          delete=False, encoding=encoding) as f:
                f.write(content)
                temp_path = f.name

            try:
                # Upload vers Cloud Storage
                public_url = self.cloud_storage.upload_file(temp_path, filename)

                # Nettoyer le fichier temporaire
                os.unlink(temp_path)

                return temp_path, public_url

            except Exception as e:
                logger.error(f"Erreur sauvegarde cloud {filename}: {e}")
                # Fallback vers local
                return self._save_local(content, filename)

        else:
            # Sauvegarde locale
            return self._save_local(content, filename)

    def _save_local(self, content, filename: str) -> Tuple[str, str]:
        """Sauvegarde locale (fallback)"""
        file_path = self.static_dir / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)

        mode = 'wb' if isinstance(content, bytes) else 'w'
        encoding = None if isinstance(content, bytes) else 'utf-8'

        with open(file_path, mode, encoding=encoding) as f:
            f.write(content)

        # URL locale (pour développement)
        local_url = f"/static/{filename}"
        return str(file_path), local_url

    def get_file_url(self, filename: str) -> str:
        """
        Retourne l'URL publique d'un fichier

        Args:
            filename: Nom du fichier

        Returns:
            URL publique ou locale
        """
        if self.is_cloud and self.cloud_storage:
            # Vérifier si le fichier existe et retourner l'URL publique
            if self.cloud_storage.file_exists(filename):
                blob = self.cloud_storage.bucket.blob(filename)
                return blob.public_url
            else:
                return f"/static/{filename}"  # Fallback
        else:
            return f"/static/{filename}"

    def file_exists(self, filename: str) -> bool:
        """
        Vérifie si un fichier existe

        Args:
            filename: Nom du fichier

        Returns:
            True si le fichier existe
        """
        if self.is_cloud and self.cloud_storage:
            return self.cloud_storage.file_exists(filename)
        else:
            file_path = self.static_dir / filename
            return file_path.exists()
