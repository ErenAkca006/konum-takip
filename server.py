import json
import os
import sqlite3
import smtplib
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "locations.db"
HTML_PATH = BASE_DIR / "konumum.html"

load_dotenv(BASE_DIR / ".env")

app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path="")
CORS(app, resources={r"/api/*": {"origins": "*"}})


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lat REAL NOT NULL,
            lon REAL NOT NULL,
            accuracy REAL,
            timestamp TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()


init_db()


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def send_email(lat, lon, accuracy, timestamp):
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = (os.getenv("SMTP_USER", "") or "").strip()
    smtp_password = (os.getenv("SMTP_PASSWORD", "") or "").strip()
    to_email = (os.getenv("TO_EMAIL", "erenakc69@gmail.com") or "erenakc69@gmail.com").strip()

    placeholder = "PASTE_YOUR_GMAIL_APP_PASSWORD_HERE"
    if not smtp_user or not smtp_password or smtp_password == placeholder or "PASTE_" in smtp_password.upper():
        return {
            "status": "skipped",
            "message": "SMTP credentials are not set. Replace the placeholder in .env with a real Gmail app password to enable automatic email delivery.",
        }

    map_url = f"https://www.google.com/maps?q={lat},{lon}"
    subject = "Kişisel konum takibi"
    body = (
        f"Tarih: {timestamp}\n"
        f"Koordinatlar: {lat:.6f}, {lon:.6f}\n"
        f"Doğruluk: ±{accuracy} m\n"
        f"Harita: {map_url}"
    )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = to_email
    msg.set_content(body)

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(msg)

    return {"status": "sent"}


@app.get("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/api/history")
def history():
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT lat, lon, accuracy, timestamp FROM locations ORDER BY id DESC LIMIT 20"
    ).fetchall()
    conn.close()
    return jsonify([
        {
            "lat": row["lat"],
            "lon": row["lon"],
            "accuracy": row["accuracy"],
            "timestamp": row["timestamp"],
        }
        for row in rows
    ])


@app.post("/api/location")
def receive_location():
    payload = request.get_json(silent=True) or {}
    lat = payload.get("lat")
    lon = payload.get("lon")
    accuracy = payload.get("accuracy")
    timestamp = payload.get("timestamp") or datetime.utcnow().isoformat()

    if lat is None or lon is None:
        return jsonify({"error": "lat and lon are required"}), 400

    conn = get_db_connection()
    conn.execute(
        "INSERT INTO locations (lat, lon, accuracy, timestamp) VALUES (?, ?, ?, ?)",
        (float(lat), float(lon), float(accuracy) if accuracy is not None else None, timestamp),
    )
    conn.commit()
    location_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    conn.close()

    email_result = send_email(float(lat), float(lon), float(accuracy) if accuracy is not None else 0, timestamp)
    return jsonify({
        "status": "ok",
        "id": location_id,
        "email": email_result,
        "timestamp": timestamp,
    })


@app.get("/")
def index():
    return send_file(HTML_PATH, mimetype="text/html")


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
