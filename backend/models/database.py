"""
Modèles de base de données unifiés (SQLite local / PostgreSQL Cloud)
"""
import os
import sqlite3
import hashlib
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
from backend.config.settings import IS_CLOUD_ENV, DB_PATH, STATIC_DIR

logger = logging.getLogger(__name__)

# Factory function pour créer la bonne base de données
def create_database():
    """Factory function qui retourne la bonne implémentation DB selon l'environnement"""
    # Pour les tests ou développement, forcer SQLite même en mode cloud
    if IS_CLOUD_ENV and os.environ.get('SKIP_GCP_AUTH') != 'true':
        from backend.models.database_cloud import CloudDatabase
        return CloudDatabase()
    else:
        # Utiliser toujours SQLite pour les tests/développement
        return Database()


class Database:
    """Gestionnaire de base de données SQLite pour développement/local"""

    def __init__(self, db_path: Path = DB_PATH):
        # Toujours utiliser SQLite pour cette classe
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()
    
    def get_connection(self):
        """Retourne une connexion à la base de données"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_db(self):
        """Initialise le schéma de la base de données"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Table articles
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                id TEXT PRIMARY KEY,
                url TEXT NOT NULL UNIQUE,
                title TEXT,
                html_content TEXT,
                pdf_path TEXT,
                site_source TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                scraped_at TIMESTAMP,
                status TEXT DEFAULT 'completed',
                tags TEXT,
                metadata TEXT
            )
        """)
        
        # Index pour la recherche full-text (FTS5)
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
                id, url, title, html_content, content=articles, content_rowid=rowid
            )
        """)
        
        # Table scraping_jobs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scraping_jobs (
                id TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                article_id TEXT,
                status TEXT DEFAULT 'pending',
                priority INTEGER DEFAULT 0,
                error_message TEXT,
                retry_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                data TEXT,  -- Données JSON pour informations de debug
                FOREIGN KEY (article_id) REFERENCES articles(id)
            )
        """)
        
        # Table api_keys
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id TEXT PRIMARY KEY,
                key_hash TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                is_admin BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            )
        """)

        # Table pour les clés API temporaires
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS temp_api_keys (
                id TEXT PRIMARY KEY,
                key_hash TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                is_active BOOLEAN DEFAULT 1
            )
        """)
        
        # Table scraping_stats (agrégations par jour)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scraping_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL UNIQUE,
                total_scrapes INTEGER DEFAULT 0,
                successful_scrapes INTEGER DEFAULT 0,
                failed_scrapes INTEGER DEFAULT 0,
                avg_duration REAL
            )
        """)
        
        # Table admin_passwords
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admin_passwords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            )
        """)
        
        conn.commit()
        conn.close()
    
    def create_article(self, article_id: str, url: str, title: str = None, 
                       html_content: str = None, pdf_path: str = None, 
                       site_source: str = None, tags: str = None, 
                       metadata: str = None) -> bool:
        """Créer un nouvel article"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO articles (id, url, title, html_content, pdf_path, 
                                     site_source, scraped_at, tags, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (article_id, url, title, html_content, pdf_path, site_source, 
                  datetime.now(), tags, metadata))
            
            # Mise à jour de l'index FTS
            cursor.execute("""
                INSERT INTO articles_fts (rowid, id, url, title, html_content)
                VALUES ((SELECT rowid FROM articles WHERE id = ?), ?, ?, ?, ?)
            """, (article_id, article_id, url, title or "", html_content or ""))
            
            conn.commit()
            return True
        except sqlite3.IntegrityError as e:
            print(f"Erreur création article: {e}")
            return False
        finally:
            conn.close()
    
    def get_article(self, article_id: str) -> Optional[Dict[str, Any]]:
        """Récupérer un article par son ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM articles WHERE id = ?", (article_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return dict(row)
        return None
    
    def get_article_by_url(self, url: str) -> Optional[Dict[str, Any]]:
        """Récupérer un article par son URL"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM articles WHERE url = ?", (url,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return dict(row)
        return None
    
    def list_articles(self, limit: int = 50, offset: int = 0, 
                      search: str = None, site_source: str = None) -> List[Dict[str, Any]]:
        """Lister les articles avec pagination et filtres"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        query = "SELECT * FROM articles WHERE 1=1"
        params = []
        
        if search:
            query += " AND id IN (SELECT rowid FROM articles_fts WHERE articles_fts MATCH ?)"
            params.append(search)
        
        if site_source:
            query += " AND site_source = ?"
            params.append(site_source)
        
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def create_job(self, job_id: str, url: str, priority: int = 0) -> bool:
        """Créer un nouveau job de scraping"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO scraping_jobs (id, url, status, priority)
                VALUES (?, ?, 'pending', ?)
            """, (job_id, url, priority))
            conn.commit()
            return True
        except Exception as e:
            print(f"Erreur création job: {e}")
            return False
        finally:
            conn.close()
    
    def update_job_status(self, job_id: str, status: str,
                         article_id: str = None, error: str = None) -> bool:
        """Mettre à jour le statut d'un job"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            if status == 'processing':
                cursor.execute("""
                    UPDATE scraping_jobs 
                    SET status = ?, started_at = ?
                    WHERE id = ?
                """, (status, datetime.now(), job_id))
            
            elif status == 'completed':
                cursor.execute("""
                    UPDATE scraping_jobs 
                    SET status = ?, article_id = ?, completed_at = ?
                    WHERE id = ?
                """, (status, article_id, datetime.now(), job_id))
            
            elif status == 'failed':
                cursor.execute("""
                    UPDATE scraping_jobs 
                    SET status = ?, error_message = ?, completed_at = ?
                    WHERE id = ?
                """, (status, error, datetime.now(), job_id))
            
            elif status == 'cancelled':
                cursor.execute("""
                    UPDATE scraping_jobs 
                    SET status = ?, error_message = ?, completed_at = ?
                    WHERE id = ?
                """, (status, error or 'Job annulé par l\'utilisateur', datetime.now(), job_id))
            
            else:
                # Pour les autres statuts, mise à jour simple
                cursor.execute("""
                    UPDATE scraping_jobs 
                    SET status = ?
                    WHERE id = ?
                """, (status, job_id))
            
            conn.commit()
            return True
        except Exception as e:
            print(f"Erreur update job: {e}")
            return False
        finally:
            conn.close()
    
    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Récupérer un job par son ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM scraping_jobs WHERE id = ?", (job_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return dict(row)
        return None
    
    def get_pending_jobs(self) -> List[Dict[str, Any]]:
        """Récupérer les jobs en attente (excluant les annulés)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM scraping_jobs 
            WHERE status = 'pending' AND status != 'cancelled'
            ORDER BY priority DESC, created_at ASC
        """)
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def create_api_key(self, key_hash: str, name: str, is_admin: bool = False) -> bool:
        """Créer une nouvelle clé API"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            api_key_id = hashlib.sha256(f"{key_hash}{datetime.now()}".encode()).hexdigest()[:12]
            cursor.execute("""
                INSERT INTO api_keys (id, key_hash, name, is_admin)
                VALUES (?, ?, ?, ?)
            """, (api_key_id, key_hash, name, is_admin))
            conn.commit()
            return True
        except Exception as e:
            print(f"Erreur création clé API: {e}")
            return False
        finally:
            conn.close()
    
    def get_api_key_by_device(self, device_id: str) -> Optional[Dict[str, Any]]:
        """Vérifier si un device_id a déjà une clé API active"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM api_keys 
            WHERE name = ? AND is_active = 1
        """, (f"device:{device_id}",))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return dict(row)
        return None
    
    def verify_api_key(self, key_hash: str) -> Optional[Dict[str, Any]]:
        """Vérifier une clé API et mettre à jour last_used"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM api_keys 
            WHERE key_hash = ? AND is_active = 1
        """, (key_hash,))
        row = cursor.fetchone()
        
        if row:
            # Mettre à jour last_used
            cursor.execute("""
                UPDATE api_keys 
                SET last_used = ?
                WHERE id = ?
            """, (datetime.now(), row['id']))
            conn.commit()
            return dict(row)
        
        conn.close()
        return None
    
    def list_api_keys(self, is_admin: bool = None) -> List[Dict[str, Any]]:
        """Lister les clés API"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if is_admin is not None:
            cursor.execute("SELECT * FROM api_keys WHERE is_admin = ?", (is_admin,))
        else:
            cursor.execute("SELECT * FROM api_keys")
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def revoke_api_key(self, api_key_id: str) -> bool:
        """Révoquer une clé API"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE api_keys 
                SET is_active = 0 
                WHERE id = ?
            """, (api_key_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def create_temp_api_key(self, key_hash: str, expires_at) -> bool:
        """Créer une clé API temporaire"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            temp_key_id = hashlib.sha256(f"{key_hash}{datetime.now()}".encode()).hexdigest()[:12]
            cursor.execute("""
                INSERT INTO temp_api_keys (id, key_hash, expires_at)
                VALUES (?, ?, ?)
            """, (temp_key_id, key_hash, expires_at))
            conn.commit()
            return True
        except Exception as e:
            print(f"Erreur création clé API temporaire: {e}")
            return False
        finally:
            conn.close()

    def delete_article(self, article_id: str) -> bool:
        """Supprimer un article"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("DELETE FROM articles_fts WHERE id = ?", (article_id,))
            cursor.execute("DELETE FROM articles WHERE id = ?", (article_id,))
            conn.commit()
            return True
        except Exception as e:
            print(f"Erreur suppression article: {e}")
            return False
        finally:
            conn.close()
    
    def cleanup_old_data(self, days_articles: int = 90, days_jobs: int = 7, days_static_files: int = 7):
        """Nettoyer les données anciennes"""
        conn = self.get_connection()
        cursor = conn.cursor()

        articles_deleted = 0
        jobs_deleted = 0
        
        cutoff_date_articles = datetime.now() - timedelta(days=days_articles)
        cutoff_date_jobs = datetime.now() - timedelta(days=days_jobs)
        
        # Supprimer anciens articles
        cursor.execute("""
            DELETE FROM articles 
            WHERE created_at < ?
        """, (cutoff_date_articles,))
        articles_deleted = cursor.rowcount
        
        # Supprimer anciens jobs
        cursor.execute("""
            DELETE FROM scraping_jobs 
            WHERE created_at < ?
        """, (cutoff_date_jobs,))
        jobs_deleted = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        files_deleted = self._cleanup_static_files(days_static_files)

        if any([articles_deleted, jobs_deleted, files_deleted]):
            logger.info(
                "Nettoyage terminé: %s articles, %s jobs, %s fichiers supprimés",
                articles_deleted,
                jobs_deleted,
                files_deleted
            )
        
        return {
            'articles_deleted': articles_deleted,
            'jobs_deleted': jobs_deleted,
            'files_deleted': files_deleted,
            'logs_deleted': 0
        }

    def _cleanup_static_files(self, days_static_files: int) -> int:
        """Supprimer les fichiers statiques (HTML/PDF) plus anciens que la limite
        et les screenshots de debug (PNG) de plus de 3 jours."""
        cutoff_date = datetime.now() - timedelta(days=days_static_files)
        cutoff_debug = datetime.now() - timedelta(days=3)
        files_deleted = 0

        if not STATIC_DIR.exists():
            return 0

        for pattern in ("*.html", "*.pdf"):
            for file_path in STATIC_DIR.glob(pattern):
                try:
                    file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if file_mtime < cutoff_date:
                        file_path.unlink()
                        files_deleted += 1
                        logger.debug("Fichier statique supprimé: %s", file_path)
                except FileNotFoundError:
                    continue
                except Exception as e:
                    logger.warning("Impossible de supprimer %s: %s", file_path, e)

        # Nettoyer les screenshots de debug de plus de 3 jours
        for file_path in STATIC_DIR.glob("debug_*.png"):
            try:
                file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                if file_mtime < cutoff_debug:
                    file_path.unlink()
                    files_deleted += 1
                    logger.debug("Screenshot debug supprimé: %s", file_path)
            except FileNotFoundError:
                continue
            except Exception as e:
                logger.warning("Impossible de supprimer %s: %s", file_path, e)

        return files_deleted

    # Méthodes héritées pour compatibilité descendante
    def cleanup_old_articles(self, days: int = 30) -> int:
        """Compatibilité avec l'ancienne API qui nettoyait uniquement les articles."""
        result = self.cleanup_old_data(
            days_articles=days,
            days_jobs=0,
            days_static_files=0
        )
        return result.get('articles_deleted', 0)
    
    def verify_admin_password(self, password: str) -> bool:
        """Vérifier un mot de passe admin"""
        import hashlib
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM admin_passwords 
            WHERE password_hash = ? AND is_active = 1
        """, (password_hash,))
        
        row = cursor.fetchone()
        conn.close()
        
        return row is not None
    
    def create_admin_password(self, password: str) -> bool:
        """Créer un nouveau mot de passe admin"""
        import hashlib
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Désactiver tous les anciens mots de passe
        cursor.execute("UPDATE admin_passwords SET is_active = 0")
        
        # Créer le nouveau
        cursor.execute("""
            INSERT INTO admin_passwords (password_hash)
            VALUES (?)
        """, (password_hash,))
        
        conn.commit()
        conn.close()
        
        return True
    
    def get_active_admin_password_count(self) -> int:
        """Compter les mots de passe admin actifs"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM admin_passwords WHERE is_active = 1")
        count = cursor.fetchone()[0]

        conn.close()
        return count

    def get_job_by_article_id(self, article_id: str) -> Optional[Dict[str, Any]]:
        """Récupérer un job par l'ID de son article"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM scraping_jobs WHERE article_id = ?", (article_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return None

    def update_job_data(self, job_id: str, data: dict) -> bool:
        """Mettre à jour les données JSON d'un job"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                UPDATE scraping_jobs
                SET data = ?
                WHERE id = ?
            """, (json.dumps(data), job_id))

            conn.commit()
            return cursor.rowcount > 0

        except Exception as e:
            print(f"Erreur mise à jour données job {job_id}: {e}")  # Utiliser print au lieu de logger
            return False

        finally:
            conn.close()

    def list_all_jobs(self):
        """Méthode helper pour lister tous les jobs"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM scraping_jobs ORDER BY created_at DESC")
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
