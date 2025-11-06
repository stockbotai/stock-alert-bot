from flask import Flask, render_template, jsonify
import random
import datetime

app = Flask(__name__)

# In-memory data storage (will hold full day’s data)
market_data = []

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/market-data')
def get_market_data():
    """Generate and store dummy market data (simulating API or stock feed)"""
    now = datetime.datetime.now().strftime("%H:%M:%S")
    avg_change = round(random.uniform(-1.5, 1.5), 2)
    top_bullish = random.choice(["RELIANCE", "HDFCBANK", "TCS", "SBILIFE", "BHARTIARTL"])
    top_bearish = random.choice(["COALINDIA", "TATASTEEL", "POWERGRID", "HINDALCO", "LT"])
    
    new_data = {
        "time": now,
        "avg_change": avg_change,
        "bullish": top_bullish,
        "bearish": top_bearish
    }

    # Store with timestamp (for whole day record)
    market_data.append(new_data)
    
    return jsonify({
        "latest": new_data,
        "history": market_data[-50:]  # last 50 data points for chart
    })

if __name__ == "__main__":
    app.run(debug=True)
