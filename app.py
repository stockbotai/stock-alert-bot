# app.py
import os
import json
import logging
from datetime import datetime
from threading import Thread

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# OpenAI
import openai

# market/data & ML
import yfinance as yf
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

# scheduling & DB
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, MetaData, Table
from sqlalchemy.orm import sessionmaker

import requests

# ---------- Config ----------
STOCKS = os.environ.get("STOCK_LIST", "RELIANCE.NS,TCS.NS,SBIN.NS,HDFCBANK.NS,INFY.NS").split(",")
SCAN_INTERVAL_MIN = int(os.environ.get("SCAN_INTERVAL_MIN", "5"))
FALL_THRESHOLD = float(os.environ.get("FALL_THRESHOLD_PERCENT", "-1.5"))
RISE_THRESHOLD = float(os.environ.get("RISE_THRESHOLD_PERCENT", "2.0"))
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")  # set on Render
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT = os.environ.get("TELEGRAM_CHAT_ID")  # numeric chat id
DATABASE_URL = os.environ.get("DATABASE_URL")  # optional: postgres://... if not set use sqlite file
PORT = int(os.environ.get("PORT", 10000))
# ----------------------------

# logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("genie")

app = Flask(__name__, static_folder='.')
CORS(app)

# --- DB setup (SQLAlchemy) ---
if DATABASE_URL:
    engine = create_engine(DATABASE_URL, echo=False, future=True)
else:
    engine = create_engine(f"sqlite:///alerts.db", echo=False, connect_args={"check_same_thread": False})

metadata = MetaData()

alerts_table = Table(
    "alerts", metadata,
    Column("id", Integer, primary_key=True),
    Column("symbol", String(64)),
    Column("price", Float),
    Column("change_pct", Float),
    Column("ai_prediction", String(128)),
    Column("alert_type", String(64)),
    Column("created_at", DateTime),
)

metadata.create_all(engine)
Session = sessionmaker(bind=engine)

def save_alert_db(symbol, price, change_pct, ai_prediction, alert_type):
    session = Session()
    session.execute(alerts_table.insert().values(
        symbol=symbol, price=price, change_pct=change_pct,
        ai_prediction=ai_prediction, alert_type=alert_type, created_at=datetime.utcnow()
    ))
    session.commit()
    session.close()

def get_alerts_db(limit=50):
    session = Session()
    res = session.execute(alerts_table.select().order_by(alerts_table.c.id.desc()).limit(limit)).all()
    session.close()
    out = []
    for r in res:
        out.append({
            "symbol": r.symbol,
            "price": float(r.price) if r.price is not None else None,
            "change_pct": float(r.change_pct) if r.change_pct is not None else None,
            "ai_prediction": r.ai_prediction,
            "alert_type": r.alert_type,
            "created_at": r.created_at.isoformat() if r.created_at else None
        })
    return out

# --- OpenAI setup ---
if OPENAI_KEY:
    openai.api_key = OPENAI_KEY

def ai_answer(question):
    if not OPENAI_KEY:
        # fallback
        q = question.lower()
        if "top" in q and "gainer" in q: return "Top gainers example: RELIANCE, TCS..."
        if "nifty" in q: return "Nifty looks mixed today. Use Run Scan for live data."
        return "I can run live scans and report alerts. Try 'Run Scan' or ask for a specific symbol."
    try:
        # Use ChatCompletion if available, else Completion
        # Using a compatible endpoint
        resp = openai.ChatCompletion.create(
            model=os.environ.get("OPENAI_MODEL","gpt-4o-mini"),
            messages=[{"role":"system","content":"You are a concise stock assistant."},
                      {"role":"user","content": question}],
            max_tokens=300,
            temperature=0.2
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.exception("OpenAI call failed")
        return f"AI error: {str(e)}"

# --- market functions ---
def fetch_stock_info(symbol):
    try:
        t = yf.Ticker(symbol)
        hist = t.history(period="1d", interval="5m")
        if hist is None or len(hist) == 0:
            return None
        open_price = hist["Open"].iloc[0]
        last_price = hist["Close"].iloc[-1]
        change_pct = (last_price - open_price) / open_price * 100
        volume = int(hist["Volume"].sum()) if "Volume" in hist.columns else 0
        return {"symbol": symbol, "price": float(last_price), "change_pct": round(change_pct,2), "volume": volume}
    except Exception as e:
        logger.exception("fetch_stock_info error")
        return None

def predict_trend(symbol):
    try:
        data = yf.download(symbol, period="5d", interval="30m", progress=False)
        if data is None or len(data) < 6: return "No Data"
        data["returns"] = data["Close"].pct_change()
        data["volume_change"] = data["Volume"].pct_change().fillna(0)
        data = data.dropna()
        X = data[["returns","volume_change"]].values[:-1]
        y = np.sign(data["returns"].shift(-1).dropna().values)
        if len(X) < 5: return "No Data"
        model = LinearRegression()
        model.fit(X, y[:len(X)])
        pred = model.predict([X[-1]])[0]
        if pred > 0: return "Uptrend Expected"
        if pred < 0: return "Possible Downtrend"
        return "Neutral"
    except Exception as e:
        logger.exception("predict error")
        return "Error"

def send_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT, "text": msg}
        r = requests.post(url, data=payload, timeout=10)
        return r.ok
    except Exception as e:
        logger.exception("telegram send error")
        return False

def scan_and_save():
    logger.info("Starting market scan for %d symbols", len(STOCKS))
    for s in STOCKS:
        info = fetch_stock_info(s)
        if not info: continue
        ai = predict_trend(s)
        alert_type = None
        if info["change_pct"] <= float(FALL_THRESHOLD):
            alert_type = "Falling"
        elif info["change_pct"] >= float(RISE_THRESHOLD):
            alert_type = "Rising"
        if ai == "Possible Downtrend" and alert_type is None:
            alert_type = "AI-down"
        if alert_type:
            save_alert_db(s, info["price"], info["change_pct"], ai, alert_type)
            text = f"ALERT {s} {alert_type} {info['change_pct']}% price {info['price']}"
            logger.info(text)
            try:
                send_telegram(text)
            except:
                pass

# scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(scan_and_save, 'interval', minutes=SCAN_INTERVAL_MIN, id='market-scan', replace_existing=True)
scheduler.start()

# --- Flask routes ---
@app.route("/api/genie", methods=["POST"])
def api_genie():
    data = request.get_json() or {}
    q = data.get("question","").strip()
    if not q:
        return jsonify({"error":"empty question"}), 400
    # async: answer via AI but keep it sync for now
    ans = ai_answer(q)
    # include recent alerts html for UI
    alerts = get_alerts_db(limit=6)
    html = ""
    for a in alerts:
        html += f"<div class='card'><strong>{a['symbol']}</strong><div class='small'>{a['alert_type']} · {a['change_pct']}% · {a['created_at']}</div></div>"
    return jsonify({"answer": ans, "alerts_html": html})

@app.route("/trigger-scan", methods=["POST","GET"])
def api_trigger_scan():
    Thread(target=scan_and_save).start()
    return jsonify({"status":"started"})

@app.route("/api/alerts")
def api_alerts():
    limit = int(request.args.get("limit",50))
    return jsonify(get_alerts_db(limit=limit))

@app.route("/api/stocks")
def api_stocks():
    out = []
    for s in STOCKS:
        info = fetch_stock_info(s)
        if info:
            info["ai_prediction"] = predict_trend(s)
            out.append(info)
    out = sorted(out, key=lambda x: x.get("volume",0), reverse=True)
    return jsonify(out)

@app.route("/")
def index():
    return send_from_directory(".", "index.html")

# teardown
import atexit
atexit.register(lambda: scheduler.shutdown(wait=False))

if __name__ == "__main__":
    logger.info("Starting app on port %s", PORT)
    app.run(host="0.0.0.0", port=PORT)
