from flask import Flask, request, jsonify, render_template_string
import os
from datetime import datetime

app = Flask(__name__)

SECRET_KEY = os.environ.get("SECRET_KEY", "local_dev_secret")

# เก็บรายการเป็น dict
transactions = []

def translate_event_type(event_type, bank_code=None):
    # Wallet / Topup / Payment
    if event_type in ["P2P", "TOPUP"]:
        return "วอลเล็ต"
    elif event_type == "PAYMENT":
        return "ชำระเงิน"
    # ธนาคาร
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
            # เพิ่มธนาคารอื่นได้ตามต้องการ
        }
        return bank_mapping.get(bank_code, "ไม่ระบุธนาคาร")
    else:
        return "อื่น ๆ"

@app.route("/")
def index():
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>THKBot168 Dashboard</title>
        <style>
            body { font-family: Arial, sans-serif; padding: 20px; background: #f0f2f5; }
            h1 { text-align: center; }
            input[type="text"] { width: 100%; padding: 8px; margin-bottom: 10px; }
            table { width: 100%; border-collapse: collapse; background: white; }
            th, td { padding: 12px; border-bottom: 1px solid #ddd; text-align: left; }
            tr:hover { background-color: #f1f1f1; }
            .status-new { color: orange; font-weight: bold; }
            .status-approved { color: green; font-weight: bold; }
            .status-rejected { color: red; font-weight: bold; }
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
            setTimeout(() => { window.location.reload(); }, 5000); // auto-refresh ทุก 5 วิ
        </script>
    </head>
    <body>
        <h1>THKBot168 Dashboard</h1>
        <input type="text" id="searchInput" onkeyup="filterTable()" placeholder="ค้นหารายการ...">
        <table id="txTable">
            <tr>
                <th>Transaction ID</th>
                <th>ประเภท</th>
                <th>จำนวน</th>
                <th>ชื่อ / เบอร์</th>
                <th>เวลา</th>
                <th>สถานะ</th>
            </tr>
            {% for tx in transactions %}
            <tr>
                <td>{{ tx.txid }}</td>
                <td>{{ tx.event }}</td>
                <td>{{ "%.2f"|format(tx.amount) }}</td>
                <td>{{ tx.name_phone }}</td>
                <td>{{ tx.time }}</td>
                <td class="status-{{ tx.status }}">{{ tx.status|capitalize }}</td>
            </tr>
            {% endfor %}
        </table>
    </body>
    </html>
    """
    return render_template_string(html, transactions=transactions)

@app.route("/truewallet/webhook", methods=["POST"])
def webhook():
    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "ไม่มีข้อมูล JSON"}), 400

        event_type_raw = data.get("event", "Other")
        bank_code = data.get("bank_code")
        event_type = translate_event_type(event_type_raw, bank_code)

        amount = float(data.get("amount", 0))
        status = data.get("status", "new").lower()
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
            "status": status
        })

        return jsonify({"status": "success"}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
