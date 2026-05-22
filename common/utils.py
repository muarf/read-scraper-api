import os
from random import choice
import logging

logger = logging.getLogger(__name__)

class NoResultException(Exception):
    """Exception pour indiquer qu'aucun résultat n'a été trouvé (ne doit pas être retry)"""
    pass

class KeywordsNeededException(Exception):
    """Exception pour indiquer que des mots-clés sont nécessaires pour continuer"""
    pass

def generate_id(length):
    # Utiliser seulement des caractères alphanumériques et -_
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
    user_id = ''.join(choice(alphabet) for _ in range(length))
    return user_id

def send_message_to_client(message, session_id):
    # Gestion sécurisée des caractères Unicode pour l'affichage
    try:
        safe_message = str(message).encode('utf-8', errors='replace').decode('utf-8')
    except UnicodeEncodeError:
        safe_message = str(message).encode('ascii', errors='replace').decode('ascii')
    
    logger.info(f"[{session_id}] {safe_message}")

def file_exists(name):
    import sys
    from pathlib import Path
    
    # Calculer le chemin absolu depuis le répertoire racine du projet
    project_root = Path(__file__).resolve().parent.parent
    static_dir = project_root / 'static'
    file_path = static_dir / f'{name}.html'
    return file_path.exists()

def sanitize_filename(filename):
    import re
    return re.sub(r'[^a-zA-Z0-9_-]', '-', filename)

def fix_encoding(text: str) -> str:
    """Corrige les problèmes d'encodage (double encodage UTF-8, caractères spéciaux, etc.)"""
    if isinstance(text, bytes):
        text = text.decode('utf-8', errors='replace')
    
    replacements = {
        'œ': 'oe', 'Œ': 'OE', 'æ': 'ae', 'Æ': 'AE',
        ''': "'", ''': "'", '"': '"', '"': '"',
        '…': '...', '–': '-', '—': '-',
        'â€™': "'", 'â€œ': '"', 'â€': '"',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    
    import unicodedata
    normalized_text = ""
    for char in text:
        try:
            char.encode('latin-1', errors='strict')
            normalized_text += char
        except UnicodeEncodeError:
            if char == 'œ': normalized_text += 'oe'
            elif char == 'Œ': normalized_text += 'OE'
            elif char == 'æ': normalized_text += 'ae'
            elif char == 'Æ': normalized_text += 'AE'
            else:
                try:
                    decomposed = unicodedata.normalize('NFD', char)
                    ascii_char = ''.join(c for c in decomposed if ord(c) < 128)
                    normalized_text += ascii_char if ascii_char else '?'
                except:
                    normalized_text += '?'
    text = normalized_text
    
    try:
        double_encoding_patterns = [
            'Ã©', 'Ã¨', 'Ã§', 'Ã ', 'Ãª', 'Ã´', 'Ã¹', 'Ã¯', 'Ã»',
            'Ã‰', 'Ãˆ', 'Ã‡', 'Ã€', 'Ã'
        ]
        has_double_encoding = any(pattern in text for pattern in double_encoding_patterns)
        
        if has_double_encoding:
            try:
                double_encoding_fixes = {
                    'Ã©': 'é', 'Ã¨': 'è', 'Ã§': 'ç', 'Ã ': 'à', 'Ãª': 'ê', 
                    'Ã´': 'ô', 'Ã¹': 'ù', 'Ã¯': 'ï', 'Ã»': 'û',
                    'Ã‰': 'É', 'Ãˆ': 'È', 'Ã‡': 'Ç', 'Ã€': 'À', 'Ã': 'Â'
                }
                corrected = text
                for pattern, correct_char in double_encoding_fixes.items():
                    corrected = corrected.replace(pattern, correct_char)
                
                if not any(pattern in corrected for pattern in double_encoding_patterns):
                    logger.info("Correction d'encodage appliquée (double encodage détecté et corrigé)")
                    text = corrected
            except Exception as e:
                logger.debug(f"Impossible de corriger le double encodage: {e}")
        return text
    except Exception as e:
        logger.warning(f"Erreur lors de la correction d'encodage: {e}")
        return text

def remove_highlight_tags(html: str) -> str:
    """Supprime les balises mark/highlight du HTML tout en gardant le contenu"""
    import re
    max_iterations = 10
    iteration = 0
    while '<mark' in html and iteration < max_iterations:
        html = re.sub(r'<mark[^>]*>(.*?)</mark>', r'\1', html, flags=re.DOTALL)
        iteration += 1
    html = re.sub(r'class="hlterms"', '', html)
    return html

def resolve_pdf_path(pdf_path_str: str) -> str:
    """Résout le chemin d'un PDF à partir de son URL/chemin relatif."""
    from pathlib import Path
    project_root = Path(__file__).resolve().parent.parent
    static_dir = project_root / 'backend' / 'static' # Utilisé par l'API Backend
    
    # Check if the file exists in the general static dir instead
    if pdf_path_str.startswith('/static/'):
        filename = pdf_path_str.replace('/static/', '')
    else:
        filename = pdf_path_str
        
    return str(static_dir / filename)