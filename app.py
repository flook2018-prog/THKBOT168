from flask import Flask, request, jsonify
import os

app = Flask(__name__)

# ดึง SECRET_KEY จาก Environment ของ Railway
SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY ไม่ได้ตั้งค่าใน Environment")

# ตัวอย่างเก็บรายการ
transactions = []

def translate_event_type(event_type):
    # แปลงประเภท Event ของ TrueWallet เป็นข้อความไทย
    mapping = {
        "P2P": "วอลเล็ตโอนเงิน",
        "TOPUP": "เติมเงิน",
        "PAYMENT": "จ่ายเงิน"
    }
    return mapping.get(event_type, event_type)

# หน้าเว็บหลัก
@app.route("/")
def index():
    html = """
    <h1>THKBot168 Dashboard</h1>
    <p>รายการล่าสุด:</p>
    <ul>
        {% for tx in transactions %}
            <li>{{ tx }}</li>
        {% endfor %}
    </ul>
    """
    return app.jinja_env.from_string(html).render(transactions=transactions)

# Webhook สำหรับ TrueWallet
@app.route("/truewallet/webhook", methods=["POST"])
def webhook():
    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "ไม่มีข้อมูล JSON"}), 400

        # แปลงประเภท Event
        event_type = translate_event_type(data.get("event", "Unknown"))
        amount = data.get("amount", 0)

        # เก็บรายการไว้ใน memory (คุณสามารถเก็บใน DB ได้)
        transactions.append(f"{event_type}: {amount} บาท")

        return jsonify({"status": "success"}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
