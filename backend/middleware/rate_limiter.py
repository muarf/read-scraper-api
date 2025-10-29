"""
Middleware de rate limiting
"""
from functools import wraps
from flask import request, jsonify
from datetime import datetime, timedelta
from backend.config.settings import RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW, ADMIN_RATE_LIMIT_REQUESTS
import logging

logger = logging.getLogger(__name__)


class RateLimiter:
    """Middleware de rate limiting"""
    
    def __init__(self):
        self.requests = {}  # {api_key: [(timestamp, ...), ...]}
    
    def _get_client_key(self) -> str:
        """Obtenir la clé unique du client"""
        api_key = request.headers.get('X-API-Key', 'anonymous')
        return api_key
    
    def _is_admin(self) -> bool:
        """Vérifier si le client est admin"""
        if hasattr(request, 'api_key_data'):
            return request.api_key_data.get('is_admin', False)
        return False
    
    def _cleanup_old_requests(self, client_key: str):
        """Nettoyer les anciennes requêtes pour un client"""
        now = datetime.now()
        cutoff = now - timedelta(seconds=RATE_LIMIT_WINDOW)
        
        if client_key in self.requests:
            self.requests[client_key] = [
                ts for ts in self.requests[client_key]
                if ts > cutoff
            ]
    
    def _check_rate_limit(self, client_key: str, max_requests: int) -> tuple[bool, dict]:
        """
        Vérifier si le client a dépassé sa limite
        
        Returns:
            tuple: (is_allowed, rate_limit_info)
        """
        now = datetime.now()
        self._cleanup_old_requests(client_key)
        
        # Obtenir les requêtes récentes
        if client_key not in self.requests:
            self.requests[client_key] = []
        
        recent_requests = self.requests[client_key]
        
        # Vérifier si on dépasse la limite
        if len(recent_requests) >= max_requests:
            return False, {
                'limit': max_requests,
                'remaining': 0,
                'reset_at': min(recent_requests) + timedelta(seconds=RATE_LIMIT_WINDOW)
            }
        
        # Ajouter cette requête
        recent_requests.append(now)
        self.requests[client_key] = recent_requests
        
        return True, {
            'limit': max_requests,
            'remaining': max_requests - len(recent_requests),
            'reset_at': min(recent_requests) + timedelta(seconds=RATE_LIMIT_WINDOW) if recent_requests else now
        }
    
    def rate_limit(self, f):
        """Decorator pour appliquer le rate limiting"""
        @wraps(f)
        def decorated_function(*args, **kwargs):
            client_key = self._get_client_key()
            is_admin = self._is_admin()
            
            # Déterminer la limite selon le type d'utilisateur
            max_requests = ADMIN_RATE_LIMIT_REQUESTS if is_admin else RATE_LIMIT_REQUESTS
            
            # Vérifier la limite
            is_allowed, rate_info = self._check_rate_limit(client_key, max_requests)
            
            if not is_allowed:
                return jsonify({
                    'error': 'Rate limit dépassé',
                    'message': f'Vous avez atteint la limite de {max_requests} requêtes par heure',
                    'limit': rate_info['limit'],
                    'remaining': rate_info['remaining'],
                    'reset_at': rate_info['reset_at'].isoformat()
                }), 429
            
            # Ajouter les infos de rate limit dans les headers
            response = f(*args, **kwargs)
            if isinstance(response, tuple) and len(response) == 2:
                # Flask response avec status code
                response_obj, status = response
                if hasattr(response_obj, 'headers'):
                    response_obj.headers['X-RateLimit-Limit'] = str(rate_info['limit'])
                    response_obj.headers['X-RateLimit-Remaining'] = str(rate_info['remaining'])
                    response_obj.headers['X-RateLimit-Reset'] = str(int(rate_info['reset_at'].timestamp()))
                return response_obj, status
            else:
                return response
        
        return decorated_function




