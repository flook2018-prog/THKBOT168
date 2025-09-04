from flask import Flask, render_template, request, jsonify
import jwt
import os
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get("FLASK_SECRET")

# เก็บรายการชั่วคราว (ถ้าใช้จริงควรใช้ DB)
transactions = []

TRUEWALLET_SECRET = os.environ.get("TRUEWALLET_SECRET")
DASHBOARD_TOKEN = os.environ.get("DASHBOARD_TOKEN")

@app.route('/')
def index():
    token = request.args.get("token")
    if token != DASHBOARD_TOKEN:
        return "Unauthorized", 401
    return render_template("dashboard.html", transactions=reversed(transactions))

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    message_jwt = data.get("message")
    if not message_jwt:
        return jsonify({"error": "No message"}), 400

    try:
        payload = jwt.decode(message_jwt, TRUEWALLET_SECRET, algorithms=["HS256"])
        # แปลงจำนวนเงินเป็นบาท
        payload["amount"] = int(payload.get("amount",0))/100
        payload["received_time"] = datetime.strptime(payload["received_time"][:19], "%Y-%m-%dT%H:%M:%S").strftime("%d-%m-%Y %H:%M:%S")
        transactions.append(payload)
        # เก็บรายการล่าสุดไม่เกิน 100 รายการ
        if len(transactions) > 100:
            transactions.pop(0)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=True)
