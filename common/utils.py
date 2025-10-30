#utils.py
from flask_socketio import SocketIO
from flask import jsonify, make_response, render_template
import os
from random import choice

def generate_id(length):
    # Utiliser seulement des caractères alphanumériques et -_
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
    user_id = ''.join(choice(alphabet) for _ in range(length))
    return user_id
def send_message_to_client(socketio, app, message, session_id):
    # Gestion sécurisée des caractères Unicode pour l'affichage
    safe_message = str(message).encode('utf-8', errors='replace').decode('utf-8')
    print(safe_message)
    # Gérer le cas où socketio est None (mode API sans WebSocket)
    if socketio is not None:
        event_name = f'server_message_{session_id}'
        socketio.emit(event_name, {'message': safe_message})
        socketio.sleep(0)
def file_exists(name):
    import sys
    from pathlib import Path
    
    # Calculer le chemin absolu depuis le répertoire racine du projet
    project_root = Path(__file__).resolve().parent.parent
    static_dir = project_root / 'static'
    file_path = static_dir / f'{name}.html'
    return file_path.exists()
def set_user_cookies():
    user_id = generate_id(10)
    response = make_response(render_template('index.html'))  # Créer un objet de réponse Flask
    response.set_cookie("user_id", user_id, samesite=None, path="/")  # Définir le cookie avec l'identifiant utilisateur
    return user_id, response