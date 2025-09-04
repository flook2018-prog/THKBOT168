from flask import Flask, request, render_template
import os
import jwt
from datetime import datetime

app = Flask(__name__)

# อ่าน SECRET_KEY จาก Service Variable ใน Railway
SECRET_KEY = os.environ.get("TRUEWALLET_SECRET")

# เก็บรายการเงินเข้า
transactions = []

# Webhook รับ POST จาก TrueWallet
@app.route("/truewallet/webhook", methods=["POST"])
def webhook():
    if not request.is_json:
        return {"status":"error","message":"Expected JSON"}, 400

    data = request.get_json()
    message = data.get("message")
    if not message:
        return {"status":"error","message":"Missing 'message'"}, 400

    try:
        # Decode JWT
        payload = jwt.decode(message, SECRET_KEY, algorithms=["HS256"])

        # แปลงเวลา
        payload["received_time"] = datetime.strptime(
            payload["received_time"][:19], "%Y-%m-%dT%H:%M:%S"
        ).strftime("%d/%m/%Y %H:%M:%S")

        # เก็บรายการใหม่ด้านบน
        transactions.insert(0, payload)

        print("New transaction:", payload)
        return {"status":"ok"}, 200
    except Exception as e:
        print("Error decoding JWT:", e)
        return {"status":"error","message": str(e)}, 400

# หน้าเว็บ Dashboard
@app.route("/")
def index():
    return render_template("index.html", transactions=transactions)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
