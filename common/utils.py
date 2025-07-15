#utils.py
from flask_socketio import SocketIO
from flask import jsonify, make_response, render_template
import os
from random import choice

def generate_id(length):
    alphabet = [chr(i) for i in range(33, 126) if i != 92 and i != 96]
    user_id = ''.join(choice(alphabet) for _ in range(length))
    return user_id
def send_message_to_client(socketio, app, message,session_id):
    print(message)
    event_name = f'server_message_{session_id}'
    socketio.emit(event_name, {'message': message})
    socketio.sleep(0)
def file_exists(name):
    file_path = os.path.join('static', f'{name}.html')
    return os.path.exists(file_path)
def set_user_cookies():
    user_id = generate_id(10)
    response = make_response(render_template('index.html'))  # Créer un objet de réponse Flask
    response.set_cookie("user_id", user_id, samesite=None, path="/")  # Définir le cookie avec l'identifiant utilisateur
    return user_id, response