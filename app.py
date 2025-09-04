from flask import Flask, request, jsonify, render_template_string
import os, json, jwt, random
from datetime import datetime, date
from collections import defaultdict
import threading, time

app = Flask(__name__)

transactions = []  # เก็บรายการทั้งหมด
daily_summary = defaultdict(float)  # เก็บยอดรวมต่อวัน {"YYYY-MM-DD": total_amount}
ip_approver_map = {}  # เก็บ IP -> ชื่อผู้อนุมัติ

LOG_FILE = "transactions.log"
SECRET_KEY = "8d2909e5a59bc24bbf14059e9e591402"
APPROVER_FILE = "approvers.json"

# โหลดชื่อผู้อนุมัติจากไฟล์
if os.path.exists(APPROVER_FILE):
    with open(APPROVER_FILE, "r", encoding="utf-8") as f:
        ip_approver_map = json.load(f)

def save_approvers():
    with open(APPROVER_FILE, "w", encoding="utf-8") as f:
        json.dump(ip_approver_map, f, ensure_ascii=False, indent=2)

# แปลงประเภทเหตุการณ์
def translate_event_type(event_type):
    mapping = {
        "P2P": "วอลเล็ตโอนเงิน",
        "MONEY_LINK": "รับจากซองทรูมันนี่",
        "DIRECT_TOPUP": "เติมเงินร้านค้า/ธนาคาร",
        "PROMPTPAY_IN": "เติมเงินพร้อมเพย์"
    }
    return mapping.get(event_type, event_type)

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
    new_orders = [tx for tx in transactions if tx["status"] == "new"][-20:][::-1]
    approved_orders = [tx for tx in transactions if tx["status"] == "approved"][-20:][::-1]

    # อัปเดต daily_summary
    daily_summary.clear()
    for tx in transactions:
        if tx["status"] == "approved":
            day = tx["time"].strftime("%Y-%m-%d")
            daily_summary[day] += tx["amount"]

    # format transactions
    for tx in new_orders + approved_orders:
        tx["time_str"] = tx["time"].strftime("%Y-%m-%d %H:%M:%S")
        tx["amount_str"] = f"{tx['amount']:,.2f}"
        tx["approver_name"] = tx.get("approver_name", "")

    daily_list = [{"date": d, "total": f"{v:,.2f}"} for d, v in sorted(daily_summary.items())]

    # ยอด Wallet วันนี้
    wallet_daily_total = sum(
        tx["amount"] for tx in transactions
        if tx["status"] == "approved" and
           tx["time"].strftime("%Y-%m-%d") == today_str
    )

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
        save_approvers()
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
        data = None
        if request.is_json:
            data = request.get_json()
        elif request.form:
            data = request.form.to_dict()
        elif request.data:
            try:
                data = json.loads(request.data.decode("utf-8"))
            except:
                data = {}

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
        amount = int(decoded.get("amount", 0)) / 100
        sender_name = decoded.get("sender_name") or "-"
        sender_mobile = decoded.get("sender_mobile") or "-"
        name = f"{sender_name} / {sender_mobile}" if sender_mobile else sender_name
        bank = decoded.get("channel") or "-"
        # ใช้เวลาจากข้อมูลลูกค้า หากไม่มีใช้เวลาปัจจุบัน
        ts_str = decoded.get("time")  # รูปแบบ "YYYY-MM-DD HH:MM:SS"
        if ts_str:
            try:
                now = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
            except:
                now = datetime.now()
        else:
            now = datetime.now()
        status = "new"

        tx = {
            "id": txid,
            "event": event_type,
            "amount": amount,
            "name": name,
            "bank": bank,
            "status": status,
            "time": now
        }
        transactions.append(tx)
        log_with_time("[WEBHOOK RECEIVED]", tx)
        return jsonify({"status":"success"}), 200

    except Exception as e:
        log_with_time("[WEBHOOK EXCEPTION]", e)
        return jsonify({"status":"error","message":str(e)}), 500

# ================== ลบรายการอนุมัติทุก 00:00 ==================
def clear_approved_daily():
    while True:
        now = datetime.now()
        if now.hour == 0 and now.minute == 0:
            global transactions
            transactions = [tx for tx in transactions if tx["status"] != "approved"]
            log_with_time("[DAILY CLEAR] ลบรายการอนุมัติทั้งหมด")
            time.sleep(60)
        else:
            time.sleep(30)

threading.Thread(target=clear_approved_daily, daemon=True).start()

# ================== HTML ==================
DASHBOARD_HTML = """  
<!DOCTYPE html>
<html>
<head>
<title>THKBot168 Dashboard</title>
<style>
body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f0f2f5; margin:0; padding:20px; color:#333;}
h1,h2{text-align:center;margin-bottom:15px;}
.scroll-box{max-height:400px;overflow-y:auto;margin-bottom:25px;background:#fff;border-radius:12px;box-shadow:0 4px 12px rgba(0,0,0,0.08);padding:10px;scroll-behavior:smooth;}
table{width:100%;border-collapse:collapse;}
th,td{padding:12px;text-align:center;}
th{position:sticky;top:0;z-index:2;background:linear-gradient(90deg,#4a90e2,#007bff);color:white;box-shadow:0 2px 5px rgba(0,0,0,0.1);}
tr:hover{background-color:#f1f5f9;transition:background 0.3s;}
button{padding:6px 12px;border:none;border-radius:6px;cursor:pointer;background:#28a745;color:white;transition:all 0.3s ease;}
button:hover{background:#218838;transform:scale(1.05);}
::-webkit-scrollbar{width:8px;}
::-webkit-scrollbar-thumb{background-color:rgba(0,0,0,0.2);border-radius:4px;}
::-webkit-scrollbar-track{background:transparent;}
</style>
</head>
<body>
<h1>THKBot168 Dashboard (Realtime)</h1>
<h2>วันที่-เวลา: <span id="current-datetime"></span></h2>
<h2><span id="wallet-info">0 บาท</span></h2>

<h2>รายการใหม่ (New Orders)</h2>
<div class="scroll-box">
<table id="new-orders-table">
<thead>
<tr><th>Transaction ID</th><th>ประเภท</th><th>จำนวน</th><th>ชื่อ/เบอร์</th><th>เวลา</th><th>อนุมัติ</th></tr>
</thead>
<tbody></tbody>
</table>
</div>

<h2>รายการที่อนุมัติแล้ว (Approved Orders)</h2>
<div class="scroll-box">
<table id="approved-orders-table">
<thead>
<tr><th>Transaction ID</th><th>ประเภท</th><th>จำนวน</th><th>ชื่อ/เบอร์</th><th>เวลา</th><th>ผู้อนุมัติ</th></tr>
</thead>
<tbody></tbody>
</table>
</div>

<h2>ยอดรวมรายวัน</h2>
<div class="scroll-box">
<table id="daily-summary-table">
<thead><tr><th>วันที่</th><th>ยอดรวม (บาท)</th></tr></thead>
<tbody></tbody>
</table>
</div>

<script>
function updateCurrentTime(){
    const now=new Date();
    const y=now.getFullYear();
    const m=String(now.getMonth()+1).padStart(2,'0');
    const d=String(now.getDate()).padStart(2,'0');
    const hh=String(now.getHours()).padStart(2,'0');
    const mm=String(now.getMinutes()).padStart(2,'0');
    const ss=String(now.getSeconds()).padStart(2,'0');
    document.getElementById("current-datetime").innerText=`${y}-${m}-${d} ${hh}:${mm}:${ss}`;
}
setInterval(updateCurrentTime,1000);updateCurrentTime();

async function fetchTransactions(){
try{
let resp=await fetch("/get_transactions");
let data=await resp.json();
document.getElementById("wallet-info").innerText=`💰💰 ยอด Wallet วันนี้: ${data.wallet_daily_total} บาท`;

// New orders
let newTableBody=document.querySelector("#new-orders-table tbody");newTableBody.innerHTML="";
data.new_orders.forEach(tx=>{
let row=newTableBody.insertRow();
row.insertCell(0).innerText=tx.id;
row.insertCell(1).innerText=tx.event;
row.insertCell(2).innerText=tx.amount_str;
row.insertCell(3).innerText=tx.name;
row.insertCell(4).innerText=tx.time_str;
let btnCell=row.insertCell(5);
let btn=document.createElement("button");
btn.innerText="อนุมัติ";
btn.onclick=async()=>{
await fetch("/approve",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:tx.id})});
fetchTransactions();};
btnCell.appendChild(btn);
});

// Approved orders
let approvedTableBody=document.querySelector("#approved-orders-table tbody");approvedTableBody.innerHTML="";
data.approved_orders.forEach(tx=>{
let row=approvedTableBody.insertRow();
row.insertCell(0).innerText=tx.id;
row.insertCell(1).innerText=tx.event;
row.insertCell(2).innerText=tx.amount_str;
row.insertCell(3).innerText=tx.name;
row.insertCell(4).innerText=tx.time_str;
row.insertCell(5).innerText=tx.approver_name;
});

// Daily summary
let dailyTableBody=document.querySelector("#daily-summary-table tbody");dailyTableBody.innerHTML="";
data.daily_summary.forEach(day=>{
let row=dailyTableBody.insertRow();
row.insertCell(0).innerText=day.date;
row.insertCell(1).innerText=day.total;
});

}catch(e){console.error("Error fetching transactions:",e);}
}
setInterval(fetchTransactions,3000);
fetchTransactions();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)))
