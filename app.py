from flask import Flask, request, jsonify, render_template_string, session, redirect, url_for
from datetime import datetime, timedelta
import os
import socket

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "local_dev_secret")

# เก็บรายการ
transactions = []  # ทั้งหมด
approved_transactions = []  # อนุมัติแล้ว
wallet_daily_total = 0
wallet_history = []

# IP -> ชื่อ
ip_user_mapping = {}

# ฟังก์ชันแปลงประเภท
def translate_event_type(event_type, bank_code=None):
    if event_type in ["P2P", "TOPUP"]:
        return "วอลเล็ต"
    elif event_type == "PAYMENT":
        return "ชำระเงิน"
    elif event_type == "BANK" and bank_code:
        bank_mapping = {
            "BAY": "กรุงเทพ",
            "SCB": "ไทยพาณิชย์",
            "KBANK": "กสิกร",
            "KTB": "กรุงไทย",
            "TMB": "ทหารไทย",
            "GSB": "ออมสิน",
            "BBL": "กรุงเทพ",
            "CIMB": "CIMB",
        }
        return bank_mapping.get(bank_code, "ไม่ระบุธนาคาร")
    else:
        return "อื่น ๆ"

# หน้า Login
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            return render_template_string(login_html, error="กรุณากรอกชื่อ")
        ip = request.remote_addr
        if ip in ip_user_mapping:
            session['username'] = ip_user_mapping[ip]
        else:
            ip_user_mapping[ip] = name
            session['username'] = name
        return redirect(url_for("dashboard"))
    return render_template_string(login_html, error=None)

# Dashboard
@app.route("/dashboard")
def dashboard():
    username = session.get("username")
    if not username:
        return redirect(url_for("login"))

    # แยกออเดอร์ใหม่และอนุมัติแล้ว
    new_orders = [tx for tx in transactions if tx['status'] == 'new']
    approved_orders = approved_transactions

    # คำนวณยอด Wallet วันปัจจุบัน
    global wallet_daily_total
    today = datetime.now().date()
    wallet_daily_total = sum(tx['amount'] for tx in approved_orders if datetime.fromtimestamp(tx['timestamp']).date() == today and tx['event'] == "วอลเล็ต")

    return render_template_string(dashboard_html,
                                  username=username,
                                  new_orders=new_orders,
                                  approved_orders=approved_orders,
                                  wallet_daily_total=wallet_daily_total,
                                  wallet_history=wallet_history)

# Webhook รับรายการ
@app.route("/truewallet/webhook", methods=["POST"])
def webhook():
    data = request.json
    if not data:
        return jsonify({"status":"error", "message":"ไม่มีข้อมูล JSON"}), 400

    event_type_raw = data.get("event", "Other")
    bank_code = data.get("bank_code")
    event_type = translate_event_type(event_type_raw, bank_code)
    amount = float(data.get("amount",0))
    status = "new"
    txid = data.get("txid","N/A")
    timestamp = data.get("timestamp", datetime.now().timestamp())

    if event_type == "วอลเล็ต":
        name = data.get("name","-")
        phone = data.get("phone","-")
        name_phone = f"{name} / {phone}"
    else:
        name_phone = "-"

    tx = {
        "txid": txid,
        "event": event_type,
        "amount": amount,
        "name_phone": name_phone,
        "timestamp": timestamp,
        "status": status,
        "approved_by": None,
        "approved_time": None
    }

    transactions.append(tx)
    return jsonify({"status":"success"}), 200

# อนุมัติรายการ
@app.route("/approve/<txid>", methods=["POST"])
def approve(txid):
    username = session.get("username")
    if not username:
        return jsonify({"status":"error","message":"กรุณา login"}), 401

    for tx in transactions:
        if tx['txid'] == txid and tx['status'] == 'new':
            tx['status'] = 'approved'
            tx['approved_by'] = username
            tx['approved_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            approved_transactions.append(tx)
            transactions.remove(tx)
            return jsonify({"status":"success"}), 200
    return jsonify({"status":"error","message":"ไม่พบรายการหรืออนุมัติแล้ว"}), 404

# HTML Login
login_html = """
<!DOCTYPE html>
<html>
<head>
    <title>Login - THKBot168</title>
    <style>
        body { font-family: Arial; background: #f0f2f5; display:flex; justify-content:center; align-items:center; height:100vh; }
        .login-box { background:white; padding:40px; border-radius:10px; box-shadow:0 0 15px rgba(0,0,0,0.2); text-align:center; }
        input[type=text]{padding:10px; width:100%; margin:10px 0; border-radius:5px; border:1px solid #ccc;}
        button{padding:10px 20px; border:none; background:#4CAF50; color:white; border-radius:5px; cursor:pointer;}
        button:hover{background:#45a049;}
        .error{color:red;}
    </style>
</head>
<body>
    <div class="login-box">
        <h2>เข้าสู่ระบบ THKBot168</h2>
        {% if error %}<p class="error">{{ error }}</p>{% endif %}
        <form method="POST">
            <input type="text" name="name" placeholder="กรุณากรอกชื่อ">
            <button type="submit">เข้าสู่ระบบ</button>
        </form>
    </div>
</body>
</html>
"""

# HTML Dashboard
dashboard_html = """
<!DOCTYPE html>
<html>
<head>
<title>THKBot168 Dashboard</title>
<style>
body { font-family: Arial, sans-serif; background:#f0f2f5; padding:20px; }
h1 { text-align:center; }
table { width:100%; border-collapse:collapse; margin-bottom:20px; background:white;}
th, td { padding:12px; border-bottom:1px solid #ddd; text-align:left; }
tr:hover { background:#f1f1f1; }
.status-new { color:orange; font-weight:bold; }
.status-approved { color:green; font-weight:bold; }
button.approve-btn { padding:5px 10px; background:#4CAF50; color:white; border:none; border-radius:5px; cursor:pointer;}
button.approve-btn:hover { background:#45a049; }
.summary-box { background:white; padding:10px; border-radius:5px; margin-bottom:10px; }
</style>
<script>
function approveTx(txid){
    fetch('/approve/'+txid, {method:'POST'})
    .then(res => res.json())
    .then(data => { if(data.status=='success') location.reload(); else alert(data.message); });
}
setTimeout(()=>{location.reload();}, 5000); // auto-refresh
</script>
</head>
<body>
<h1>สวัสดี {{username}}</h1>
<div class="summary-box">
    <b>ยอดฝากวอเลทวันนี้:</b> {{ wallet_daily_total }} บาท
</div>

<h2>รายการใหม่</h2>
<table>
<tr><th>Transaction ID</th><th>ประเภท</th><th>จำนวน</th><th>ชื่อ/เบอร์</th><th>เวลา</th><th>สถานะ</th><th>อนุมัติ</th></tr>
{% for tx in new_orders %}
<tr>
<td>{{ tx.txid }}</td>
<td>{{ tx.event }}</td>
<td>{{ "%.2f"|format(tx.amount) }}</td>
<td>{{ tx.name_phone }}</td>
<td>{{ datetime.fromtimestamp(tx.timestamp).strftime("%Y-%m-%d %H:%M:%S") }}</td>
<td class="status-{{ tx.status }}">{{ tx.status }}</td>
<td><button class="approve-btn" onclick="approveTx('{{ tx.txid }}')">อนุมัติ</button></td>
</tr>
{% endfor %}
</table>

<h2>รายการที่อนุมัติแล้ว</h2>
<table>
<tr><th>Transaction ID</th><th>ประเภท</th><th>จำนวน</th><th>ชื่อ/เบอร์</th><th>เวลา</th><th>อนุมัติโดย</th><th>เวลาที่อนุมัติ</th></tr>
{% for tx in approved_orders %}
<tr>
<td>{{ tx.txid }}</td>
<td>{{ tx.event }}</td>
<td>{{ "%.2f"|format(tx.amount) }}</td>
<td>{{ tx.name_phone }}</td>
<td>{{ datetime.fromtimestamp(tx.timestamp).strftime("%Y-%m-%d %H:%M:%S") }}</td>
<td>{{ tx.approved_by }}</td>
<td>{{ tx.approved_time }}</td>
</tr>
{% endfor %}
</table>
</body>
</html>
"""

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)))
