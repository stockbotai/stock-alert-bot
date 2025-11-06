from flask import Flask, jsonify, render_template
import yfinance as yf
import pandas as pd
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime

app = Flask(__name__)

data_cache = {"bullish": [], "bearish": [], "last_update": None}

def ewo(df):
    df["sma5"] = df["Close"].rolling(5).mean()
    df["sma35"] = df["Close"].rolling(35).mean()
    df["ewo"] = (df["sma5"] - df["sma35"]) / df["Close"] * 100
    return df["ewo"].iloc[-1]

def update_data():
    global data_cache
    sectors = {
        "METAL": ["TATASTEEL.NS","HINDALCO.NS","JSWSTEEL.NS"],
        "IT": ["INFY.NS","TCS.NS","HCLTECH.NS"],
        "AUTO": ["TATAMOTORS.NS","HEROMOTOCO.NS","BAJAJ-AUTO.NS"]
    }
    bullish, bearish = [], []
    for sector, stocks in sectors.items():
        for s in stocks:
            d1 = yf.download(s, period="2d", interval="1d")
            d5 = yf.download(s, period="5d", interval="5m")
            if len(d1)>35 and len(d5)>35:
                e1 = ewo(d1)
                e5 = ewo(d5)
                if e1>0 and e5>0:
                    bullish.append({"symbol": s, "sector": sector, "ewo_1d": round(e1,2), "ewo_5m": round(e5,2)})
                elif e1<0 and e5<0:
                    bearish.append({"symbol": s, "sector": sector, "ewo_1d": round(e1,2), "ewo_5m": round(e5,2)})
    data_cache = {"bullish": bullish, "bearish": bearish, "last_update": datetime.now().strftime("%H:%M:%S")}
    print("Updated:", data_cache["last_update"])

@app.route("/")
def home():
    return render_template("index.html", data=data_cache)

@app.route("/api")
def api():
    return jsonify(data_cache)

if __name__ == "__main__":
    scheduler = BackgroundScheduler()
    scheduler.add_job(update_data, "interval", minutes=1)
    scheduler.start()
    update_data()
    app.run(host="0.0.0.0", port=10000)
