"""
Service de génération de PDF
"""
import os
import pdfkit
import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from backend.config.settings import STATIC_DIR, IS_CLOUD_ENV
from backend.services.cloud_storage import StorageService
import logging

logger = logging.getLogger(__name__)


class PDFService:
    """Service de génération de PDF"""

    def __init__(self):
        self.storage = StorageService()
        if not IS_CLOUD_ENV:
            # Correction temporaire du bug STATIC_DIR pour local
            from pathlib import Path
            self.static_dir = Path(__file__).resolve().parent.parent.parent / "static"
    
    def fix_encoding(self, text: str) -> str:
        """Corrige les problèmes d'encodage (double encodage UTF-8, caractères spéciaux, etc.)"""
        if isinstance(text, bytes):
            text = text.decode('utf-8', errors='replace')
        
        # Normaliser les caractères spéciaux qui posent problème à wkhtmltopdf
        # Remplacer les apostrophes/guillemets typographiques par des versions simples
        # IMPORTANT: On utilise UTF-8 partout, pas latin-1
        replacements = {
            'œ': 'oe',  # Ligature œ
            'Œ': 'OE',  # Ligature Œ majuscule
            'æ': 'ae',  # Ligature æ
            'Æ': 'AE',  # Ligature Æ majuscule
            ''': "'",  # Apostrophe courbe droite
            ''': "'",  # Apostrophe courbe gauche
            '"': '"',   # Guillemet droit
            '"': '"',   # Guillemet gauche
            '…': '...', # Points de suspension
            '–': '-',   # Tiret cadratin
            '—': '-',   # Tiret cadratin long
            'â€™': "'", # Apostrophe mal encodée
            'â€œ': '"', # Guillemet mal encodé
            'â€': '"',  # Guillemet fermant mal encodé
        }
        
        # Appliquer les remplacements de caractères spéciaux
        for old, new in replacements.items():
            text = text.replace(old, new)
        
        # Normalisation agressive : remplacer TOUS les caractères non-latin-1 restants
        # en parcourant caractère par caractère pour être sûr
        import unicodedata
        normalized_text = ""
        for char in text:
            try:
                # Essayer d'encoder en latin-1 avec errors='strict' pour détecter les problèmes
                char.encode('latin-1', errors='strict')
                normalized_text += char
            except UnicodeEncodeError:
                # Caractère non-latin-1, le remplacer
                if char == 'œ':
                    normalized_text += 'oe'
                elif char == 'Œ':
                    normalized_text += 'OE'
                elif char == 'æ':
                    normalized_text += 'ae'
                elif char == 'Æ':
                    normalized_text += 'AE'
                else:
                    # Utiliser la décomposition Unicode et prendre le caractère de base
                    try:
                        decomposed = unicodedata.normalize('NFD', char)
                        # Prendre seulement les caractères ASCII
                        ascii_char = ''.join(c for c in decomposed if ord(c) < 128)
                        normalized_text += ascii_char if ascii_char else '?'
                    except:
                        normalized_text += '?'
        text = normalized_text
        
        # Détecter et corriger le double encodage UTF-8
        # Patterns de double encodage à détecter:
        # - Ã©, Ã¨, Ã§, Ã, etc. (é, è, ç, à mal encodés)
        # - Ã‰, Ãˆ, etc. (majuscules accentuées mal encodées)
        try:
            double_encoding_patterns = [
                'Ã©', 'Ã¨', 'Ã§', 'Ã ', 'Ãª', 'Ã´', 'Ã¹', 'Ã¯', 'Ã»',
                'Ã‰', 'Ãˆ', 'Ã‡', 'Ã€', 'Ã'  # Majuscules accentuées
            ]
            
            has_double_encoding = any(pattern in text for pattern in double_encoding_patterns)
            
            if has_double_encoding:
                # Correction du double encodage SANS utiliser latin-1
                # Le double encodage se produit quand UTF-8 est interprété comme latin-1 puis ré-encodé en UTF-8
                # On corrige en remplaçant directement les patterns par les caractères corrects
                try:
                    # Mapping des patterns de double encodage vers les caractères corrects
                    double_encoding_fixes = {
                        'Ã©': 'é', 'Ã¨': 'è', 'Ã§': 'ç', 'Ã ': 'à', 'Ãª': 'ê', 
                        'Ã´': 'ô', 'Ã¹': 'ù', 'Ã¯': 'ï', 'Ã»': 'û',
                        'Ã‰': 'É', 'Ãˆ': 'È', 'Ã‡': 'Ç', 'Ã€': 'À', 'Ã': 'Â'
                    }
                    
                    # Remplacer les patterns de double encodage
                    corrected = text
                    for pattern, correct_char in double_encoding_fixes.items():
                        corrected = corrected.replace(pattern, correct_char)
                    
                    # Vérifier que la correction a amélioré le texte
                    if not any(pattern in corrected for pattern in double_encoding_patterns):
                        logger.info("Correction d'encodage appliquée (double encodage détecté et corrigé)")
                        text = corrected
                except Exception as e:
                    # Si ça échoue, on garde le texte original
                    logger.debug(f"Impossible de corriger le double encodage: {e}")
            
            return text
        except Exception as e:
            logger.warning(f"Erreur lors de la correction d'encodage: {e}")
            return text
    
    def remove_highlight_tags(self, html: str) -> str:
        """Supprime les balises mark/highlight du HTML tout en gardant le contenu"""
        # Supprimer récursivement toutes les balises mark (y compris imbriquées)
        max_iterations = 10  # Éviter les boucles infinies
        iteration = 0
        while '<mark' in html and iteration < max_iterations:
            html = re.sub(r'<mark[^>]*>(.*?)</mark>', r'\1', html, flags=re.DOTALL)
            iteration += 1
        # Supprimer les classes hlterms restantes
        html = re.sub(r'class="hlterms"', '', html)
        return html
    
    def generate_pdf(self, html_content: str, url: str, job_id: str) -> tuple:
        """
        Générer un PDF à partir du contenu HTML
        
        Args:
            html_content: Contenu HTML de l'article
            url: URL ou nom de l'article (pour le nom de fichier)
            job_id: ID du job pour les logs
            
        Returns:
            tuple: (pdf_path, html_path)
        """
        try:
            # CORRIGER L'ENCODAGE EN PREMIER - avant tout traitement
            try:
                html_content = self.fix_encoding(html_content)
            except Exception as encoding_error:
                # Si fix_encoding échoue, utiliser une méthode de secours
                # Protection du logging pour éviter les erreurs d'encodage
                try:
                    error_msg = str(encoding_error).encode('utf-8', errors='replace').decode('utf-8')
                    logger.warning(f"[{job_id}] Erreur dans fix_encoding, utilisation méthode de secours: {error_msg}")
                except:
                    logger.warning(f"[{job_id}] Erreur dans fix_encoding, utilisation méthode de secours (détails non disponibles)")
                # Méthode de secours : remplacer les caractères problématiques
                import unicodedata
                safe_text = ""
                for char in html_content:
                    # Remplacer les ligatures et caractères spéciaux
                    if char == 'œ':
                        safe_text += 'oe'
                    elif char == 'Œ':
                        safe_text += 'OE'
                    elif char == 'æ':
                        safe_text += 'ae'
                    elif char == 'Æ':
                        safe_text += 'AE'
                    elif ord(char) > 127:
                        # Pour les autres caractères non-ASCII, utiliser la décomposition Unicode
                        try:
                            decomposed = unicodedata.normalize('NFD', char)
                            ascii_char = ''.join(c for c in decomposed if ord(c) < 128)
                            safe_text += ascii_char if ascii_char else '?'
                        except:
                            safe_text += '?'
                    else:
                        safe_text += char
                html_content = safe_text
            
            # Enlever les balises de surlignement
            html_content = self.remove_highlight_tags(html_content)
            
            # S'assurer que le contenu est en UTF-8 (string)
            if isinstance(html_content, bytes):
                html_content = html_content.decode('utf-8', errors='replace')
            
            # S'assurer que html_content est bien normalisé (double vérification)
            # Normaliser à nouveau pour être absolument sûr
            import unicodedata
            safe_html_content = ""
            for char in html_content:
                try:
                    char.encode('latin-1', errors='strict')
                    safe_html_content += char
                except UnicodeEncodeError:
                    if char == 'œ':
                        safe_html_content += 'oe'
                    elif char == 'Œ':
                        safe_html_content += 'OE'
                    elif char == 'æ':
                        safe_html_content += 'ae'
                    elif char == 'Æ':
                        safe_html_content += 'AE'
                    else:
                        try:
                            decomposed = unicodedata.normalize('NFD', char)
                            ascii_char = ''.join(c for c in decomposed if ord(c) < 128)
                            safe_html_content += ascii_char if ascii_char else '?'
                        except:
                            safe_html_content += '?'
            html_content = safe_html_content
            
            # Wrapper le HTML dans un document complet avec encodage UTF-8 explicite
            # C'est essentiel pour que wkhtmltopdf gère correctement les accents
            full_html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
    <style>
        body {{
            font-family: Arial, "DejaVu Sans", "Liberation Sans", sans-serif;
            font-size: 12pt;
            line-height: 1.6;
            color: #333;
        }}
        h1, h2, h3, h4, h5, h6 {{
            font-family: Arial, "DejaVu Sans", "Liberation Sans", sans-serif;
            color: #000;
        }}
        p, div, span {{
            font-family: Arial, "DejaVu Sans", "Liberation Sans", sans-serif;
        }}
    </style>
</head>
<body>
{html_content}
</body>
</html>"""
            
            # Générer le nom de fichier (sans caractères spéciaux)
            raw_name = (lambda u: urlparse(u).path.split('/')[-1][:90])(url)
            # Normaliser le nom de fichier pour éviter les problèmes d'encodage
            safe_name = ""
            for char in raw_name:
                try:
                    char.encode('latin-1', errors='strict')
                    safe_name += char
                except UnicodeEncodeError:
                    if char == 'œ':
                        safe_name += 'oe'
                    elif char == 'Œ':
                        safe_name += 'OE'
                    elif char == 'æ':
                        safe_name += 'ae'
                    elif char == 'Æ':
                        safe_name += 'AE'
                    else:
                        safe_name += '_'
            name = safe_name
            
            # Options PDF avec encodage UTF-8 explicite
            pdf_options = {
                'page-size': 'A4',
                'margin-top': '5mm',
                'margin-right': '5mm',
                'margin-bottom': '5mm',
                'margin-left': '5mm',
                'encoding': 'UTF-8',
                'enable-local-file-access': '',
                'no-images': '',
                'quiet': '',
                'disable-smart-shrinking': '',
                'custom-header': [
                    ('Accept-Encoding', 'gzip'),
                    ('Content-Type', 'text/html; charset=UTF-8')
                ],
                'no-pdf-compression': '',
                'dpi': 300,
                'minimum-font-size': '10'
            }
            
            # Créer un fichier HTML temporaire pour éviter les problèmes d'encodage
            # C'est plus fiable que de passer directement la string à pdfkit
            # Utiliser UTF-8 avec BOM pour garantir la détection de l'encodage
            tmp_html_path = None
            try:
                # Créer le fichier avec UTF-8 BOM (Byte Order Mark) pour une meilleure compatibilité
                tmp_html_path = tempfile.mktemp(suffix='.html', prefix='pdf_gen_')
                with open(tmp_html_path, 'wb') as tmp_file:
                    # Écrire le BOM UTF-8 puis le contenu
                    tmp_file.write('\ufeff'.encode('utf-8'))  # UTF-8 BOM
                    tmp_file.write(full_html.encode('utf-8'))
                
                # Générer le PDF à partir du fichier HTML temporaire
                # Cela garantit un encodage UTF-8 correct
                # Protection supplémentaire : s'assurer que le chemin du fichier est safe
                try:
                    pdf_data = pdfkit.from_file(tmp_html_path, False, options=pdf_options)
                except Exception as pdf_error:
                    # Si l'erreur contient des caractères non-latin-1, les remplacer
                    error_msg = str(pdf_error)
                    # Normaliser le message d'erreur pour éviter les problèmes d'encodage
                    safe_error_msg = ""
                    for char in error_msg:
                        try:
                            char.encode('latin-1', errors='strict')
                            safe_error_msg += char
                        except UnicodeEncodeError:
                            safe_error_msg += '?'
                    # Re-lever l'exception avec un message sécurisé
                    raise Exception(safe_error_msg) from pdf_error
            finally:
                # Nettoyer le fichier temporaire
                if tmp_html_path:
                    try:
                        os.unlink(tmp_html_path)
                    except:
                        pass

            # Sauvegarder les fichiers via StorageService
            pdf_local_path, pdf_url = self.storage.save_file(pdf_data, f"{name}.pdf")
            # Sauvegarder le HTML complet (avec wrapper) pour référence
            # StorageService accepte les strings pour les fichiers HTML
            html_local_path, html_url = self.storage.save_file(full_html, f"{name}.html")

            logger.info(f"[{job_id}] PDF généré: {pdf_url}")
            logger.info(f"[{job_id}] HTML généré: {html_url}")

            return pdf_url, html_url
        
        except Exception as e:
            # Gestion sécurisée de l'erreur pour éviter les problèmes d'encodage dans le logging
            # IMPORTANT: Normaliser le message d'erreur AVANT de le logger
            try:
                error_str = str(e)
                # Normaliser le message d'erreur caractère par caractère pour éviter latin-1
                import unicodedata
                safe_error_str = ""
                for char in error_str:
                    try:
                        char.encode('latin-1', errors='strict')
                        safe_error_str += char
                    except UnicodeEncodeError:
                        if char == 'œ':
                            safe_error_str += 'oe'
                        elif char == 'Œ':
                            safe_error_str += 'OE'
                        elif char == 'æ':
                            safe_error_str += 'ae'
                        elif char == 'Æ':
                            safe_error_str += 'AE'
                        else:
                            try:
                                decomposed = unicodedata.normalize('NFD', char)
                                ascii_char = ''.join(c for c in decomposed if ord(c) < 128)
                                safe_error_str += ascii_char if ascii_char else '?'
                            except:
                                safe_error_str += '?'
                
                # Maintenant on peut logger en sécurité
                logger.error(f"[{job_id}] Erreur génération PDF: {safe_error_str}")
            except Exception as log_error:
                # Si même le logging échoue, utiliser un message générique
                logger.error(f"[{job_id}] Erreur génération PDF (détails non disponibles: {type(log_error).__name__})")
            
            # Re-lever l'exception avec un message normalisé
            try:
                error_str = str(e)
                safe_error_str = ""
                for char in error_str:
                    try:
                        char.encode('latin-1', errors='strict')
                        safe_error_str += char
                    except UnicodeEncodeError:
                        safe_error_str += '?'
                raise Exception(safe_error_str) from e
            except:
                # Si tout échoue, lever une exception générique
                raise Exception("Erreur génération PDF (détails non disponibles)") from e

