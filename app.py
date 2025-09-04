from flask import Flask, request, render_template
import os
import jwt
from datetime import datetime

app = Flask(__name__)

# อ่าน SECRET จาก Service Variable ของ Railway
SECRET_KEY = os.environ.get("TRUEWALLET_SECRET")

# เก็บรายการเงินเข้า
transactions = []

@app.route("/truewallet/webhook", methods=["POST"])
def webhook():
    try:
        data = request.json
        message = data.get("message")
        payload = jwt.decode(message, SECRET_KEY, algorithms=["HS256"])
        
        # แปลงเวลาที่ได้รับเงิน
        payload["received_time"] = datetime.strptime(payload["received_time"][:19], "%Y-%m-%dT%H:%M:%S").strftime("%d/%m/%Y %H:%M:%S")
        
        # เก็บรายการ
        transactions.insert(0, payload)  # แสดงรายการล่าสุดด้านบน
        
        print("New transaction:", payload)
        return {"status":"ok"}, 200
    except Exception as e:
        print("Error:", e)
        return {"status":"error", "message": str(e)}, 400

@app.route("/")
def index():
    return render_template("index.html", transactions=transactions)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
