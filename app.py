from flask import Flask, request, jsonify, render_template_string
import os
from datetime import datetime, date

app = Flask(__name__)

transactions = []  # {"id":.., "event":.., "amount":.., "name":.., "bank":.., "status":.., "time":..}

LOG_FILE = "transactions.log"

def translate_event_type(event_type):
    mapping = {
        "P2P": "วอลเล็ตโอนเงิน",
        "TOPUP": "เติมเงิน",
        "PAYMENT": "จ่ายเงิน",
        "WITHDRAW": "ถอนเงิน"
    }
    return mapping.get(event_type, event_type)

def log_with_time(*args):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    msg = f"[{ts}] " + " ".join(str(a) for a in args)
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

# ================== Dashboard ==================
@app.route("/")
def index():
    return render_template_string(DASHBOARD_HTML)

@app.route("/get_transactions")
def get_transactions():
    today_str = date.today().strftime("%Y-%m-%d")
    new_orders = [tx for tx in transactions if tx["status"] == "new"][-20:][::-1]
    approved_orders = [tx for tx in transactions if tx["status"] == "approved"][-20:][::-1]

    wallet_daily_total = sum(tx["amount"] for tx in transactions
                             if tx["status"] == "approved" and tx["time"].strftime("%Y-%m-%d") == today_str)
    wallet_history = sum(tx["amount"] for tx in transactions if tx["status"] == "approved")

    for tx in new_orders + approved_orders:
        tx["time_str"] = tx["time"].strftime("%Y-%m-%d %H:%M:%S")

    return jsonify({
        "new_orders": new_orders,
        "approved_orders": approved_orders,
        "wallet_daily_total": wallet_daily_total,
        "wallet_history": wallet_history
    })

@app.route("/approve", methods=["POST"])
def approve():
    txid = request.json.get("id")
    for tx in transactions:
        if tx["id"] == txid:
            tx["status"] = "approved"
            log_with_time(f"[UPDATE STATUS] {txid} -> approved")
            break
    return jsonify({"status": "success"}), 200

@app.route("/truewallet/webhook", methods=["POST"])
def webhook():
    try:
        data = request.json
        if not data:
            log_with_time("[WEBHOOK ERROR] ไม่มีข้อมูล JSON")
            return jsonify({"status": "error", "message": "ไม่มีข้อมูล JSON"}), 400

        txid = data.get("transactionId", f"TX{len(transactions)+1}")
        event_type = translate_event_type(data.get("event", "Unknown"))
        amount = data.get("amount", 0)
        name = data.get("accountName", "-")
        bank = data.get("bankCode", "-")
        status = data.get("status", "new")
        now = datetime.now()

        tx = {
            "id": txid,
            "event": event_type,
            "amount": amount,
            "name": name,
            "bank": bank,
            "status": status.lower(),
            "time": now
        }
        transactions.append(tx)

        log_with_time("[WEBHOOK RECEIVED] Raw Data:", data)
        log_with_time("[WEBHOOK PARSED] Stored Transaction:", tx)

        return jsonify({"status": "success"}), 200

    except Exception as e:
        log_with_time("[WEBHOOK EXCEPTION]", e)
        return jsonify({"status": "error", "message": str(e)}), 200

# ================== HTML ==================
DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>THKBot168 Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; padding: 20px; background: #f0f2f5; }
        h1, h2 { text-align: center; }
        table { width: 100%; border-collapse: collapse; margin-bottom: 20px; background: white; border-radius: 12px; overflow: hidden; }
        th, td { padding: 12px; border-bottom: 1px solid #eee; text-align: center; }
        th { background: #007bff; color: white; }
        tr:hover { background-color: #f9f9f9; }
        .scroll-box { max-height: 400px; overflow-y: auto; margin-bottom: 20px; }
        button { padding: 6px 12px; border: none; border-radius: 6px; cursor: pointer; background: green; color: white; }
        .status-new { color: orange; font-weight: bold; }
        .status-approved { color: green; font-weight: bold; }
    </style>
</head>
<body>
    <h1>THKBot168 Dashboard (Realtime)</h1>
    <h2 id="wallet-info">ยอด Wallet วันนี้: 0 บาท | ย้อนหลัง: 0 บาท</h2>

    <h2>รายการใหม่ (New Orders)</h2>
    <div class="scroll-box">
        <table id="new-orders-table">
            <tr>
                <th>Transaction ID</th>
                <th>ประเภท</th>
                <th>จำนวน</th>
                <th>ชื่อ/เบอร์</th>
                <th>เวลา</th>
                <th>อนุมัติ</th>
            </tr>
        </table>
    </div>

    <h2>รายการที่อนุมัติแล้ว (Approved Orders)</h2>
    <div class="scroll-box">
        <table id="approved-orders-table">
            <tr>
                <th>Transaction ID</th>
                <th>ประเภท</th>
                <th>จำนวน</th>
                <th>ชื่อ/เบอร์</th>
                <th>เวลา</th>
            </tr>
        </table>
    </div>

<script>
async function fetchTransactions(){
    try{
        let resp = await fetch("/get_transactions");
        let data = await resp.json();

        // Update wallet info
        document.getElementById("wallet-info").innerText =
            `ยอด Wallet วันนี้: ${data.wallet_daily_total} บาท | ย้อนหลัง: ${data.wallet_history} บาท`;

        // Update new orders table
        let newTable = document.getElementById("new-orders-table");
        newTable.innerHTML = `<tr>
            <th>Transaction ID</th>
            <th>ประเภท</th>
            <th>จำนวน</th>
            <th>ชื่อ/เบอร์</th>
            <th>เวลา</th>
            <th>อนุมัติ</th>
        </tr>`;
        data.new_orders.forEach(tx => {
            let row = newTable.insertRow();
            row.insertCell(0).innerText = tx.id;
            row.insertCell(1).innerText = tx.event;
            row.insertCell(2).innerText = tx.amount;
            row.insertCell(3).innerText = tx.name;
            row.insertCell(4).innerText = tx.time_str;
            row.className = "status-new";
            let btnCell = row.insertCell(5);
            let btn = document.createElement("button");
            btn.innerText = "อนุมัติ";
            btn.onclick = async ()=> {
                await fetch("/approve", {
                    method:"POST",
                    headers:{"Content-Type":"application/json"},
                    body: JSON.stringify({id: tx.id})
                });
                fetchTransactions(); // refresh table
            };
            btnCell.appendChild(btn);
        });

        // Update approved orders table
        let approvedTable = document.getElementById("approved-orders-table");
        approvedTable.innerHTML = `<tr>
            <th>Transaction ID</th>
            <th>ประเภท</th>
            <th>จำนวน</th>
            <th>ชื่อ/เบอร์</th>
            <th>เวลา</th>
        </tr>`;
        data.approved_orders.forEach(tx => {
            let row = approvedTable.insertRow();
            row.insertCell(0).innerText = tx.id;
            row.insertCell(1).innerText = tx.event;
            row.insertCell(2).innerText = tx.amount;
            row.insertCell(3).innerText = tx.name;
            row.insertCell(4).innerText = tx.time_str;
            row.className = "status-approved";
        });

    } catch(e){
        console.error("Error fetching transactions:", e);
    }
}

// fetch ทุก 3 วินาที
setInterval(fetchTransactions, 3000);
fetchTransactions(); // fetch ครั้งแรกตอนโหลด
</script>
</body>
</html>
"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
