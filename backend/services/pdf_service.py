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
            # Enlever les balises de surlignement
            html_content = self.remove_highlight_tags(html_content)
            
            # Générer le nom de fichier
            name = (lambda u: urlparse(u).path.split('/')[-1][:90])(url)
            
            # Options PDF
            pdf_options = {
                'page-size': 'A4',
                'margin-top': '5mm',
                'margin-right': '5mm',
                'margin-bottom': '5mm',
                'margin-left': '5mm',
                'encoding': 'UTF-8',
                'no-images': '',
                'quiet': '',
                'disable-smart-shrinking': '',
                'custom-header': [
                    ('Accept-Encoding', 'gzip')
                ],
                'no-pdf-compression': '',
                'dpi': 300,
                'minimum-font-size': '10'
            }
            
            # Générer le PDF
            pdf_data = pdfkit.from_string(html_content, False, options=pdf_options)

            # Sauvegarder les fichiers via StorageService
            pdf_local_path, pdf_url = self.storage.save_file(pdf_data, f"{name}.pdf")
            html_local_path, html_url = self.storage.save_file(html_content, f"{name}.html")

            logger.info(f"[{job_id}] PDF généré: {pdf_url}")
            logger.info(f"[{job_id}] HTML généré: {html_url}")

            return pdf_url, html_url
        
        except Exception as e:
            logger.error(f"[{job_id}] Erreur génération PDF: {e}")
            raise

