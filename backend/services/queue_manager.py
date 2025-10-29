"""
Gestionnaire de queue pour les jobs de scraping
"""
import threading
import time
from typing import Optional
from backend.models.database import Database
from backend.config.settings import JOB_TIMEOUT, MAX_RETRIES
import logging

logger = logging.getLogger(__name__)


class QueueManager:
    """Gestionnaire de queue pour les jobs de scraping"""
    
    def __init__(self, db: Database, scraper_callback):
        self.db = db
        self.scraper_callback = scraper_callback
        self.worker_thread = None
        self.is_running = False
        self._lock = threading.Lock()
    
    def start(self):
        """Démarrer le worker de queue"""
        with self._lock:
            if self.is_running:
                return
            
            self.is_running = True
            self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self.worker_thread.start()
            logger.info("Queue manager démarré")
    
    def stop(self):
        """Arrêter le worker de queue"""
        with self._lock:
            if not self.is_running:
                return
            
            self.is_running = False
            if self.worker_thread:
                self.worker_thread.join(timeout=5)
            logger.info("Queue manager arrêté")
    
    def _worker_loop(self):
        """Boucle principale du worker"""
        while self.is_running:
            try:
                pending_jobs = self.db.get_pending_jobs()
                
                if pending_jobs:
                    logger.info(f"Traitement de {len(pending_jobs)} job(s) en attente")
                    
                    for job in pending_jobs:
                        if not self.is_running:
                            break
                        
                        try:
                            self._process_job(job)
                        except Exception as e:
                            logger.error(f"Erreur traitement job {job['id']}: {e}")
                            self.db.update_job_status(job['id'], 'failed', error=str(e))
                
                # Attendre avant de vérifier à nouveau
                time.sleep(1)
            
            except Exception as e:
                logger.error(f"Erreur dans worker loop: {e}")
                time.sleep(5)
    
    def _process_job(self, job: dict):
        """Traiter un job de scraping"""
        job_id = job['id']
        url = job['url']
        
        logger.info(f"Début traitement job {job_id} pour URL: {url}")
        
        # Mettre à jour le statut à 'processing'
        self.db.update_job_status(job_id, 'processing')
        
        # Démarrer le timer
        start_time = time.time()
        
        try:
            # Appeler la fonction de scraping
            result = self.scraper_callback(url, job_id)
            
            if result:
                article_id, article_data = result
                
                # Mettre à jour le statut à 'completed'
                self.db.update_job_status(job_id, 'completed', article_id=article_id)
                
                duration = time.time() - start_time
                logger.info(f"Job {job_id} complété avec succès en {duration:.2f}s")
            else:
                raise Exception("Scraping échoué: résultat vide")
        
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Erreur traitement job {job_id}: {error_msg}")
            
            # Incrémenter retry_count
            retry_count = self.db.get_job(job_id).get('retry_count', 0) + 1
            
            if retry_count < MAX_RETRIES:
                logger.info(f"Retry job {job_id} ({retry_count}/{MAX_RETRIES})")
                conn = self.db.get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE scraping_jobs 
                    SET status = 'pending', retry_count = ?
                    WHERE id = ?
                """, (retry_count, job_id))
                conn.commit()
                conn.close()
            else:
                self.db.update_job_status(job_id, 'failed', error=error_msg)
                logger.error(f"Job {job_id} définitivement échoué après {retry_count} tentatives")
        
        # Vérifier le timeout
        if time.time() - start_time > JOB_TIMEOUT:
            logger.warning(f"Job {job_id} a dépassé le timeout de {JOB_TIMEOUT}s")
            self.db.update_job_status(job_id, 'failed', error=f"Timeout après {JOB_TIMEOUT}s")




