# app.py
import os
import time
import json
from datetime import datetime
from threading import Thread

import yfinance as yf
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from flask import Flask, jsonify, send_from_directory, request
import sqlite3
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__, static_folder='.')

# --- CONFIG ----------
STOCKS = [
    "RELIANCE.NS","TCS.NS","SBIN.NS","HDFCBANK.NS",
    "INFY.NS","LT.NS","BHARTIARTL.NS","ICICIBANK.NS",
    "POWERGRID.NS","ADANIENT.NS"
]
SCAN_INTERVAL_MINUTES = 5
FALL_THRESHOLD_PERCENT = -1.5   # अगर change <= -1.5% तो falling alert
RISE_THRESHOLD_PERCENT = 2.0    # अगर change >= 2% then rise alert
DB_FILE = "alerts.db"
# -----------------------

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        price REAL,
        change_pct REAL,
        ai_prediction TEXT,
        alert_type TEXT,
        created_at TEXT
    )
    """)
    conn.commit()
    conn.close()

def save_alert(symbol, price, change_pct, ai_prediction, alert_type):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    c.execute("""
        INSERT INTO alerts (symbol, price, change_pct, ai_prediction, alert_type, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (symbol, price, change_pct, ai_prediction, alert_type, now))
    conn.commit()
    conn.close()

def get_alerts(limit=200):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, symbol, price, change_pct, ai_prediction, alert_type, created_at FROM alerts ORDER BY id DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    keys = ["id","symbol","price","change_pct","ai_prediction","alert_type","created_at"]
    return [dict(zip(keys, r)) for r in rows]

# Simple AI predictor using last 5 days / 30m or 1h data (linear regression on returns & volume change)
def predict_trend(symbol):
    try:
        # try shorter interval first
        data = yf.download(symbol, period="5d", interval="30m", progress=False)
        if data is None or len(data) < 6:
            return "No Data"
        data["returns"] = data["Close"].pct_change()
        data["volume_change"] = data["Volume"].pct_change().fillna(0)
        data = data.dropna()
        X = data[["returns", "volume_change"]].values[:-1]
        y = np.sign(data["returns"].shift(-1).dropna().values)
        if len(X) < 5:
            return "No Data"
        model = LinearRegression()
        model.fit(X, y[:len(X)])
        pred = model.predict([X[-1]])[0]
        if pred > 0:
            return "📈 Uptrend Expected"
        elif pred < 0:
            return "📉 Possible Downtrend"
        else:
            return "➖ Neutral"
    except Exception as e:
        return "Error"

def fetch_stock_info(symbol):
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="1d", interval="5m")
    if hist is None or len(hist) == 0:
        return None
    open_price = hist["Open"].iloc[0]
    last_price = hist["Close"].iloc[-1]
    change_pct = (last_price - open_price) / open_price * 100
    volume_sum = int(hist["Volume"].sum()) if "Volume" in hist.columns else 0
    return {"symbol": symbol, "price": float(last_price), "change_pct": round(change_pct, 2), "volume": volume_sum}

def scan_and_alert():
    print(f"[{datetime.utcnow().isoformat()}] Running scan for {len(STOCKS)} stocks...")
    for s in STOCKS:
        try:
            info = fetch_stock_info(s)
            if info is None:
                continue
            ai = predict_trend(s)
            # Decide alert
            alert_type = None
            if info["change_pct"] <= FALL_THRESHOLD_PERCENT:
                alert_type = "Falling"
            elif info["change_pct"] >= RISE_THRESHOLD_PERCENT:
                alert_type = "Rising"
            # Also create an alert if AI predicts downtrend
            if ai == "📉 Possible Downtrend" and alert_type is None:
                alert_type = "AI-down"
            if alert_type:
                # Save alert in DB
                save_alert(s, info["price"], info["change_pct"], ai, alert_type)
                print(f"Alert saved: {s} {alert_type} ({info['change_pct']}%)")
        except Exception as e:
            print("Error scanning", s, str(e))

# API routes
@app.route("/api/stocks")
def api_stocks():
    # current snapshot for display (no DB)
    out = []
    for s in STOCKS:
        try:
            info = fetch_stock_info(s)
            if info:
                info["ai_prediction"] = predict_trend(s)
                out.append(info)
        except Exception as e:
            print("api error", s, e)
    # sort by volume desc
    out = sorted(out, key=lambda x: x.get("volume", 0), reverse=True)
    return jsonify(out)

@app.route("/api/alerts")
def api_alerts():
    limit = int(request.args.get("limit", 200))
    return jsonify(get_alerts(limit=limit))

@app.route("/trigger-scan", methods=["POST", "GET"])
def trigger_scan():
    # manual trigger
    Thread(target=scan_and_alert).start()
    return jsonify({"status":"started"})

# serve frontend
@app.route("/")
def index():
    return send_from_directory(".", "index.html")

# Initialize DB and scheduler
init_db()
scheduler = BackgroundScheduler()
scheduler.add_job(func=scan_and_alert, trigger="interval", minutes=SCAN_INTERVAL_MINUTES, id="stock-scan", replace_existing=True)
scheduler.start()

# ensure scheduler stops on exit
import atexit
atexit.register(lambda: scheduler.shutdown(wait=False))

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 10000))
    # set host 0.0.0.0 for Render
    app.run(host="0.0.0.0", port=port)
