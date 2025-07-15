# server/server.py
import json
import subprocess
import os
import time
import csv
import psutil
import threading
from weasyprint import HTML
import pdfkit
from flask import Flask, render_template, request, jsonify, make_response, g
from flask_socketio import SocketIO
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from web_scraper.chrome_driver_login import login_to_target_site
from web_scraper.chrome_driver_search import search_target_site
from web_scraper.extract_title import extract_title
from web_scraper.download_article import download_article
from web_scraper.gen_pdf import generate_pdf
from common.utils import file_exists, generate_id, set_user_cookies
from flask_cors import CORS
from common.utils import send_message_to_client
from urllib.parse import urlparse
app = Flask(__name__, static_folder='/app/static/', static_url_path='/static')
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
CORS(app, resources={r"/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*", path='/socket.io')
debug = False
@socketio.on('message')
def handle_message(message):
    print('Message reçu du client :', message)
    send_message_to_client(socketio, app, f"URL reçue : {message}")

@socketio.on('connect')
def handle_connect():
    print('Client connecté a socketio')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client déconnecté de socketio')

# Configuration du navigateur
chrome_path = '/usr/bin/google-chrome'
options = webdriver.ChromeOptions()
options.binary_location = chrome_path
if not debug:
    # options.add_argument('--headless')
    # options.add_argument('--window-size=1920x1080')
    options.add_argument('--no-sandbox')
username = 'demo0038'
password = 'PRESSE'
# Fonction pour obtenir le navigateur pour cette requête
global_browser = None
def get_browser(session_id):
    global global_browser
    if global_browser is None:
        global_browser = webdriver.Chrome(options=options)
        send_message_to_client(socketio, app, f"On lance le navigateur ", session_id)
        login_to_target_site(socketio, app, global_browser, username, password, session_id)
    return global_browser


def close_browser(session_id):
    global global_browser    
    # Ferme le navigateur seulement s'il est déjà initialisé
    if global_browser is not None:
        global_browser.quit()
        send_message_to_client(socketio, app, "On ferme le navigateur", session_id)
        global_browser = None  # Réinitialise la variable globale à None

@app.route('/', methods=['GET', 'POST'])
def index():
    session_id, session_id_response = set_user_cookies()
    socketio.emit('session_id', {'session_id': session_id})
    event_name = f'submit_response_{session_id}'
    print("session_id_1", session_id)
    if request.method == 'POST':
        data = request.form
        handle_form_submission(data, session_id, event_name)
        
    return render_template('index.html', title=None)
@socketio.on('submit_form')
def handle_form_submission(data, session_id=None,event_name=None):
    #if not session_id:
    session_id, session_id_response = set_user_cookies()
    print("session_id_2", session_id)
    socketio.emit('session_id', {'session_id': session_id})
    event_name = f'submit_response_{session_id}'

    send_message_to_client(socketio, app, f"on commence", session_id)
    url = data.get('url', '')
    if url:

        send_message_to_client(socketio, app, f"URL reçue : {url}", session_id)
        query, title = extract_title(url)
        send_message_to_client(socketio, app, f"Titre extrait : {title}", session_id)
        query_ = query.replace(" ", "_");
        name = (lambda u: urlparse(u).path.split('/')[-1][:90])(query_)
        send_message_to_client(socketio, app, f"Nom du fichier : {name}.html", session_id)
        if file_exists(name):
            send_message_to_client(socketio, app, f"le fichier existe déjà", session_id)
            html = open(os.path.join('static', f'{name}.html'), 'r').read()
            #print(html);
            link_pdf = os.path.join('static', f'{name}.pdf')
            send_message_to_client(socketio, app, f"on envoie le html et le pdf {link_pdf}", session_id)
            results_data = []
            results_data.append({'pdf_link[0]': link_pdf})
            percentage = '100'
            socketio.emit(event_name, {'article': html, 'title': title, 'pdf_link': link_pdf, 'percentage': percentage})
            response = make_response(render_template('index.html', article=html , results=results_data, title=title, link_pdf=link_pdf, percentage=percentage)) 
            return response
        browser = get_browser(session_id)
        search_result = search_target_site(socketio, app, browser, query, title,session_id)
        if search_result is not None:
            _, results_data = search_result
            if results_data and isinstance(results_data, list) and len(results_data) > 0 and all(isinstance(item, dict) for item in results_data) and 'link' in results_data[0]:
                link = results_data[0]['link']
                percentage = results_data[0]['percentage']
                article = download_article(socketio, app, browser, link, session_id)
                link_pdf = generate_pdf(socketio, app, article, query_, session_id)
                response = make_response(render_template('index.html', article=article, results=results_data, title=title, link_pdf=link_pdf, percentage=percentage))
                
                results_data[0].update({'pdf_link': link_pdf[0]})
                send_message_to_client(socketio, app, f"On télécharge l'article {results_data[0]['logo']} {results_data[0]['title']} {results_data[0]['date']} {results_data[0]['pdf_link']}", session_id)
                socketio.emit(event_name, {'article': article, 'results': results_data, 'title': title, 'pdf_link': link_pdf[0], 'percentage': percentage})
            else:
                # Handle the case where results_data does not have the correct format
                link = None
                article = None
                response = make_response(render_template('index.html', article=article, results=None, title=title))
                send_message_to_client(socketio, app, "Erreur : results_data n'a pas le bon format.", session_id)
        else:
            # Handle the case where search_result is None
            link = None
            article = None
            response = make_response(render_template('index.html', article=article, results=None, title=title))
            send_message_to_client(socketio, app, "Erreur : search_result est None.", session_id)

        send_message_to_client(socketio, app, "on envoie la page à afficher", session_id)
        socketio.emit(event_name, {'termine': True})
        close_browser(session_id)
        global_browser = None
        return response


    return render_template('index.html', title=None)


@app.route('/download', methods=['POST'])
def download():
    session_id = request.namespace.session.session_id
    # Utilise get_browser() pour obtenir le navigateur pour cette requête
    browser = get_browser(session_id)
    data = request.get_json()
    link = data['link']
    logo = data['logo']
    title = data['title']
    date = data['date']

    send_message_to_client(socketio, app,f"On télécharge l'article {logo} {title} {date} {link}", session_id)
    article = download_article(socketio, app, browser, link, session_id)
    return jsonify({'article': str(article)})

@app.route('/close', methods=['GET', 'POST'])
def close_tab_route():
    data = request.form
    tab_id = data.get('tabId', '')

    # Ferme le navigateur lorsqu'une requête POST est reçue
    close_browser()

    # Fais ce que tu as besoin avec l'ID de l'onglet
    print(f"Received close request for tab ID: {tab_id}")

    return jsonify(success=True)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)
