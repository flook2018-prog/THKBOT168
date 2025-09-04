from flask import Flask, request, jsonify, render_template_string
import os

app = Flask(__name__)

transactions = []  # {"id":.., "event":.., "amount":.., "name":.., "bank":.., "status":..}

def translate_event_type(event_type):
    mapping = {
        "P2P": "วอลเล็ตโอนเงิน",
        "TOPUP": "เติมเงิน",
        "PAYMENT": "จ่ายเงิน",
        "WITHDRAW": "ถอนเงิน"
    }
    return mapping.get(event_type, event_type)

# หน้า Dashboard
@app.route("/")
def index():
    latest_tx = transactions[-10:][::-1]  # แสดง 10 รายการล่าสุด
    return render_template_string(DASHBOARD_HTML, transactions=latest_tx)

# อัปเดตสถานะ
@app.route("/update_status", methods=["POST"])
def update_status():
    idx = int(request.form.get("index", -1))
    new_status = request.form.get("status")
    if 0 <= idx < len(transactions):
        transactions[idx]["status"] = new_status
        print(f"[UPDATE STATUS] {transactions[idx]['id']} -> {new_status}")
    return ("", 204)

# Webhook TrueWallet
@app.route("/truewallet/webhook", methods=["POST"])
def webhook():
    try:
        data = request.json
        if not data:
            print("[WEBHOOK ERROR] ไม่มีข้อมูล JSON")
            return jsonify({"status": "error", "message": "ไม่มีข้อมูล JSON"}), 400

        txid = data.get("transactionId", f"TX{len(transactions)+1}")
        event_type = translate_event_type(data.get("event", "Unknown"))
        amount = data.get("amount", 0)
        name = data.get("accountName", "-")
        bank = data.get("bankCode", "-")
        status = data.get("status", "new")

        tx = {
            "id": txid,
            "event": event_type,
            "amount": amount,
            "name": name,
            "bank": bank,
            "status": status.lower()
        }
        transactions.append(tx)

        # log ลง console
        print("[WEBHOOK RECEIVED] Raw Data:", data)
        print("[WEBHOOK PARSED] Stored Transaction:", tx)

        return jsonify({"status": "success"}), 200

    except Exception as e:
        print("[WEBHOOK EXCEPTION]", e)
        # ป้องกัน 502 → ตอบกลับแม้ error
        return jsonify({"status": "error", "message": str(e)}), 200


# ================== HTML ==================

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>THKBot168 Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; padding: 20px; background: #f0f2f5; }
        h1 { text-align: center; }
        input[type="text"] { width: 100%; padding: 10px; margin-bottom: 15px; border-radius: 8px; border: 1px solid #ccc; }
        table { width: 100%; border-collapse: collapse; background: white; border-radius: 12px; overflow: hidden; }
        th, td { padding: 14px; border-bottom: 1px solid #eee; text-align: center; }
        th { background: #007bff; color: white; }
        tr:hover { background-color: #f9f9f9; }
        .status-new { color: orange; font-weight: bold; }
        .status-approved { color: green; font-weight: bold; }
        .status-rejected { color: red; font-weight: bold; }
        .scroll-box { max-height: 400px; overflow-y: auto; }
        button { padding: 6px 12px; border: none; border-radius: 6px; cursor: pointer; }
        .approve { background: green; color: white; }
        .reject { background: red; color: white; }
    </style>
    <script>
        function filterTable() {
            let input = document.getElementById("searchInput").value.toLowerCase();
            let rows = document.getElementById("txTable").getElementsByTagName("tr");
            for (let i=1; i<rows.length; i++) {
                let cells = rows[i].getElementsByTagName("td");
                let match = false;
                for (let j=0; j<cells.length; j++) {
                    if (cells[j].innerText.toLowerCase().includes(input)) {
                        match = true; break;
                    }
                }
                rows[i].style.display = match ? "" : "none";
            }
        }
    </script>
</head>
<body>
    <h1>THKBot168 Dashboard</h1>
    <input type="text" id="searchInput" onkeyup="filterTable()" placeholder="🔍 ค้นหารายการ...">
    <div class="scroll-box">
    <table id="txTable">
        <tr>
            <th>รหัสธุรกรรม</th>
            <th>ประเภท</th>
            <th>จำนวน</th>
            <th>ชื่อบัญชี</th>
            <th>ธนาคาร</th>
            <th>สถานะ</th>
            <th>จัดการ</th>
        </tr>
        {% for tx in transactions %}
        <tr>
            <td>{{ tx.id }}</td>
            <td>{{ tx.event }}</td>
            <td>{{ tx.amount }} บาท</td>
            <td>{{ tx.name }}</td>
            <td>{{ tx.bank }}</td>
            <td class="status-{{ tx.status }}">{{ tx.status|capitalize }}</td>
            <td>
                <form method="POST" action="/update_status" style="display:inline;">
                    <input type="hidden" name="index" value="{{ loop.index0 }}">
                    <button type="submit" name="status" value="approved" class="approve">อนุมัติ</button>
                    <button type="submit" name="status" value="rejected" class="reject">ปฏิเสธ</button>
                </form>
            </td>
        </tr>
        {% endfor %}
    </table>
    </div>
</body>
</html>
"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
