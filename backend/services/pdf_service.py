"""
Service de génération de PDF
"""
import os
import re
import tempfile
import subprocess
import shutil
from pathlib import Path
from urllib.parse import urlparse
from backend.config.settings import STATIC_DIR, IS_CLOUD_ENV
import logging

logger = logging.getLogger(__name__)


class PDFService:
    """Service de génération de PDF à partir de HTML via Chromium headless"""
    
    def __init__(self):
        from backend.config.settings import CHROME_PATH, IS_CLOUD_ENV, STATIC_DIR
        self.chrome_path = CHROME_PATH
        self.is_cloud = IS_CLOUD_ENV
        self.static_dir = STATIC_DIR
        
        if not self.is_cloud and not self.chrome_path:
            logger.warning("CHROME_PATH non défini en environnement local")
        
        # S'assurer que le dossier statique existe
        if self.static_dir:
            self.static_dir.mkdir(parents=True, exist_ok=True)
        else:
            # Fallback si STATIC_DIR n'est pas bien défini
            from pathlib import Path
            self.static_dir = Path(__file__).resolve().parent.parent.parent / "static"
    
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
                html_content = fix_encoding(html_content)
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
            html_content = remove_highlight_tags(html_content)
            
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
            # C'est plus fiable que de passer directement la string
            # Utiliser UTF-8 avec BOM pour garantir la détection de l'encodage
            # Utiliser un répertoire tmp local au projet pour contourner les limitations du Snap Chromium
            local_tmp_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tmp')
            os.makedirs(local_tmp_dir, exist_ok=True)
            
            tmp_html_path = None
            tmp_pdf_path = None
            try:
                # Créer le fichier avec UTF-8 BOM (Byte Order Mark) pour une meilleure compatibilité
                tmp_html_path = tempfile.mktemp(suffix='.html', prefix='pdf_gen_', dir=local_tmp_dir)
                tmp_pdf_path = tempfile.mktemp(suffix='.pdf', prefix='pdf_gen_', dir=local_tmp_dir)
                with open(tmp_html_path, 'wb') as tmp_file:
                    # Écrire le BOM UTF-8 puis le contenu
                    tmp_file.write('\ufeff'.encode('utf-8'))  # UTF-8 BOM
                    tmp_file.write(full_html.encode('utf-8'))
                
                # Générer le PDF à partir du fichier HTML temporaire via Chromium
                # Trouver un binaire valide de Chromium sur le système
                chromium_binaries = ['/snap/bin/chromium', '/usr/bin/chromium-browser', 'chromium-browser', 'chromium', 'google-chrome']
                chromium_bin = None
                for b in chromium_binaries:
                    if b.startswith('/') and os.path.exists(b):
                        chromium_bin = b
                        break
                if not chromium_bin:
                    for b in ['chromium-browser', 'chromium', 'google-chrome']:
                        found = shutil.which(b)
                        if found:
                            chromium_bin = found
                            break
                
                if not chromium_bin:
                    raise Exception("Chromium binary not found on the system for PDF generation")
                
                cmd = [
                    chromium_bin,
                    '--headless',
                    '--disable-gpu',
                    '--no-sandbox',
                    '--print-to-pdf=' + tmp_pdf_path,
                    tmp_html_path
                ]
                logger.info(f"[{job_id}] Running Chromium command: {' '.join(cmd)}")
                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=True)
                
                # Lire le fichier PDF généré
                if not os.path.exists(tmp_pdf_path) or os.path.getsize(tmp_pdf_path) == 0:
                    raise Exception(f"Chromium did not generate PDF file or generated an empty file. Stderr: {result.stderr.decode('utf-8', errors='replace')}")
                
                with open(tmp_pdf_path, 'rb') as pdf_file:
                    pdf_data = pdf_file.read()
                    
                logger.info(f"[{job_id}] Chromium generated PDF successfully ({len(pdf_data)} bytes)")

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
                # Nettoyer les fichiers temporaires
                for p in [tmp_html_path, tmp_pdf_path]:
                    if p:
                        try:
                            os.unlink(p)
                        except:
                            pass

            # Sauvegarder les fichiers localement dans le dossier statique
            pdf_local_path = self.static_dir / f"{name}.pdf"
            with open(pdf_local_path, "wb") as f:
                f.write(pdf_data)
            
            html_local_path = self.static_dir / f"{name}.html"
            with open(html_local_path, "w", encoding="utf-8") as f:
                f.write(full_html)
                
            pdf_url = f"/static/{name}.pdf"
            html_url = f"/static/{name}.html"

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

