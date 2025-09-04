from flask import Flask, request, jsonify, render_template_string, session, redirect, url_for
from datetime import datetime, timedelta
import os, threading, time

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY","local_dev_secret")

# ข้อมูล
transactions = []            # รายการใหม่
approved_transactions = []   # รายการอนุมัติแล้ว
wallet_daily_total = 0       # ยอด Wallet วันนี้
wallet_history = []          # ยอดย้อนหลัง
ip_user_mapping = {}         # จำชื่อผู้ใช้ตาม IP

# แปลงประเภท
def translate_event_type(event_type, bank_code=None):
    if event_type in ["P2P","TOPUP","P2P_TRANSFER"]:
        return "วอลเล็ต"
    elif event_type=="PAYMENT":
        return "ชำระเงิน"
    elif event_type=="BANK" and bank_code:
        bank_mapping = {
            "BAY":"กรุงเทพ","SCB":"ไทยพาณิชย์","KBANK":"กสิกร",
            "KTB":"กรุงไทย","TMB":"ทหารไทย","GSB":"ออมสิน","BBL":"กรุงเทพ","CIMB":"CIMB"
        }
        return bank_mapping.get(bank_code,"ไม่ระบุธนาคาร")
    else:
        return "อื่น ๆ"

def ts_to_str(ts):
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M:%S")
    except:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# Login
login_html = """<!DOCTYPE html>
<html>
<head>
<title>Login - THKBot168</title>
<style>
body {font-family:Arial;background:#f0f2f5;display:flex;justify-content:center;align-items:center;height:100vh;}
.login-box {background:white;padding:40px;border-radius:10px;box-shadow:0 0 15px rgba(0,0,0,0.2);text-align:center;}
input[type=text]{padding:10px;width:100%;margin:10px 0;border-radius:5px;border:1px solid #ccc;}
button{padding:10px 20px;border:none;background:#4CAF50;color:white;border-radius:5px;cursor:pointer;}
button:hover{background:#45a049;}
.error{color:red;}
</style>
</head>
<body>
<div class="login-box">
<h2>ตั้งชื่อครั้งแรก</h2>
{% if error %}<p class="error">{{ error }}</p>{% endif %}
<form method="POST">
<input type="text" name="name" placeholder="กรุณากรอกชื่อ">
<button type="submit">ยืนยัน</button>
</form>
</div>
</body>
</html>
"""

@app.route("/", methods=["GET","POST"])
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

# Dashboard
dashboard_html = """<!DOCTYPE html>
<html>
<head>
<title>THKBot168 Dashboard</title>
<style>
body {font-family:Arial;background:#f0f2f5;padding:20px;}
h1,h2 {text-align:center;}
table {width:100%;border-collapse:collapse;background:white;}
th,td {padding:12px;border-bottom:1px solid #ddd;text-align:left;}
tr:hover {background-color:#f1f1f1;}
.status-new {color:orange;font-weight:bold;}
.status-approved {color:green;font-weight:bold;}
.status-rejected {color:red;font-weight:bold;}
input[type=text]{padding:8px;width:100%;margin-bottom:10px;border-radius:5px;border:1px solid #ccc;}
button.approve{padding:5px 10px;background:#4CAF50;color:white;border:none;border-radius:5px;cursor:pointer;}
button.approve:hover{background:#45a049;}
#wallet_total{font-weight:bold;font-size:16px;margin-bottom:10px;}
#popup{position:fixed;top:10px;right:10px;background:#4CAF50;color:white;padding:10px;border-radius:5px;display:none;}
</style>
<script>
function filterTable() {
    let input = document.getElementById("searchInput").value.toLowerCase();
    let rows = document.getElementById("txTable").getElementsByTagName("tr");
    for (let i=1;i<rows.length;i++){
        let cells = rows[i].getElementsByTagName("td");
        let match=false;
        for(let j=0;j<cells.length;j++){
            if(cells[j].innerText.toLowerCase().includes(input)){match=true;break;}
        }
        rows[i].style.display = match?"":"none";
    }
}
function approveTx(txid){
    fetch("/approve/"+txid,{method:"POST"})
    .then(res=>res.json())
    .then(d=>{if(d.status=="success"){location.reload();alert("อนุมัติเรียบร้อย");}})
}
function popupShow(msg){
    let p=document.getElementById("popup");
    p.innerText=msg;
    p.style.display="block";
    setTimeout(()=>{p.style.display="none";},3000);
}
</script>
</head>
<body>
<h1>THKBot168 Dashboard</h1>
<h2>สวัสดี {{username}}</h2>
<div id="wallet_total">ยอด Wallet วันนี้: {{wallet_daily_total}}</div>
<input type="text" id="searchInput" onkeyup="filterTable()" placeholder="ค้นหารายการ...">
<div id="popup"></div>

<h2>รายการใหม่</h2>
<table id="txTable">
<tr><th>TXID</th><th>ประเภท</th><th>จำนวน</th><th>ชื่อ/เบอร์</th><th>เวลา</th><th>สถานะ</th><th>อนุมัติ</th></tr>
{% for tx in new_orders %}
<tr>
<td>{{tx.txid}}</td>
<td>{{tx.event}}</td>
<td>{{"%.2f"|format(tx.amount)}}</td>
<td>{{tx.name_phone}}</td>
<td>{{ts_to_str(tx.timestamp)}}</td>
<td class="status-{{tx.status}}">{{tx.status}}</td>
<td><button class="approve" onclick="approveTx('{{tx.txid}}')">อนุมัติ</button></td>
</tr>
{% endfor %}
</table>

<h2>รายการอนุมัติแล้ว</h2>
<table>
<tr><th>TXID</th><th>ประเภท</th><th>จำนวน</th><th>ชื่อ/เบอร์</th><th>เวลา</th><th>อนุมัติโดย</th><th>เวลาอนุมัติ</th></tr>
{% for tx in approved_orders %}
<tr>
<td>{{tx.txid}}</td>
<td>{{tx.event}}</td>
<td>{{"%.2f"|format(tx.amount)}}</td>
<td>{{tx.name_phone}}</td>
<td>{{ts_to_str(tx.timestamp)}}</td>
<td>{{tx.approved_by}}</td>
<td>{{tx.approved_time}}</td>
</tr>
{% endfor %}
</table>

<h2>ยอด Wallet ย้อนหลัง</h2>
<table>
<tr><th>วันที่</th><th>ยอดรวม</th></tr>
{% for w in wallet_history %}
<tr><td>{{w.date}}</td><td>{{"%.2f"|format(w.total)}}</td></tr>
{% endfor %}
</table>

</body>
</html>
"""

# Dashboard route
@app.route("/dashboard")
def dashboard():
    ip = request.remote_addr
    username = ip_user_mapping.get(ip,"Guest")

    new_orders = [tx for tx in transactions if tx['status']=="new"]
    approved_orders = approved_transactions

    # อัพเดทยอด Wallet วันนี้
    global wallet_daily_total
    today = datetime.now().date()
    wallet_daily_total = sum(
        tx['amount'] 
        for tx in approved_orders 
        if datetime.fromtimestamp(tx['timestamp']).date()==today and tx['event']=="วอลเล็ต"
    )

    return render_template_string(dashboard_html,
                                  username=username,
                                  new_orders=new_orders,
                                  approved_orders=approved_orders,
                                  wallet_daily_total=wallet_daily_total,
                                  wallet_history=wallet_history,
                                  ts_to_str=ts_to_str)

# Webhook
@app.route("/truewallet/webhook", methods=["POST"])
def webhook():
    global wallet_daily_total
    try:
        data = request.json
        if not data:
            return jsonify({"status":"error","message":"ไม่มีข้อมูล JSON"}),400

        txid = data.get("txid") or data.get("transaction_id") or "N/A"
        amount_raw = data.get("amount") or 0
        try: amount = float(amount_raw)
        except: amount = 0.0
        event_type_raw = data.get("event") or "Other"
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

        # อัพเดทยอด Wallet วันนี้ทันที
        if event_type=="วอลเล็ต":
            wallet_daily_total += amount

        return jsonify({"status":"success"}),200
    except Exception as e:
        return jsonify({"status":"error","message":str(e)}),500

# Approve
@app.route("/approve/<txid>", methods=["POST"])
def approve(txid):
    global wallet_daily_total
    username = session.get("username","Guest")
    for tx in transactions:
        if tx['txid']==txid and tx['status']=="new":
            tx['status']="approved"
            tx['approved_by']=username
            tx['approved_time']=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            approved_transactions.append(tx)
            transactions.remove(tx)
            if tx['event']=="วอลเล็ต":
                wallet_daily_total += tx['amount']
            return jsonify({"status":"success"}),200
    return jsonify({"status":"error","message":"ไม่พบรายการหรืออนุมัติแล้ว"}),404

# Reset wallet daily at 00:00
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
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)))
