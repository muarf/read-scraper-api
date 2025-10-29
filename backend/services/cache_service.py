"""
Service de cache pour éviter les re-scraping inutiles
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from backend.models.database import Database
from backend.config.settings import CACHE_DURATION_HOURS
import logging

logger = logging.getLogger(__name__)


class CacheService:
    """Service de cache pour les articles"""
    
    def __init__(self, db: Database):
        self.db = db
    
    def is_cached(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Vérifier si une URL est déjà en cache
        Retourne l'article en cache ou None
        """
        article = self.db.get_article_by_url(url)
        
        if not article:
            return None
        
        # Vérifier si le cache est encore valide
        scraped_at = datetime.fromisoformat(article['scraped_at']) if article['scraped_at'] else None
        
        if scraped_at:
            cache_duration = timedelta(hours=CACHE_DURATION_HOURS)
            if datetime.now() - scraped_at < cache_duration:
                logger.info(f"Cache hit pour URL: {url}")
                return article
        
        logger.info(f"Cache expiré pour URL: {url}")
        return None
    
    def get_cached_article(self, url: str) -> Optional[Dict[str, Any]]:
        """Récupérer un article en cache (alias pour is_cached)"""
        return self.is_cached(url)
    
    def invalidate_cache(self, url: str):
        """Invalider le cache pour une URL spécifique"""
        article = self.db.get_article_by_url(url)
        if article:
            article_id = article['id']
            self.db.delete_article(article_id)
            logger.info(f"Cache invalidé pour URL: {url}")
    
    def invalidate_article(self, article_id: str):
        """Invalider le cache pour un article spécifique"""
        article = self.db.get_article(article_id)
        if article:
            self.db.delete_article(article_id)
            logger.info(f"Cache invalidé pour article: {article_id}")




