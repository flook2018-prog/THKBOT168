from flask import Flask, request, jsonify, render_template_string, session, redirect, url_for
import os, threading, time
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "local_dev_secret")

# เก็บข้อมูล
transactions = []
approved_transactions = []
wallet_daily_total = 0
wallet_history = []
ip_user_mapping = {}

# ------------------ Helper ------------------
def translate_event_type(event_type, bank_code=None):
    if event_type in ["P2P", "TOPUP"]:
        return "วอลเล็ต"
    elif event_type == "PAYMENT":
        return "ชำระเงิน"
    elif event_type == "BANK" and bank_code:
        bank_mapping = {
            "SCB": "ไทยพาณิชย์",
            "KBANK": "กสิกรไทย",
            "KTB": "กรุงไทย",
            "BBL": "กรุงเทพ",
            "BAY": "กรุงศรี",
            "GSB": "ออมสิน",
            "CIMB": "CIMB",
            "TMB": "ทหารไทย",
        }
        return bank_mapping.get(bank_code, "ไม่ระบุธนาคาร")
    return "อื่น ๆ"

def ts_to_str(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")

# ------------------ HTML ------------------
login_html = """
<!DOCTYPE html>
<html>
<head>
    <title>เข้าสู่ระบบ</title>
    <style>
        body { background:#f0f2f5; display:flex; justify-content:center; align-items:center; height:100vh; font-family:Arial; }
        .login-box { background:white; padding:30px; border-radius:12px; box-shadow:0 0 10px rgba(0,0,0,0.1); width:300px; text-align:center; }
        input { width:100%; padding:10px; margin-top:10px; border:1px solid #ccc; border-radius:8px; }
        button { margin-top:15px; padding:10px; width:100%; background:#007bff; color:white; border:none; border-radius:8px; cursor:pointer; }
        button:hover { background:#0056b3; }
        .error { color:red; margin-top:10px; }
    </style>
</head>
<body>
    <div class="login-box">
        <h2>ตั้งชื่อผู้ใช้</h2>
        <form method="POST">
            <input type="text" name="name" placeholder="กรอกชื่อของคุณ">
            <button type="submit">บันทึก</button>
        </form>
        {% if error %}<div class="error">{{ error }}</div>{% endif %}
    </div>
</body>
</html>
"""

dashboard_html = """
<!DOCTYPE html>
<html>
<head>
    <title>THKBot168 Dashboard</title>
    <style>
        body { font-family:Arial, sans-serif; background:#f0f2f5; padding:20px; }
        h1 { text-align:center; }
        table { width:100%; border-collapse:collapse; background:white; margin-top:15px; }
        th, td { padding:10px; border-bottom:1px solid #ddd; text-align:left; }
        tr:hover { background:#f9f9f9; }
        .status-new { color:orange; font-weight:bold; }
        .status-approved { color:green; font-weight:bold; }
        .summary { background:#007bff; color:white; padding:15px; border-radius:10px; margin-bottom:20px; }
        button { padding:6px 12px; border:none; border-radius:6px; background:#28a745; color:white; cursor:pointer; }
        button:hover { background:#218838; }
    </style>
    <script>
        function approveTx(txid){
            fetch("/approve/"+txid,{method:"POST"})
            .then(r=>r.json()).then(d=>{
                if(d.status=="success"){ loadData(); }
                else{ alert(d.message); }
            });
        }
        function loadData(){
            fetch("/get_transactions").then(r=>r.json()).then(data=>{
                let newT=document.getElementById("newOrders");
                newT.innerHTML="";
                data.new_orders.forEach(tx=>{
                    let row=`<tr>
                        <td>${tx.txid}</td>
                        <td>${tx.event}</td>
                        <td>${tx.amount.toFixed(2)}</td>
                        <td>${tx.name_phone}</td>
                        <td>${tx.time}</td>
                        <td class="status-${tx.status}">${tx.status}</td>
                        <td><button onclick="approveTx('${tx.txid}')">อนุมัติ</button></td>
                    </tr>`;
                    newT.innerHTML+=row;
                });
                document.getElementById("walletTotal").innerText=data.wallet_daily_total.toFixed(2);
            });
        }
        setInterval(loadData,5000);
        window.onload=loadData;
    </script>
</head>
<body>
    <div class="summary">
        👤 ผู้ใช้: {{ username }} | 💰 ยอดฝากวันนี้: <span id="walletTotal">{{ wallet_daily_total }}</span> บาท
    </div>
    <h1>THKBot168 Dashboard</h1>

    <h2>ออเดอร์ใหม่</h2>
    <table>
        <tr><th>TXID</th><th>ประเภท</th><th>จำนวน</th><th>ชื่อ/เบอร์</th><th>เวลา</th><th>สถานะ</th><th>อนุมัติ</th></tr>
        <tbody id="newOrders"></tbody>
    </table>

    <h2>ออเดอร์ที่อนุมัติแล้ว</h2>
    <table>
        <tr><th>TXID</th><th>ประเภท</th><th>จำนวน</th><th>ชื่อ/เบอร์</th><th>เวลา</th><th>สถานะ</th><th>อนุมัติโดย</th><th>เวลาอนุมัติ</th></tr>
        {% for tx in approved_orders %}
        <tr>
            <td>{{ tx.txid }}</td>
            <td>{{ tx.event }}</td>
            <td>{{ "%.2f"|format(tx.amount) }}</td>
            <td>{{ tx.name_phone }}</td>
            <td>{{ ts_to_str(tx.timestamp) }}</td>
            <td class="status-approved">อนุมัติแล้ว</td>
            <td>{{ tx.approved_by }}</td>
            <td>{{ tx.approved_time }}</td>
        </tr>
        {% endfor %}
    </table>
</body>
</html>
"""

# ------------------ Routes ------------------
@app.route("/login", methods=["GET","POST"])
def login():
    ip = request.remote_addr
    if ip in ip_user_mapping:
        session['username'] = ip_user_mapping[ip]
        return redirect(url_for("dashboard"))
    if request.method=="POST":
        name = request.form.get("name","").strip()
        if not name:
            return render_template_string(login_html,error="กรุณากรอกชื่อ")
        ip_user_mapping[ip] = name
        session['username'] = name
        return redirect(url_for("dashboard"))
    return render_template_string(login_html,error=None)

@app.route("/")
def home():
    ip = request.remote_addr
    if ip not in ip_user_mapping:
        return redirect(url_for("login"))
    return redirect(url_for("dashboard"))

@app.route("/dashboard")
def dashboard():
    ip = request.remote_addr
    username = ip_user_mapping.get(ip,"Guest")
    return render_template_string(dashboard_html,
                                  username=username,
                                  approved_orders=approved_transactions,
                                  wallet_daily_total=wallet_daily_total,
                                  ts_to_str=ts_to_str)

@app.route("/get_transactions")
def get_transactions():
    new_orders = [{
        "txid":tx["txid"],
        "event":tx["event"],
        "amount":tx["amount"],
        "name_phone":tx["name_phone"],
        "time":ts_to_str(tx["timestamp"]),
        "status":tx["status"]
    } for tx in transactions if tx["status"]=="new"]
    return jsonify({"new_orders":new_orders,"wallet_daily_total":wallet_daily_total})

@app.route("/truewallet/webhook", methods=["POST"])
def webhook():
    global wallet_daily_total
    try:
        data = request.json
        txid = data.get("txid") or data.get("transaction_id") or "N/A"
        amount_raw = data.get("amount") or data.get("total_amount") or 0
        try: amount=float(amount_raw)
        except: amount=0.0
        event_type_raw = data.get("event") or data.get("type") or "Other"
        bank_code = data.get("bank_code") or data.get("bank")
        event_type = translate_event_type(event_type_raw, bank_code)
        name_phone = "-"
        if event_type=="วอลเล็ต":
            name = data.get("name") or "-"
            phone = data.get("phone") or "-"
            name_phone = f"{name} / {phone}"
        timestamp = data.get("timestamp") or datetime.now().timestamp()
        tx = {"txid":txid,"event":event_type,"amount":amount,"name_phone":name_phone,
              "timestamp":timestamp,"status":"new","approved_by":None,"approved_time":None}
        transactions.append(tx)
        if event_type=="วอลเล็ต":
            wallet_daily_total+=amount
        return jsonify({"status":"success"}),200
    except Exception as e:
        return jsonify({"status":"error","message":str(e)}),500

@app.route("/approve/<txid>", methods=["POST"])
def approve(txid):
    username = session.get("username","Guest")
    for tx in transactions:
        if tx["txid"]==txid and tx["status"]=="new":
            tx["status"]="approved"
            tx["approved_by"]=username
            tx["approved_time"]=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            approved_transactions.append(tx)
            transactions.remove(tx)
            return jsonify({"status":"success"}),200
    return jsonify({"status":"error","message":"ไม่พบรายการ"}),404

# Reset wallet รายวัน
def reset_daily_wallet():
    global wallet_daily_total, wallet_history
    last_date = datetime.now().date()
    while True:
        now = datetime.now()
        if now.date()!=last_date:
            wallet_history.append({"date":last_date.strftime("%Y-%m-%d"),"total":wallet_daily_total})
            wallet_daily_total=0
            last_date=now.date()
        time.sleep(60)

threading.Thread(target=reset_daily_wallet,daemon=True).start()

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)))
