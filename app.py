from flask import Flask, request, jsonify, render_template_string, redirect, session
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "local_dev_secret")

transactions = []
wallet_history = {}  # เก็บยอดฝากย้อนหลัง {date: amount}

# ------------------------------
# Helper แปลงประเภท
# ------------------------------
def translate_event_type(event_type, bank_code=None):
    if event_type in ["P2P", "TOPUP"]:
        return "วอลเล็ต"
    elif event_type == "PAYMENT":
        return "ชำระเงิน"
    elif event_type == "BANK" and bank_code:
        bank_mapping = {
            "BAY": "กรุงศรี",
            "SCB": "ไทยพาณิชย์",
            "KBANK": "กสิกรไทย",
            "KTB": "กรุงไทย",
            "TMB": "ทหารไทย",
            "GSB": "ออมสิน",
            "BBL": "กรุงเทพ",
            "CIMB": "CIMB",
        }
        return bank_mapping.get(bank_code, "ไม่ระบุธนาคาร")
    return "อื่น ๆ"

# ------------------------------
# หน้า Login
# ------------------------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        if username:
            session["username"] = username
            return redirect("/dashboard")
    return """
    <html>
    <head>
        <style>
            body { display: flex; justify-content: center; align-items: center; height: 100vh; background: #f0f2f5; font-family: Arial; }
            .login-box { background: white; padding: 30px; border-radius: 12px; box-shadow: 0px 4px 10px rgba(0,0,0,0.1); width: 300px; text-align: center; }
            input { width: 90%; padding: 10px; margin: 10px 0; border-radius: 8px; border: 1px solid #ccc; }
            button { padding: 10px 20px; border: none; border-radius: 8px; background: #007bff; color: white; font-weight: bold; cursor: pointer; }
            button:hover { background: #0056b3; }
        </style>
    </head>
    <body>
        <div class="login-box">
            <h2>เข้าสู่ระบบ</h2>
            <form method="POST">
                <input type="text" name="username" placeholder="ใส่ชื่อของคุณ" required>
                <button type="submit">เข้าสู่ระบบ</button>
            </form>
        </div>
    </body>
    </html>
    """

# ------------------------------
# Dashboard
# ------------------------------
@app.route("/dashboard")
def dashboard():
    username = session.get("username", "Guest")

    # แยกออเดอร์
    new_orders = [tx for tx in transactions if tx["status"] == "new"]
    approved_orders = [tx for tx in transactions if tx["status"] == "approved"]

    # แสดงแค่ 10 รายการล่าสุด
    new_orders = new_orders[-10:]

    # ยอดรวมของวันนี้
    today = datetime.now().strftime("%Y-%m-%d")
    today_total = wallet_history.get(today, 0)

    dashboard_html = """
    <html>
    <head>
        <title>THKBot168 Dashboard</title>
        <style>
            body { font-family: Arial; background: #f0f2f5; padding: 20px; }
            h2 { margin-top: 30px; }
            table { width: 100%; border-collapse: collapse; margin-top: 10px; background: white; }
            th, td { padding: 10px; border-bottom: 1px solid #ddd; text-align: left; }
            .status-new { color: orange; font-weight: bold; }
            .status-approved { color: green; font-weight: bold; }
            .scroll-box { max-height: 250px; overflow-y: auto; border: 1px solid #ccc; border-radius: 8px; }
            .btn { padding: 5px 10px; border: none; border-radius: 6px; cursor: pointer; }
            .btn-success { background: green; color: white; }
            .btn-success:hover { background: darkgreen; }
            .summary { background: #fff; padding: 15px; border-radius: 8px; margin-bottom: 20px; font-weight: bold; }
        </style>
        <meta http-equiv="refresh" content="5"> <!-- auto refresh ทุก 5 วิ -->
    </head>
    <body>
        <h1>THKBot168 Dashboard</h1>
        <p>ยินดีต้อนรับ, {{username}}</p>
        <div class="summary">ยอดฝากรวมของวันนี้: {{ "%.2f"|format(today_total) }} บาท</div>

        <h2>ออเดอร์ใหม่ (ล่าสุด 10 รายการ)</h2>
        <div class="scroll-box">
        <table>
            <tr><th>TXID</th><th>ประเภท</th><th>จำนวน</th><th>ชื่อ/เบอร์</th><th>เวลา</th><th>สถานะ</th><th>อนุมัติ</th></tr>
            {% for tx in new_orders %}
            <tr>
                <td>{{tx.txid}}</td>
                <td>{{tx.event}}</td>
                <td>{{"%.2f"|format(tx.amount)}}</td>
                <td>{{tx.name_phone}}</td>
                <td>{{tx.time}}</td>
                <td class="status-{{tx.status}}">{{tx.status}}</td>
                <td>
                    <form action="/approve/{{tx.txid}}" method="post">
                        <button type="submit" class="btn btn-success">อนุมัติ</button>
                    </form>
                </td>
            </tr>
            {% endfor %}
        </table>
        </div>

        <h2>ออเดอร์ที่อนุมัติแล้ว</h2>
        <div class="scroll-box">
        <table>
            <tr><th>TXID</th><th>ประเภท</th><th>จำนวน</th><th>ชื่อ/เบอร์</th><th>เวลา</th><th>สถานะ</th><th>อนุมัติโดย</th><th>เวลาอนุมัติ</th></tr>
            {% for tx in approved_orders %}
            <tr>
                <td>{{tx.txid}}</td>
                <td>{{tx.event}}</td>
                <td>{{"%.2f"|format(tx.amount)}}</td>
                <td>{{tx.name_phone}}</td>
                <td>{{tx.time}}</td>
                <td class="status-{{tx.status}}">{{tx.status}}</td>
                <td>{{tx.approved_by}}</td>
                <td>{{tx.approved_time}}</td>
            </tr>
            {% endfor %}
        </table>
        </div>

        <h2>ประวัติยอดฝากย้อนหลัง</h2>
        <div class="scroll-box">
        <table>
            <tr><th>วันที่</th><th>ยอดฝากรวม (บาท)</th></tr>
            {% for d, amt in wallet_history.items() %}
            <tr>
                <td>{{d}}</td>
                <td>{{"%.2f"|format(amt)}}</td>
            </tr>
            {% endfor %}
        </table>
        </div>
    </body>
    </html>
    """
    return render_template_string(dashboard_html,
                                  username=username,
                                  new_orders=new_orders,
                                  approved_orders=approved_orders,
                                  wallet_history=wallet_history,
                                  today_total=today_total)

# ------------------------------
# API รับ webhook
# ------------------------------
@app.route("/truewallet/webhook", methods=["POST"])
def webhook():
    try:
        data = request.json
        event_type_raw = data.get("event", "Other")
        bank_code = data.get("bank_code")
        event_type = translate_event_type(event_type_raw, bank_code)

        amount = float(data.get("amount", 0))
        txid = data.get("txid", "N/A")
        timestamp = data.get("timestamp")
        time_str = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S") if timestamp else datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if event_type == "วอลเล็ต":
            name = data.get("name", "-")
            phone = data.get("phone", "-")
            name_phone = f"{name} / {phone}"
        else:
            name_phone = "-"

        transactions.append({
            "txid": txid,
            "event": event_type,
            "amount": amount,
            "name_phone": name_phone,
            "time": time_str,
            "status": "new",
            "approved_by": "",
            "approved_time": ""
        })

        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ------------------------------
# API อนุมัติ
# ------------------------------
@app.route("/approve/<txid>", methods=["POST"])
def approve(txid):
    username = session.get("username", "Admin")
    for tx in transactions:
        if tx["txid"] == txid and tx["status"] == "new":
            tx["status"] = "approved"
            tx["approved_by"] = username
            tx["approved_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if tx["event"] == "วอลเล็ต":
                day = datetime.now().strftime("%Y-%m-%d")
                wallet_history[day] = wallet_history.get(day, 0) + tx["amount"]
            break
    return redirect("/dashboard")

# ------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

