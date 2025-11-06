from flask import Flask, jsonify, render_template
import requests, pandas as pd, json, os
from datetime import datetime

app = Flask(__name__)

NSE_URL = "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%2050"
headers = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br"
}

DATA_FILE = "data/daily_data.json"

def fetch_nse_data():
    """Fetch live stock data from NSE"""
    try:
        s = requests.Session()
        s.get("https://www.nseindia.com", headers=headers)
        r = s.get(NSE_URL, headers=headers)
        data = r.json()
        df = pd.DataFrame(data["data"])
        df["pChange"] = df["pChange"].astype(float)
        df["lastPrice"] = df["lastPrice"].astype(float)
        return df[["symbol", "lastPrice", "pChange"]]
    except Exception as e:
        print("❌ Error fetching NSE data:", e)
        return pd.DataFrame(columns=["symbol", "lastPrice", "pChange"])

def save_data(df):
    """Save current snapshot to JSON file with timestamp"""
    os.makedirs("data", exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    record = {"timestamp": now, "data": df.to_dict(orient="records")}
    
    existing = []
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            try:
                existing = json.load(f)
            except:
                existing = []
    existing.append(record)
    with open(DATA_FILE, "w") as f:
        json.dump(existing, f, indent=2)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/bullish")
def bullish():
    df = fetch_nse_data()
    save_data(df)
    bullish = df[df["pChange"] > 0].sort_values("pChange", ascending=False).head(10)
    result = [
        {"name": s, "price": f"{p} ₹", "change": f"+{c}%"}
        for s, p, c in bullish.values
    ]
    return jsonify(result)

@app.route("/api/bearish")
def bearish():
    df = fetch_nse_data()
    bearish = df[df["pChange"] < 0].sort_values("pChange", ascending=True).head(10)
    result = [
        {"name": s, "price": f"{p} ₹", "change": f"{c}%"}
        for s, p, c in bearish.values
    ]
    return jsonify(result)

@app.route("/api/history")
def history():
    if not os.path.exists(DATA_FILE):
        return jsonify([])
    with open(DATA_FILE, "r") as f:
        data = json.load(f)
    return jsonify(data)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
