from flask import Flask, request, jsonify, render_template_string
import json
from datetime import datetime, date
from collections import defaultdict

app = Flask(__name__)

# ----------------- TrueWallet -----------------
transactions = []
daily_summary = defaultdict(float)

SECRET_KEY = "8d2909e5a59bc24bbf14059e9e591402"

# ----------------- Profit/LOSS -----------------
profit_history = []

# ----------------- Utils -----------------
def translate_event_type(event_type):
    mapping = {
        "P2P": "วอลเล็ตโอนเงิน",
        "MONEY_LINK": "รับจากซอง",
        "DIRECT_TOPUP": "เติมเงินร้านค้า/ธนาคาร",
        "PROMPTPAY_IN": "พร้อมเพย์",
        "TOPUP": "เติมเงิน",
        "PAYMENT": "จ่ายเงิน",
        "WITHDRAW": "ถอนเงิน"
    }
    return mapping.get(event_type, event_type)

# ----------------- Routes -----------------
@app.route("/")
def index():
    return render_template_string(DASHBOARD_HTML, profit_history=profit_history)

# Get transactions for dashboard
@app.route("/get_transactions")
def get_transactions():
    today_str = date.today().strftime("%Y-%m-%d")
    new_orders = [tx for tx in transactions if tx["status"]=="new"][-20:][::-1]
    approved_orders = [tx for tx in transactions if tx["status"]=="approved"][-20:][::-1]

    wallet_daily_total = sum(tx["amount"] for tx in transactions if tx["status"]=="approved" and tx["time"].strftime("%Y-%m-%d")==today_str)
    wallet_history = sum(tx["amount"] for tx in transactions if tx["status"]=="approved")

    # update daily_summary
    daily_summary.clear()
    for tx in transactions:
        if tx["status"]=="approved":
            day = tx["time"].strftime("%Y-%m-%d")
            daily_summary[day] += tx["amount"]

    for tx in new_orders + approved_orders:
        tx["time_str"] = tx["time"].strftime("%Y-%m-%d %H:%M:%S")
        tx["amount_str"] = f"{tx['amount']:,.2f}"

    daily_list = [{"date":d,"total":f"{v:,.2f}"} for d,v in sorted(daily_summary.items())]

    return jsonify({
        "new_orders": new_orders,
        "approved_orders": approved_orders,
        "wallet_daily_total": f"{wallet_daily_total:,.2f}",
        "wallet_history": f"{wallet_history:,.2f}",
        "daily_summary": daily_list
    })

@app.route("/approve", methods=["POST"])
def approve():
    txid = request.json.get("id")
    for tx in transactions:
        if tx["id"]==txid:
            tx["status"]="approved"
            tx["approved_by"]="System"  # สามารถแก้ให้เป็นชื่อผู้อนุมัติจริงได้
            break
    return jsonify({"status":"success"})

# TrueWallet webhook
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

        if not data:
            return jsonify({"status":"error","message":"No data"}), 400

        txid = data.get("transactionId") or f"TX{len(transactions)+1}"
        event_type = translate_event_type(data.get("event") or data.get("type") or "Unknown")
        try:
            amount = float(str(data.get("amount",0)).replace(",",""))
        except:
            amount = 0
        name = data.get("accountName") or data.get("name") or "-"
        bank = data.get("bankCode") or data.get("bank") or "-"
        status = str(data.get("status","new")).lower()
        now = datetime.now()

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
        return jsonify({"status":"success"}),200

    except Exception as e:
        return jsonify({"status":"error","message":str(e)}),500

# Profit calculation
@app.route("/calculate_profit", methods=["POST"])
def calculate_profit():
    data = request.json
    try:
        withdraw = float(data.get("withdraw",0))
        ezrich = float(data.get("EzRich",0))
        truewallet = float(data.get("TrueWallet",0))
        account = float(data.get("account",0))
        kingpay = float(data.get("KingPay",0))
        author = data.get("author","-")
        date_str = data.get("date",datetime.now().strftime("%d/%m/%Y"))

        total_income = ezrich + truewallet + account + kingpay
        profit = total_income - withdraw

        record = {
            "id": len(profit_history)+1,
            "date": date_str,
            "withdraw": withdraw,
            "EzRich": ezrich,
            "TrueWallet": truewallet,
            "account": account,
            "KingPay": kingpay,
            "profit": profit,
            "author": author
        }
        profit_history.append(record)
        return jsonify({"status":"success","record":record})
    except Exception as e:
        return jsonify({"status":"error","message":str(e)})

@app.route("/delete_profit/<int:id>", methods=["POST"])
def delete_profit(id):
    global profit_history
    profit_history = [r for r in profit_history if r["id"]!=id]
    return jsonify({"status":"success"})

# ----------------- HTML -----------------
DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>THKBot168 Dashboard</title>
    <style>
        body { font-family: Arial; padding:20px; background:#f0f2f5; }
        h1,h2 { text-align:center; }
        .scroll-box { max-height:400px; overflow-y:auto; margin-bottom:20px; background:white; border-radius:12px; }
        table { width:100%; border-collapse:collapse; margin-bottom:20px; }
        th,td { padding:10px; border:1px solid #ccc; text-align:center; }
        th { background:#007bff; color:white; position:sticky; top:0; z-index:2; }
        tr:hover { background:#f9f9f9; }
        button { padding:6px 12px; border:none; border-radius:6px; cursor:pointer; background:green; color:white; }
        input { width:80px; }
    </style>
</head>
<body>
<h1>THKBot168 Dashboard (Realtime)</h1>
<h2>วันที่-เวลา: <span id="current-datetime"></span></h2>
<h2>💰💰 ยอด Wallet วันนี้: <span id="wallet-info">0</span> บาท</h2>

<!-- New / Approved Orders -->
<h2>รายการใหม่ (New Orders)</h2>
<div class="scroll-box">
<table id="new-orders-table">
<thead>
<tr><th>Transaction ID</th><th>ประเภท</th><th>จำนวน</th><th>ชื่อ/เบอร์</th><th>เวลา</th><th>อนุมัติ</th></tr>
</thead><tbody></tbody>
</table>
</div>

<h2>รายการที่อนุมัติแล้ว (Approved Orders)</h2>
<div class="scroll-box">
<table id="approved-orders-table">
<thead>
<tr><th>Transaction ID</th><th>ประเภท</th><th>จำนวน</th><th>ชื่อ/เบอร์</th><th>เวลา</th><th>ผู้อนุมัติ</th></tr>
</thead><tbody></tbody>
</table>
</div>

<h2>ยอด Wallet รายวัน (Daily Summary)</h2>
<div class="scroll-box">
<table id="daily-summary-table">
<thead>
<tr><th>วันที่</th><th>ยอดรวม (บาท)</th></tr>
</thead><tbody></tbody>
</table>
</div>

<!-- Profit/Loss Section -->
<h2>คำนวณกำไร/ขาดทุนรายวัน</h2>
<div>
วันที่: <input type="text" id="date" placeholder="dd/mm/yyyy" value=""><br>
ชื่อผู้คิดยอด: <input type="text" id="author" placeholder="ชื่อผู้คิดยอด"><br>
เงินยื่นถอน: <input type="number" id="withdraw" value="0">
EzRich: <input type="number" id="EzRich" value="0">
True Wallet: <input type="number" id="TrueWallet" value="0">
บัญชี: <input type="number" id="account" value="0">
KingPay: <input type="number" id="KingPay" value="0">
<button onclick="calculateProfit()">คำนวณ</button>
</div>

<h2>ตารางสรุปกำไร/ขาดทุน</h2>
<table id="profit-table">
<thead>
<tr><th>วันที่</th><th>เงินยื่นถอน</th><th>EzRich</th><th>TrueWallet</th><th>บัญชี</th><th>KingPay</th><th>กำไร/ขาดทุน</th><th>ผู้คิดยอด</th><th>จัดการ</th></tr>
</thead>
<tbody>
{% for r in profit_history %}
<tr id="row-{{r.id}}">
<td>{{r.date}}</td><td>{{r.withdraw}}</td><td>{{r.EzRich}}</td><td>{{r.TrueWallet}}</td><td>{{r.account}}</td><td>{{r.KingPay}}</td><td>{{r.profit}}</td><td>{{r.author}}</td>
<td><button onclick="deleteProfit({{r.id}})">ลบ</button></td>
</tr>
{% endfor %}
</tbody>
</table>

<script>
function updateCurrentTime(){
    const now = new Date();
    const y=now.getFullYear(), m=String(now.getMonth()+1).padStart(2,'0'), d=String(now.getDate()).padStart(2,'0');
    const hh=String(now.getHours()).padStart(2,'0'), mm=String(now.getMinutes()).padStart(2,'0'), ss=String(now.getSeconds()).padStart(2,'0');
    document.getElementById("current-datetime").innerText=`${y}-${m}-${d} ${hh}:${mm}:${ss}`;
}
setInterval(updateCurrentTime,1000);updateCurrentTime();

// Fetch transactions
async function fetchTransactions(){
    try{
        let resp = await fetch("/get_transactions");
        let data = await resp.json();
        document.getElementById("wallet-info").innerText = data.wallet_daily_total;

        // New orders
        let newT = document.querySelector("#new-orders-table tbody"); newT.innerHTML="";
        data.new_orders.forEach(tx=>{
            let row=newT.insertRow();
            row.insertCell(0).innerText=tx.id;
            row.insertCell(1).innerText=tx.event;
            row.insertCell(2).innerText=tx.amount_str;
            row.insertCell(3).innerText=tx.name;
            row.insertCell(4).innerText=tx.time_str;
            let btn=row.insertCell(5); let b=document.createElement("button");
            b.innerText="อนุมัติ";
            b.onclick=async ()=>{
                await fetch("/approve",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:tx.id})});
                fetchTransactions();
            }; btn.appendChild(b);
        });

        // Approved orders
        let aT=document.querySelector("#approved-orders-table tbody"); aT.innerHTML="";
        data.approved_orders.forEach(tx=>{
            let row=aT.insertRow();
            row.insertCell(0).innerText=tx.id;
            row.insertCell(1).innerText=tx.event;
            row.insertCell(2).innerText=tx.amount_str;
            row.insertCell(3).innerText=tx.name;
            row.insertCell(4).innerText=tx.time_str;
            row.insertCell(5).innerText=tx.approved_by || "System";
        });

        // Daily summary
        let dT=document.querySelector("#daily-summary-table tbody"); dT.innerHTML="";
        data.daily_summary.forEach(day=>{
            let row=dT.insertRow();
            row.insertCell(0).innerText=day.date;
            row.insertCell(1).innerText=day.total;
        });

    }catch(e){console.error(e);}
}
setInterval(fetchTransactions,3000); fetchTransactions();

// Profit functions
function calculateProfit(){
    let data={
        date: document.getElementById("date").value,
        author: document.getElementById("author").value,
        withdraw: parseFloat(document.getElementById("withdraw").value),
        EzRich: parseFloat(document.getElementById("EzRich").value),
        TrueWallet: parseFloat(document.getElementById("TrueWallet").value),
        account: parseFloat(document.getElementById("account").value),
        KingPay: parseFloat(document.getElementById("KingPay").value)
    };
    fetch("/calculate_profit",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)})
    .then(r=>r.json()).then(res=>{
        if(res.status=="success") addProfitRow(res.record); else alert(res.message);
    });
}

function addProfitRow(r){
    let tbody=document.querySelector("#profit-table tbody");
    let row=document.createElement("tr"); row.id="row-"+r.id;
    row.innerHTML=`<td>${r.date}</td><td>${r.withdraw}</td><td>${r.EzRich}</td><td>${r.TrueWallet}</td><td>${r.account}</td><td>${r.KingPay}</td><td>${r.profit}</td><td>${r.author}</td><td><button onclick="deleteProfit(${r.id})">ลบ</button></td>`;
    tbody.appendChild(row);
}

function deleteProfit(id){
    fetch("/delete_profit/"+id,{method:"POST"}).then(r=>r.json()).then(res=>{
        if(res.status=="success"){ document.getElementById("row-"+id).remove(); }
    });
}
</script>
</body>
</html>
"""

if __name__=="__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
