import pdfkit
from urllib.parse import urlparse
import os
import re

from common.utils import send_message_to_client

def fix_encoding(text):
    """Corrige les problèmes d'encodage (double encodage UTF-8, caractères spéciaux, etc.)"""
    if isinstance(text, bytes):
        text = text.decode('utf-8', errors='replace')
    
    # Normaliser les caractères spéciaux qui posent problème à wkhtmltopdf
    # IMPORTANT: Les ligatures doivent être remplacées AVANT toute tentative d'encodage latin-1
    replacements = {
        'œ': 'oe',  # Ligature œ (ne peut pas être encodée en latin-1)
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
    
    # Appliquer d'abord les remplacements de caractères spéciaux (surtout les ligatures)
    # Utiliser replace() avec tous les remplacements pour s'assurer qu'ils sont tous appliqués
    for old, new in replacements.items():
        text = text.replace(old, new)  # Remplacer même si old n'est pas dans text (plus sûr)
    
    # Normalisation agressive : remplacer TOUS les caractères non-latin-1
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
    
    # Vérification finale : s'assurer qu'il n'y a plus de caractères non-latin-1
    # Le texte devrait maintenant être compatible latin-1 après la normalisation ci-dessus
    try:
        # Tester si le texte peut être encodé en latin-1
        text.encode('latin-1', errors='strict')
        text_is_latin1_compatible = True
    except UnicodeEncodeError:
        # Cela ne devrait plus arriver après la normalisation
        text_is_latin1_compatible = False
    
    # Détecter et corriger le double encodage UTF-8
    double_encoding_patterns = [
        'Ã©', 'Ã¨', 'Ã§', 'Ã ', 'Ãª', 'Ã´', 'Ã¹', 'Ã¯', 'Ã»',
        'Ã‰', 'Ãˆ', 'Ã‡', 'Ã€', 'Ã'  # Majuscules accentuées
    ]
    
    has_double_encoding = any(pattern in text for pattern in double_encoding_patterns)
    
    if has_double_encoding and text_is_latin1_compatible:
        try:
            corrected = text.encode('latin-1', errors='ignore').decode('utf-8', errors='replace')
            if not any(pattern in corrected for pattern in double_encoding_patterns):
                text = corrected
        except:
            pass
    
    return text

def remove_highlight_tags(html):
    """Supprime les balises mark/highlight du HTML"""
    # Enlever toutes les balises <mark> en gardant le contenu
    html = re.sub(r'</?mark[^>]*>', '', html)
    # Enlever les classes hlterms
    html = re.sub(r'class="hlterms"', '', html)
    return html

def generate_pdf(socketio, app, html,url,session_id):
    send_message_to_client(socketio, app, 'on génére le PDF',session_id)
    
    # CORRIGER L'ENCODAGE EN PREMIER - avant tout traitement
    html = fix_encoding(html)
    
    # Enlever les balises de surlignement du HTML
    html = remove_highlight_tags(html)
    
    # S'assurer que le contenu est en UTF-8 (string)
    if isinstance(html, bytes):
        html = html.decode('utf-8', errors='replace')
    
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
{html}
</body>
</html>"""
    
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
        'minimum-font-size': '10'  # Spécifiez la taille de police minimale souhaitée
    }

    # Créer un fichier HTML temporaire pour éviter les problèmes d'encodage
    # C'est plus fiable que de passer directement la string à pdfkit
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as tmp_html:
        tmp_html.write(full_html)
        tmp_html_path = tmp_html.name
    
    try:
        # Générer le PDF à partir du fichier HTML temporaire
        # Cela garantit un encodage UTF-8 correct
        pdf = pdfkit.from_file(tmp_html_path, False, options=pdf_options)
    finally:
        # Nettoyer le fichier temporaire
        try:
            os.unlink(tmp_html_path)
        except:
            pass
    pdf_path = f'static/{name}.pdf'
    html_path = f'static/{name}.html'
    with open(pdf_path, 'wb') as pdf_file:
        pdf_file.write(pdf)
        send_message_to_client(socketio, app, f'pdf généré  : {name}.pdf',session_id)
    with open(html_path, 'w', encoding='utf-8') as html_file:
        html_file.write(full_html)
        send_message_to_client(socketio, app, f'html genéré  : {name}.html', session_id)
    return pdf_path, html_path
