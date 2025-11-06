from flask import Flask, jsonify, render_template
import requests
import pandas as pd
from datetime import datetime

app = Flask(__name__)

# NSE API endpoints (public JSON endpoints)
NSE_SECTOR_URL = "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%2050"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive"
}

def fetch_nse_data():
    """Fetch latest NIFTY 50 stock data from NSE"""
    try:
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers)
        response = session.get(NSE_SECTOR_URL, headers=headers)
        data = response.json()
        df = pd.DataFrame(data['data'])
        df['pChange'] = df['pChange'].astype(float)
        df['lastPrice'] = df['lastPrice'].astype(float)
        return df[['symbol', 'lastPrice', 'pChange']]
    except Exception as e:
        print("Error fetching NSE data:", e)
        return pd.DataFrame(columns=['symbol', 'lastPrice', 'pChange'])


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/bullish")
def get_bullish():
    df = fetch_nse_data()
    if df.empty:
        return jsonify([])
    bullish = df[df['pChange'] > 0].sort_values(by='pChange', ascending=False).head(10)
    result = [
        {"name": row['symbol'], "price": f"{row['lastPrice']} ₹", "change": f"+{row['pChange']}%"}
        for _, row in bullish.iterrows()
    ]
    return jsonify(result)


@app.route("/api/bearish")
def get_bearish():
    df = fetch_nse_data()
    if df.empty:
        return jsonify([])
    bearish = df[df['pChange'] < 0].sort_values(by='pChange', ascending=True).head(10)
    result = [
        {"name": row['symbol'], "price": f"{row['lastPrice']} ₹", "change": f"{row['pChange']}%"}
        for _, row in bearish.iterrows()
    ]
    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
