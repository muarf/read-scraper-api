"""
Base de données PostgreSQL pour Google Cloud SQL
"""
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse
import logging

logger = logging.getLogger(__name__)


class CloudDatabase:
    """Gestionnaire de base de données PostgreSQL pour Cloud SQL"""

    def __init__(self, connection_string: str = None):
        """
        Initialise la connexion PostgreSQL

        Args:
            connection_string: URL de connexion PostgreSQL
        """
        if connection_string is None:
            from backend.config.settings import DATABASE_URL
            connection_string = DATABASE_URL

        self.connection_string = connection_string
        self._init_db()

    def get_connection(self):
        """Retourne une connexion à la base de données"""
        return psycopg2.connect(self.connection_string, cursor_factory=RealDictCursor)

    def _init_db(self):
        """Initialise le schéma de la base de données PostgreSQL"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Table articles
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS articles (
                    id TEXT PRIMARY KEY,
                    url TEXT NOT NULL UNIQUE,
                    title TEXT,
                    html_content TEXT,
                    pdf_path TEXT,
                    site_source TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    tags TEXT,
                    metadata JSONB
                );

                CREATE INDEX IF NOT EXISTS idx_articles_url ON articles(url);
                CREATE INDEX IF NOT EXISTS idx_articles_created_at ON articles(created_at DESC);
            """)

            # Table api_keys
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    key_hash TEXT NOT NULL UNIQUE,
                    is_admin BOOLEAN DEFAULT FALSE,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    last_used TIMESTAMP WITH TIME ZONE,
                    usage_count INTEGER DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_api_keys_key_hash ON api_keys(key_hash);
            """)

            # Table jobs
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP WITH TIME ZONE,
                    completed_at TIMESTAMP WITH TIME ZONE,
                    error_message TEXT,
                    result JSONB
                );

                CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
                CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC);
            """)

            # Table cleanup_log
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cleanup_log (
                    id SERIAL PRIMARY KEY,
                    action TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT,
                    details JSONB,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)

            conn.commit()
            logger.info("Schéma PostgreSQL initialisé avec succès")

        except Exception as e:
            conn.rollback()
            logger.error(f"Erreur initialisation schéma PostgreSQL: {e}")
            raise
        finally:
            cursor.close()
            conn.close()

    def create_article(self, article_id: str, url: str, title: str = None,
                      html_content: str = None, pdf_path: str = None,
                      site_source: str = None, tags: str = None,
                      metadata: dict = None):
        """Crée un nouvel article"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO articles (id, url, title, html_content, pdf_path, site_source, tags, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    title = EXCLUDED.title,
                    html_content = EXCLUDED.html_content,
                    pdf_path = EXCLUDED.pdf_path,
                    site_source = EXCLUDED.site_source,
                    tags = EXCLUDED.tags,
                    metadata = EXCLUDED.metadata
            """, (article_id, url, title, html_content, pdf_path, site_source, tags, metadata))

            conn.commit()
            logger.info(f"Article créé/modifié: {article_id}")

        except Exception as e:
            conn.rollback()
            logger.error(f"Erreur création article {article_id}: {e}")
            raise
        finally:
            cursor.close()
            conn.close()

    def get_article(self, article_id: str) -> Optional[Dict[str, Any]]:
        """Récupère un article par son ID"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT * FROM articles WHERE id = %s", (article_id,))
            row = cursor.fetchone()

            if row:
                # Convertir RealDictRow en dict
                return dict(row)
            return None

        except Exception as e:
            logger.error(f"Erreur récupération article {article_id}: {e}")
            return None
        finally:
            cursor.close()
            conn.close()

    def get_articles(self, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        """Récupère une liste d'articles"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM articles
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """, (limit, offset))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"Erreur récupération articles: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def delete_article(self, article_id: str) -> bool:
        """Supprime un article"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("DELETE FROM articles WHERE id = %s", (article_id,))
            deleted = cursor.rowcount > 0
            conn.commit()

            if deleted:
                logger.info(f"Article supprimé: {article_id}")
            else:
                logger.warning(f"Article non trouvé pour suppression: {article_id}")

            return deleted

        except Exception as e:
            conn.rollback()
            logger.error(f"Erreur suppression article {article_id}: {e}")
            return False
        finally:
            cursor.close()
            conn.close()

    # API Keys methods
    def create_api_key(self, key_id: str, name: str, key_hash: str,
                      is_admin: bool = False) -> bool:
        """Crée une nouvelle clé API"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO api_keys (id, name, key_hash, is_admin)
                VALUES (%s, %s, %s, %s)
            """, (key_id, name, key_hash, is_admin))

            conn.commit()
            logger.info(f"Clé API créée: {name}")
            return True

        except Exception as e:
            conn.rollback()
            logger.error(f"Erreur création clé API {name}: {e}")
            return False
        finally:
            cursor.close()
            conn.close()

    def get_api_key(self, key_hash: str) -> Optional[Dict[str, Any]]:
        """Récupère une clé API par son hash"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM api_keys
                WHERE key_hash = %s AND is_active = TRUE
            """, (key_hash,))

            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

        except Exception as e:
            logger.error(f"Erreur récupération clé API: {e}")
            return None
        finally:
            cursor.close()
            conn.close()

    def get_api_keys(self) -> List[Dict[str, Any]]:
        """Récupère toutes les clés API"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT * FROM api_keys ORDER BY created_at DESC")
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"Erreur récupération clés API: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def update_api_key_usage(self, key_id: str):
        """Met à jour la dernière utilisation d'une clé API"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                UPDATE api_keys
                SET last_used = CURRENT_TIMESTAMP,
                    usage_count = usage_count + 1
                WHERE id = %s
            """, (key_id,))

            conn.commit()

        except Exception as e:
            conn.rollback()
            logger.error(f"Erreur mise à jour utilisation clé API {key_id}: {e}")
        finally:
            cursor.close()
            conn.close()

    # Jobs methods
    def create_job(self, job_id: str, url: str) -> bool:
        """Crée un nouveau job"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO jobs (id, url, status)
                VALUES (%s, %s, 'pending')
            """, (job_id, url))

            conn.commit()
            logger.info(f"Job créé: {job_id}")
            return True

        except Exception as e:
            conn.rollback()
            logger.error(f"Erreur création job {job_id}: {e}")
            return False
        finally:
            cursor.close()
            conn.close()

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Récupère un job par son ID"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT * FROM jobs WHERE id = %s", (job_id,))
            row = cursor.fetchone()

            if row:
                return dict(row)
            return None

        except Exception as e:
            logger.error(f"Erreur récupération job {job_id}: {e}")
            return None
        finally:
            cursor.close()
            conn.close()

    def update_job_status(self, job_id: str, status: str,
                         error_message: str = None, result: dict = None):
        """Met à jour le statut d'un job"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            now = datetime.utcnow()

            if status == 'processing':
                cursor.execute("""
                    UPDATE jobs
                    SET status = %s, started_at = %s
                    WHERE id = %s
                """, (status, now, job_id))
            elif status in ['completed', 'failed']:
                cursor.execute("""
                    UPDATE jobs
                    SET status = %s, completed_at = %s,
                        error_message = %s, result = %s
                    WHERE id = %s
                """, (status, now, error_message, result, job_id))
            else:
                cursor.execute("""
                    UPDATE jobs
                    SET status = %s
                    WHERE id = %s
                """, (status, job_id))

            conn.commit()
            logger.info(f"Job {job_id} mis à jour: {status}")

        except Exception as e:
            conn.rollback()
            logger.error(f"Erreur mise à jour job {job_id}: {e}")
        finally:
            cursor.close()
            conn.close()

    def get_jobs(self, status: str = None, limit: int = 20) -> List[Dict[str, Any]]:
        """Récupère une liste de jobs"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            if status:
                cursor.execute("""
                    SELECT * FROM jobs
                    WHERE status = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (status, limit))
            else:
                cursor.execute("""
                    SELECT * FROM jobs
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (limit,))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"Erreur récupération jobs: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def cleanup_old_data(self, days_articles: int = 90,
                        days_jobs: int = 7, days_logs: int = 30):
        """Nettoie les anciennes données"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Nettoyer les anciens articles
            cutoff_articles = datetime.utcnow() - timedelta(days=days_articles)
            cursor.execute("""
                DELETE FROM articles
                WHERE created_at < %s
            """, (cutoff_articles,))
            articles_deleted = cursor.rowcount

            # Nettoyer les anciens jobs
            cutoff_jobs = datetime.utcnow() - timedelta(days=days_jobs)
            cursor.execute("""
                DELETE FROM jobs
                WHERE created_at < %s
            """, (cutoff_jobs,))
            jobs_deleted = cursor.rowcount

            # Nettoyer les anciens logs
            cutoff_logs = datetime.utcnow() - timedelta(days=days_logs)
            cursor.execute("""
                DELETE FROM cleanup_log
                WHERE created_at < %s
            """, (cutoff_logs,))
            logs_deleted = cursor.rowcount

            conn.commit()

            logger.info(f"Nettoyage effectué: {articles_deleted} articles, {jobs_deleted} jobs, {logs_deleted} logs")

            # Logger le nettoyage
            cursor.execute("""
                INSERT INTO cleanup_log (action, target_type, details)
                VALUES (%s, %s, %s)
            """, ('cleanup', 'multiple',
                  {'articles_deleted': articles_deleted,
                   'jobs_deleted': jobs_deleted,
                   'logs_deleted': logs_deleted}))

            conn.commit()

        except Exception as e:
            conn.rollback()
            logger.error(f"Erreur nettoyage: {e}")
        finally:
            cursor.close()
            conn.close()
