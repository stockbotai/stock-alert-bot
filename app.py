from flask import Flask, jsonify, send_from_directory
import yfinance as yf
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression

app = Flask(__name__)

STOCKS = [
    "RELIANCE.NS","TCS.NS","SBIN.NS","HDFCBANK.NS",
    "INFY.NS","LT.NS","BHARTIARTL.NS","ICICIBANK.NS"
]

def predict_trend(symbol):
    try:
        data = yf.download(symbol, period="5d", interval="30m")
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
    except:
        return "Error"

def get_trending_stocks():
    data = []
    for s in STOCKS:
        ticker = yf.Ticker(s)
        hist = ticker.history(period="1d", interval="5m")
        if len(hist) > 0:
            change = (hist["Close"].iloc[-1] - hist["Open"].iloc[0]) / hist["Open"].iloc[0] * 100
            volume = hist["Volume"].sum()
            trend = predict_trend(s)
            data.append({
                "symbol": s,
                "change": round(change,2),
                "volume": int(volume),
                "ai_prediction": trend
            })
    df = pd.DataFrame(data)
    df = df.sort_values(by="volume", ascending=False)
    return df.to_dict(orient="records")

@app.route("/api/stocks")
def api_stocks():
    trending = get_trending_stocks()
    return jsonify(trending)

@app.route("/")
def index():
    return send_from_directory(".", "index.html")

import os

if name == "main":
    # Flask app run karega Render ke port par
    import os
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
