from flask import Flask, request, jsonify, render_template_string
import os, json, jwt, random
from datetime import datetime, date
from collections import defaultdict

app = Flask(__name__)

transactions = []
daily_summary = defaultdict(float)
ip_approver_map = {}

LOG_FILE = "transactions.log"
SECRET_KEY = "8d2909e5a59bc24bbf14059e9e591402"

def translate_event_type(event_type):
    mapping = {
        "P2P": "วอลเล็ตโอนเงิน",
        "MONEY_LINK": "รับจากซองทรูมันนี่",
        "DIRECT_TOPUP": "เติมเงินร้านค้า/ธนาคาร",
        "PROMPTPAY_IN": "เติมเงินพร้อมเพย์"
    }
    return mapping.get(event_type, event_type)

def translate_bank(bank_code):
    mapping = {
        "BBL": "ธนาคารกรุงเทพ",
        "KBANK": "ธนาคารกสิกร",
        "SCB": "ธนาคารไทยพาณิชย์",
        "KTB": "ธนาคารกรุงไทย",
        "TMB": "ธนาคารทหารไทย",
        "GSB": "ธนาคารออมสิน",
        "TRUEWALLET": "TrueWallet",
        "PROMPTPAY": "พร้อมเพย์"
    }
    return mapping.get(bank_code.upper(), bank_code)

def log_with_time(*args):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    msg = f"[{ts}] " + " ".join(str(a) for a in args)
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

def random_english_name():
    first_names = ["Alice","Bob","Charlie","David","Eve","Frank","Grace","Hannah","Ian","Jack","Kathy","Leo","Mia","Nina","Oscar"]
    return random.choice(first_names)

# ================== Dashboard ==================
@app.route("/")
def index():
    return render_template_string(DASHBOARD_HTML)

@app.route("/get_transactions")
def get_transactions():
    today_str = date.today().strftime("%Y-%m-%d")
    transactions[:] = [tx for tx in transactions if not (tx["status"]=="approved" and tx["time"].strftime("%Y-%m-%d") < today_str)]

    new_orders = [tx for tx in transactions if tx["status"] == "new"][-20:][::-1]
    approved_orders = [tx for tx in transactions if tx["status"] == "approved"][-20:][::-1]

    wallet_daily_total = sum(tx["amount"] for tx in transactions if tx["status"]=="approved" and tx["time"].strftime("%Y-%m-%d")==today_str)

    daily_summary.clear()
    for tx in transactions:
        if tx["status"]=="approved":
            day = tx["time"].strftime("%Y-%m-%d")
            daily_summary[day] += tx["amount"]

    for tx in new_orders + approved_orders:
        tx["time_str"] = tx["time"].strftime("%Y-%m-%d %H:%M:%S")
        tx["amount_str"] = f"{tx['amount']:,.2f}"
        tx["bank_name"] = translate_bank(tx.get("bank",""))
        tx["approver_name"] = tx.get("approver_name", "")

    daily_list = [{"date": d, "total": f"{v:,.2f}"} for d,v in sorted(daily_summary.items())]

    return jsonify({
        "new_orders": new_orders,
        "approved_orders": approved_orders,
        "wallet_daily_total": f"{wallet_daily_total:,.2f}",
        "daily_summary": daily_list
    })

@app.route("/approve", methods=["POST"])
def approve():
    txid = request.json.get("id")
    user_ip = request.remote_addr or "unknown"

    if user_ip not in ip_approver_map:
        ip_approver_map[user_ip] = random_english_name()
    approver_name = ip_approver_map[user_ip]

    for tx in transactions:
        if tx["id"] == txid:
            tx["status"] = "approved"
            tx["approver_name"] = approver_name
            log_with_time(f"[UPDATE STATUS] {txid} -> approved by {approver_name} ({user_ip})")
            break
    return jsonify({"status": "success"}), 200

@app.route("/truewallet/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True)
        if not data or "message" not in data:
            log_with_time("[WEBHOOK ERROR] ไม่มี field message")
            return jsonify({"status":"error","message":"No message"}), 400

        token = data["message"]
        try:
            decoded = jwt.decode(token, SECRET_KEY, algorithms=["HS256"], options={"verify_iat": False})
        except jwt.InvalidTokenError as e:
            log_with_time("[WEBHOOK ERROR] Invalid JWT", e)
            return jsonify({"status":"invalid","message":str(e)}), 400

        txid = decoded.get("transaction_id") or f"TX{len(transactions)+1}"
        event_type = translate_event_type(decoded.get("event_type", "Unknown"))
        amount = int(decoded.get("amount", 0))/100
        sender_name = decoded.get("sender_name","-")
        sender_mobile = decoded.get("sender_mobile","-")
        name = f"{sender_name} / {sender_mobile}" if sender_mobile else sender_name
        bank_code = decoded.get("channel","-")

        # ใช้เวลาอิงจาก JSON
        time_str = decoded.get("created_at") or decoded.get("time")
        try:
            if time_str:
                if "T" in time_str:
                    tx_time = datetime.strptime(time_str,"%Y-%m-%dT%H:%M:%S")
                else:
                    tx_time = datetime.strptime(time_str,"%Y-%m-%d %H:%M:%S")
            else:
                tx_time = datetime.now()
        except:
            tx_time = datetime.now()

        tx = {
            "id": txid,
            "event": event_type,
            "amount": amount,
            "name": name,
            "bank": bank_code,
            "status": "new",
            "time": tx_time
        }

        transactions.append(tx)
        log_with_time("[WEBHOOK RECEIVED]", tx)
        return jsonify({"status":"success"}), 200

    except Exception as e:
        log_with_time("[WEBHOOK EXCEPTION]", e)
        return jsonify({"status":"error","message":str(e)}), 500

# ================== HTML Dashboard ==================
DASHBOARD_HTML = """  
<!DOCTYPE html>
<html>
<head>
<title>THKBot168 Dashboard</title>
<style>
body{font-family:'Segoe UI',sans-serif;background:#f0f2f5;margin:0;padding:20px;color:#333}
h1,h2{text-align:center;margin-bottom:15px}
.scroll-box{max-height:400px;overflow-y:auto;margin-bottom:25px;background:#fff;border-radius:12px;box-shadow:0 4px 12px rgba(0,0,0,0.08);padding:10px;scroll-behavior:smooth}
table{width:100%;border-collapse:collapse}
th,td{padding:12px;text-align:center}
th{position:sticky;top:0;z-index:2;background:linear-gradient(90deg,#4a90e2,#007bff);color:white;box-shadow:0 2px 5px rgba(0,0,0,0.1)}
tr:hover{background-color:#f1f5f9;transition:0.3s}
button{padding:6px 12px;border:none;border-radius:6px;cursor:pointer;background:#28a745;color:white;transition:0.3s}
button:hover{background:#218838;transform:scale(1.05)}
::-webkit-scrollbar{width:8px}
::-webkit-scrollbar-thumb{background-color:rgba(0,0,0,0.2);border-radius:4px}
::-webkit-scrollbar-track{background:transparent}
</style>
</head>
<body>
<h1>THKBot168 Dashboard (Realtime)</h1>
<h2>วันที่-เวลา: <span id="current-datetime"></span></h2>
<h2>💰 ยอด Wallet วันนี้: <span id="wallet-info">0</span> บาท</h2>

<h2>รายการใหม่ (New Orders)</h2>
<div class="scroll-box">
<table id="new-orders-table">
<thead>
<tr>
<th>Transaction ID</th>
<th>ประเภท</th>
<th>จำนวน</th>
<th>ชื่อ/เบอร์</th>
<th>เวลา</th>
<th>ธนาคาร</th>
<th>อนุมัติ</th>
</tr>
</thead>
<tbody></tbody>
</table>
</div>

<h2>รายการที่อนุมัติแล้ว (Approved Orders)</h2>
<div class="scroll-box">
<table id="approved-orders-table">
<thead>
<tr>
<th>Transaction ID</th>
<th>ประเภท</th>
<th>จำนวน</th>
<th>ชื่อ/เบอร์</th>
<th>เวลา</th>
<th>ธนาคาร</th>
<th>ผู้อนุมัติ</th>
</tr>
</thead>
<tbody></tbody>
</table>
</div>

<h2>ยอด Wallet รายวัน</h2>
<div class="scroll-box">
<table id="daily-summary-table">
<thead>
<tr>
<th>วันที่</th>
<th>ยอดรวม (บาท)</th>
</tr>
</thead>
<tbody></tbody>
</table>
</div>

<script>
function updateCurrentTime(){document.getElementById("current-datetime").innerText=new Date().toLocaleString('en-GB',{hour12:false})}
setInterval(updateCurrentTime,1000);updateCurrentTime();

async function fetchTransactions(){
try{
let resp=await fetch("/get_transactions");let data=await resp.json();
document.getElementById("wallet-info").innerText=data.wallet_daily_total;

let newTableBody=document.querySelector("#new-orders-table tbody");newTableBody.innerHTML="";
data.new_orders.forEach(tx=>{
let row=newTableBody.insertRow();
row.insertCell(0).innerText=tx.id;
row.insertCell(1).innerText=tx.event;
row.insertCell(2).innerText=tx.amount_str;
row.insertCell(3).innerText=tx.name;
row.insertCell(4).innerText=tx.time_str;
row.insertCell(5).innerText=tx.bank_name;
let btnCell=row.insertCell(6);
let btn=document.createElement("button");
btn.innerText="อนุมัติ";
btn.onclick=async ()=>{
await fetch("/approve",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:tx.id})});
fetchTransactions();
};
btnCell.appendChild(btn);
});

let approvedTableBody=document.querySelector("#approved-orders-table tbody");approvedTableBody.innerHTML="";
data.approved_orders.forEach(tx=>{
let row=approvedTableBody.insertRow();
row.insertCell(0).innerText=tx.id;
row.insertCell(1).innerText=tx.event;
row.insertCell(2).innerText=tx.amount_str;
row.insertCell(3).innerText=tx.name;
row.insertCell(4).innerText=tx.time_str;
row.insertCell(5).innerText=tx.bank_name;
row.insertCell(6).innerText=tx.approver_name;
});

let dailyTableBody=document.querySelector("#daily-summary-table tbody");dailyTableBody.innerHTML="";
data.daily_summary.forEach(day=>{
let row=dailyTableBody.insertRow();
row.insertCell(0).innerText=day.date;
row.insertCell(1).innerText=day.total;
});

}catch(e){console.error("Error fetching transactions:",e)}
}
setInterval(fetchTransactions,3000);
fetchTransactions();
</script>
</body>
</html>
"""

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)))
