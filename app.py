from flask import Flask, request, jsonify
from flask_cors import CORS
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from openai import OpenAI
import re
import html
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# --- Flask ---
app = Flask(__name__)

# --- Ограничение CORS (разрешаем только frontend-домен) ---
CORS(app, resources={r"/api/*": {"origins": ["http://localhost:5500", "http://127.0.0.1:5500", "https://ваш-домен.com"]}})

# --- Ограничение по IP (например: 10 запросов в минуту на чат и форму) ---
limiter = Limiter(app=app, key_func=get_remote_address, default_limits=["100 per day", "10 per minute"])

# --- OpenAI ---
client = OpenAI(api_key="sk-proj-ВАШ_КЛЮЧ")

assistant_context = (
    "Ты — Фелис, дружелюбный ассистент компании CAITO M.U.I.T. "
    "Ты говоришь на русском, профессионально и понятно."
)

# --- SQLite и SQLAlchemy ---
engine = create_engine('sqlite:///requests.db', echo=False)
Base = declarative_base()
SessionLocal = sessionmaker(bind=engine)

class RequestForm(Base):
    __tablename__ = "requests"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=False)
    email = Column(String(100))
    message = Column(Text)

Base.metadata.create_all(bind=engine)

# --- Валидация и защита ---
def sanitize(text):
    return html.escape(text.strip())  # Защита от XSS

def is_valid_email(email):
    return re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", email)

def is_valid_phone(phone):
    return re.match(r"^\+?\d{9,15}$", phone)

# --- Чат с OpenAI ---
@app.route('/api/chat', methods=['POST'])
@limiter.limit("10 per minute")
def chat():
    data = request.json
    messages = data.get("messages", [])

    if not messages:
        return jsonify({"response": "..."})

    try:
        chatgpt_messages = [{"role": "system", "content": assistant_context}]
        for msg in messages:
            role = "user" if msg["speaker"] == "user" else "assistant"
            chatgpt_messages.append({"role": role, "content": sanitize(msg["text"])})

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=chatgpt_messages,
            temperature=0.7,
            max_tokens=512,
        )

        reply = response.choices[0].message.content.strip()
        return jsonify({"response": reply})

    except Exception as e:
        return jsonify({"response": f"Ошибка: {e}"}), 500

# --- Приём заявок ---
@app.route('/api/request', methods=['POST'])
@limiter.limit("10 per minute")
def receive_request():
    data = request.json

    name = sanitize(data.get("name", ""))
    phone = sanitize(data.get("phone", ""))
    email = sanitize(data.get("email", ""))
    message = sanitize(data.get("message", ""))

    if not name or not phone:
        return jsonify({"status": "error", "message": "Имя и телефон обязательны"}), 400

    if email and not is_valid_email(email):
        return jsonify({"status": "error", "message": "Некорректный email"}), 400

    if not is_valid_phone(phone):
        return jsonify({"status": "error", "message": "Некорректный номер телефона"}), 400

    try:
        db = SessionLocal()
        new_request = RequestForm(name=name, phone=phone, email=email, message=message)
        db.add(new_request)
        db.commit()
        db.close()
        return jsonify({"status": "success", "message": "Заявка принята!"})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Ошибка сервера: {e}"}), 500

# --- Запуск ---
if __name__ == '__main__':
    app.run(debug=True, port=5000)
