"""
Middleware d'authentification par API key
"""
from functools import wraps
from flask import request, jsonify
from backend.models.database import Database
import hashlib
import logging

logger = logging.getLogger(__name__)


class AuthMiddleware:
    """Middleware d'authentification par API key"""
    
    def __init__(self, db: Database):
        self.db = db
    
    def require_api_key(self, f):
        """Decorator pour exiger une clé API"""
        @wraps(f)
        def decorated_function(*args, **kwargs):
            api_key = request.headers.get('X-API-Key')
            
            if not api_key:
                return jsonify({
                    'error': 'API key manquante',
                    'message': 'Vous devez fournir une clé API dans le header X-API-Key'
                }), 401
            
            # Hasher la clé pour vérification
            key_hash = hashlib.sha256(api_key.encode()).hexdigest()
            
            # Vérifier la clé dans la BDD
            api_key_data = self.db.verify_api_key(key_hash)
            
            if not api_key_data:
                return jsonify({
                    'error': 'API key invalide',
                    'message': 'La clé API fournie est invalide ou révoquée'
                }), 401
            
            # Ajouter les données de la clé API au contexte de la requête
            request.api_key_data = api_key_data
            
            return f(*args, **kwargs)
        
        return decorated_function
    
    def require_admin(self, f):
        """Decorator pour exiger une clé API admin"""
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Vérifier d'abord la clé API
            if not hasattr(request, 'api_key_data'):
                api_key = request.headers.get('X-API-Key')
                
                if not api_key:
                    return jsonify({
                        'error': 'API key manquante',
                        'message': 'Vous devez fournir une clé API dans le header X-API-Key'
                    }), 401
                
                key_hash = hashlib.sha256(api_key.encode()).hexdigest()
                api_key_data = self.db.verify_api_key(key_hash)
                
                if not api_key_data:
                    return jsonify({
                        'error': 'API key invalide',
                        'message': 'La clé API fournie est invalide ou révoquée'
                    }), 401
                
                request.api_key_data = api_key_data
            
            # Vérifier si admin
            if not request.api_key_data.get('is_admin'):
                return jsonify({
                    'error': 'Accès refusé',
                    'message': 'Cette ressource nécessite des privilèges administrateur'
                }), 403
            
            return f(*args, **kwargs)
        
        return decorated_function




