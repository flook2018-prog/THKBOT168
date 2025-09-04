from flask import Flask, request, jsonify, render_template_string
import os

app = Flask(__name__)

# ดึง SECRET_KEY จาก Environment ของ Railway
SECRET_KEY = os.environ.get("SECRET_KEY", "local_dev_secret")

# ตัวอย่างเก็บรายการ
transactions = []  # แต่ละรายการเป็น dict: {"event":.., "amount":.., "status":..}

def translate_event_type(event_type):
    mapping = {
        "P2P": "วอลเล็ตโอนเงิน",
        "TOPUP": "เติมเงิน",
        "PAYMENT": "จ่ายเงิน"
    }
    return mapping.get(event_type, event_type)

# หน้าเว็บหลัก
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
        </script>
    </head>
    <body>
        <h1>THKBot168 Dashboard</h1>
        <input type="text" id="searchInput" onkeyup="filterTable()" placeholder="ค้นหารายการ...">
        <table id="txTable">
            <tr>
                <th>ประเภท</th>
                <th>จำนวน</th>
                <th>สถานะ</th>
            </tr>
            {% for tx in transactions %}
            <tr>
                <td>{{ tx.event }}</td>
                <td>{{ tx.amount }} บาท</td>
                <td class="status-{{ tx.status }}">{{ tx.status|capitalize }}</td>
            </tr>
            {% endfor %}
        </table>
    </body>
    </html>
    """
    return render_template_string(html, transactions=transactions)

# Webhook สำหรับ TrueWallet
@app.route("/truewallet/webhook", methods=["POST"])
def webhook():
    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "ไม่มีข้อมูล JSON"}), 400

        event_type = translate_event_type(data.get("event", "Unknown"))
        amount = data.get("amount", 0)
        status = data.get("status", "new")  # รับค่า status จาก webhook ถ้ามี

        transactions.append({
            "event": event_type,
            "amount": amount,
            "status": status.lower()  # new / approved / rejected
        })

        return jsonify({"status": "success"}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
