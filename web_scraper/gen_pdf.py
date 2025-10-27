import pdfkit
from urllib.parse import urlparse
import os
import re

from common.utils import send_message_to_client

def remove_highlight_tags(html):
    """Supprime les balises mark/highlight du HTML"""
    # Enlever toutes les balises <mark> en gardant le contenu
    html = re.sub(r'</?mark[^>]*>', '', html)
    # Enlever les classes hlterms
    html = re.sub(r'class="hlterms"', '', html)
    return html

def generate_pdf(socketio, app, html,url,session_id):
    send_message_to_client(socketio, app, 'on génére le PDF',session_id)
    
    # Enlever les balises de surlignement du HTML
    html = remove_highlight_tags(html)
    
    name = (lambda u: urlparse(u).path.split('/')[-1][:90])(url)
    send_message_to_client(socketio, app, name,session_id)
    # Options PDF avec spécification de la taille de police
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
        'minimum-font-size': '10'  # Spécifiez la taille de police minimale souhaitée
    }

    # Générer le PDF
    pdf = pdfkit.from_string(html, False, options=pdf_options)
    pdf_path = f'static/{name}.pdf'
    html_path = f'static/{name}.html'
    with open(pdf_path, 'wb') as pdf_file:
        pdf_file.write(pdf)
        send_message_to_client(socketio, app, f'pdf généré  : {name}.pdf',session_id)
    with open(html_path, 'w') as html_file:
        html_file.write(html)
        send_message_to_client(socketio, app, f'html genéré  : {name}.html', session_id)
    return pdf_path, html_path
