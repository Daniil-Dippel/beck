from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import requests
import re
import html
import os
import openai

# --- Flask setup ---
app = Flask(__name__)
# Разрешаем запросы только с указанных фронтенд-доменов
CORS(app, resources={r"/api/*": {"origins": [
    "https://caito-muit.github.io",
    "https://daniildippel.github.io",
    "http://localhost:5173",
    "http://127.0.0.1:5501",  # для локальной разработки
    "http://127.0.0.1:5000",
    "http://127.0.0.1:5500"   # если фронтенд тоже на этом порту
]}})
# Ограничение скорости и по IP
limiter = Limiter(app=app, key_func=get_remote_address, default_limits=["100 per day", "10 per minute"])

# --- MockAPI endpoints ---
CATALOG_URL = "https://6859802a138a18086dfea5ea.mockapi.io/kashchei777/catalog"
LOG_URL     = "https://6859802a138a18086dfea5ea.mockapi.io/kashchei777/log"

# --- OpenAI setup ---
openai.api_key = os.getenv("OPENAI_API_KEY")  # Задайте переменную окружения OPENAI_API_KEY
MODEL_NAME = "gpt-3.5-turbo"
ASSISTANT_CONTEXT = (
    "Ты — Фелис, дружелюбный ассистент компании CAITO M.U.I.T. "
    "Ты говоришь на русском, профессионально и понятно."
)

# --- Validation & sanitization ---
def sanitize(text: str) -> str:
    return html.escape(text.strip())

def is_valid_email(email: str) -> bool:
    return re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", email)

def is_valid_phone(phone: str) -> bool:
    return re.match(r"^\+?\d{9,15}$", phone)

# --- Proxy-only GET catalog ---
@app.route('/api/catalog', methods=['GET'])
def get_catalog():
    try:
        resp = requests.get(CATALOG_URL)
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        return jsonify({"error": f"Не удалось загрузить каталог: {e}"}), 500

# --- Proxy-only GET all requests ---
@app.route('/api/requests', methods=['GET'])
def list_requests():
    try:
        resp = requests.get(LOG_URL)
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        return jsonify({"error": f"Не удалось загрузить список заявок: {e}"}), 500

# --- Receive and forward new request ---
@app.route('/api/request', methods=['POST'])
@limiter.limit("10 per minute")
def receive_request():
    data = request.json or {}
    name = sanitize(data.get('name', ''))
    phone = sanitize(data.get('phone', ''))
    email = sanitize(data.get('email', ''))
    message = sanitize(data.get('message', ''))

    if not name or not phone:
        return jsonify({"status": "error", "message": "Имя и телефон обязательны"}), 400
    if email and not is_valid_email(email):
        return jsonify({"status": "error", "message": "Некорректный email"}), 400
    if not is_valid_phone(phone):
        return jsonify({"status": "error", "message": "Некорректный номер телефона"}), 400

    payload = {"name": name, "phone": phone, "email": email, "message": message}
    try:
        resp = requests.post(LOG_URL, json=payload)
        if resp.status_code in (200, 201):
            return jsonify({"status": "success", "message": "Заявка успешно отправлена"}), resp.status_code
        return jsonify({"status": "error", "message": "Ошибка MockAPI"}), resp.status_code
    except Exception as e:
        return jsonify({"status": "error", "message": f"Ошибка сервера: {e}"}), 500

# --- Chat with OpenAI GPT-3.5 ---
@app.route('/api/chat', methods=['POST'])
@limiter.limit("20 per minute")
def chat():
    data = request.json or {}
    messages = data.get('messages', [])
    if not isinstance(messages, list) or not messages:
        return jsonify({"error": "Нужен список сообщений"}), 400

    history = [{"role": "system", "content": ASSISTANT_CONTEXT}]
    for msg in messages:
        role = msg.get('role')
        content = sanitize(msg.get('content', ''))
        if role in ('user', 'assistant') and content:
            history.append({"role": role, "content": content})

    try:
        resp = openai.ChatCompletion.create(
            model=MODEL_NAME,
            messages=history,
            temperature=0.7,
            max_tokens=512
        )
        reply = resp.choices[0].message.content.strip()
        return jsonify({"message": reply})
    except Exception as e:
        return jsonify({"error": f"OpenAI API error: {e}"}), 500

# --- Блокировка всех прочих методов ---
@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({"error": "Метод запрещен"}), 405

# --- Запуск приложения ---
if __name__ == '__main__':
    app.run(debug=True, port=5000)
