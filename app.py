from flask import Flask, request, render_template_string, redirect, url_for, jsonify
from datetime import datetime

app = Flask(__name__)

# เก็บรายการธุรกรรมทั้งหมด
transactions = []

# แผนที่ธนาคารภาษาไทย
BANK_MAP = {
    "BBL": "ธนาคารกรุงเทพ",
    "KTB": "กรุงไทย",
    "SCB": "ไทยพาณิชย์",
    "KBANK": "กสิกรไทย",
    "BAAC": "ธ.ก.ส.",
    "GSB": "ออมสิน",
    "TMB": "ทหารไทย",
    "BAY": "กรุงศรี",
    "CIMB": "CIMB ไทย",
    "UOB": "UOB",
    "TTB": "TTB",
}

# แปลงประเภท
def translate_event_type(event_type):
    if event_type == "P2P":
        return "โอนเงิน"
    elif event_type == "TOPUP":
        return "เติมเงิน"
    elif event_type == "WITHDRAW":
        return "ถอนเงิน"
    else:
        return "อื่น ๆ"


@app.route("/truewallet/webhook", methods=["POST"])
def truewallet_webhook():
    payload = request.json
    txid = payload.get("transactionId", "N/A")
    event_type = translate_event_type(payload.get("event", ""))
    amount = float(payload.get("amount", 0.0))
    account_name = payload.get("accountName", "-")
    bank_code = payload.get("bankCode", "")

    # แปลงธนาคาร
    bank_name = BANK_MAP.get(bank_code, "ธนาคารอื่น")

    transaction = {
        "txid": txid,
        "type": event_type,
        "amount": amount,
        "account": f"{account_name} ({bank_name})",
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "new",
    }
    transactions.insert(0, transaction)  # เก็บไว้ด้านบนสุด
    return jsonify({"status": "success"})


@app.route("/approve/<txid>")
def approve_transaction(txid):
    for tx in transactions:
        if tx["txid"] == txid:
            tx["status"] = "approved"
            break
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
def dashboard():
    # เอาเฉพาะ 10 ออเดอร์ล่าสุด
    latest_tx = transactions[:10]

    dashboard_html = """
    <html>
    <head>
        <title>Dashboard</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            h2 { text-align: center; }
            .table-container {
                max-height: 400px;
                overflow-y: scroll;
                border: 1px solid #ddd;
                margin-bottom: 20px;
            }
            table { width: 100%; border-collapse: collapse; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: center; }
            th { background-color: #f2f2f2; }
            .btn { padding: 4px 10px; background: green; color: white; border: none; cursor: pointer; }
            .btn:disabled { background: gray; }
        </style>
        <script>
            setInterval(function(){ location.reload(); }, 5000);
        </script>
    </head>
    <body>
        <h2>รายการธุรกรรม (10 รายการล่าสุด)</h2>
        <div class="table-container">
        <table>
            <tr>
                <th>TXID</th>
                <th>ประเภท</th>
                <th>จำนวน</th>
                <th>ชื่อ/ธนาคาร</th>
                <th>เวลา</th>
                <th>สถานะ</th>
                <th>อนุมัติ</th>
            </tr>
            {% for tx in transactions %}
            <tr>
                <td>{{ tx.txid }}</td>
                <td>{{ tx.type }}</td>
                <td>{{ "%.2f"|format(tx.amount) }}</td>
                <td>{{ tx.account }}</td>
                <td>{{ tx.time }}</td>
                <td>{{ tx.status }}</td>
                <td>
                    {% if tx.status != "approved" %}
                        <a class="btn" href="/approve/{{ tx.txid }}">อนุมัติ</a>
                    {% else %}
                        ✔
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </table>
        </div>
    </body>
    </html>
    """
    return render_template_string(dashboard_html, transactions=latest_tx)


@app.route("/")
def home():
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    app.run(debug=True)
