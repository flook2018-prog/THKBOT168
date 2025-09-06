from flask import Flask, request, jsonify, render_template
import os, json, jwt
from datetime import datetime, timedelta
from collections import defaultdict

app = Flask(__name__)

# -------------------- CONFIG --------------------
SECRET_KEY = "f557ff6589e6d075581d68df1d4f3af7"
DATA_FILE = "transactions_data.json"
LOG_FILE = "transactions.log"

transactions = []
ip_approver_map = {}
daily_summary_history = defaultdict(float)

BANK_MAP_TH = {
    "SCB": "ไทยพาณิชย์",
    "KBank": "กสิกรไทย",
    "BBL": "กรุงเทพ",
    "Bay": "กรุงศรี",
    "KTB": "กรุงไทย",
    "GSB": "ออมสิน",
    "TTB": "ทหารไทยธนชาต",
    "BAAC": "ธ.ก.ส.",
    "ICBC": "ไอซีบีซี",
    "UOB": "ยูโอบี",
    "Citi": "ซิตี้แบงก์",
    "CIMB": "ซีไอเอ็มบี",
    "LHBank": "แลนด์แอนด์เฮ้าส์",
    "StandardChartered": "สแตนดาร์ดชาร์เตอร์ด",
    "Mizhuho": "มิซูโฮ",
    "SMBC": "ซูมิโตโม",
    "HSBC": "เอชเอสบีซี",
    "Deutsche": "ดอยซ์แบงก์",
    "JP": "เจพีมอร์แกน"
}

# -------------------- UTIL --------------------
def log_with_time(tag, msg):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {tag} {msg}\n")

def save_transactions():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(transactions, f, ensure_ascii=False, default=str)
    except Exception as e:
        log_with_time("[SAVE ERROR]", str(e))

def load_transactions():
    global transactions
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                transactions.extend(json.load(f))
        except:
            transactions.clear()

load_transactions()

# -------------------- ROUTES --------------------
@app.route("/")
def index():
    user_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    return render_template("index.html", user_ip=user_ip)

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        token = request.json.get("data")
        decoded = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        log_with_time("[WEBHOOK DECODED]", decoded)

        txid = decoded.get("transaction_id") or f"TX{len(transactions)+1}"
        if any(tx["id"] == txid for tx in transactions):
            return jsonify({"status": "success", "message": "exists"}), 200

        # แปลงจำนวนเงิน (ทรูส่งเป็นสตางค์)
        try:
            amount = float(decoded.get("amount", 0)) / 100
        except:
            amount = 0.0

        sender_name = decoded.get("sender_name", "")
        sender_mobile = decoded.get("sender_mobile", "")
        name = f"{sender_name} / {sender_mobile}" if sender_mobile else sender_name or "-"

        channel = decoded.get("channel", "")
        bank = BANK_MAP_TH.get(channel, channel) if channel else "-"

        # เวลา
        time_str = decoded.get("received_time") or datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        try:
            clean = time_str.split("+")[0]
            tx_time = datetime.strptime(clean, "%Y-%m-%dT%H:%M:%S")
        except:
            tx_time = datetime.now()
        tx_time = tx_time + timedelta(hours=7)

        tx = {
            "id": txid,
            "event": decoded.get("event_type", "Unknown"),
            "amount": amount,
            "name": name,
            "bank": bank,
            "status": "new",
            "time": tx_time
        }
        transactions.append(tx)
        save_transactions()
        log_with_time("[WEBHOOK RECEIVED]", tx)

        return jsonify({"status": "success"}), 200
    except Exception as e:
        log_with_time("[WEBHOOK ERROR]", str(e))
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/get_transactions")
def get_transactions():
    new_orders = [t for t in transactions if t["status"] == "new"]
    approved_orders = [t for t in transactions if t["status"] == "approved"]
    cancelled_orders = [t for t in transactions if t["status"] == "cancelled"]

    # แปลง format สำหรับหน้าเว็บ
    for tx in new_orders + approved_orders + cancelled_orders:
        if isinstance(tx.get("time"), str):
            try:
                tx["time"] = datetime.fromisoformat(tx["time"])
            except:
                tx["time"] = datetime.now()
        tx["time_str"] = tx["time"].strftime("%Y-%m-%d %H:%M:%S")
        tx["amount_str"] = f"{tx['amount']:,.2f}"
        tx["name"] = tx.get("name", "-")
        tx["bank"] = BANK_MAP_TH.get(tx.get("bank", "-"), tx.get("bank", "-"))
        tx["customer_user"] = tx.get("customer_user", "-")
        if "approved_time" in tx:
            tx["approved_time_str"] = datetime.fromisoformat(str(tx["approved_time"])).strftime("%Y-%m-%d %H:%M:%S")
        if "cancelled_time" in tx:
            tx["cancelled_time_str"] = datetime.fromisoformat(str(tx["cancelled_time"])).strftime("%Y-%m-%d %H:%M:%S")

    today = datetime.now().strftime("%Y-%m-%d")
    wallet_daily_total = sum(t["amount"] for t in approved_orders if t["time"].strftime("%Y-%m-%d") == today)

    daily_summary = []
    for d, total in daily_summary_history.items():
        daily_summary.append({"date": d, "total": f"{total:,.2f}"})

    return jsonify({
        "new_orders": new_orders,
        "approved_orders": approved_orders,
        "cancelled_orders": cancelled_orders,
        "wallet_daily_total": f"{wallet_daily_total:,.2f}",
        "daily_summary": daily_summary
    })

@app.route("/approve", methods=["POST"])
def approve():
    data = request.json
    txid = data.get("id")
    customer_user = data.get("customer_user", "-")
    user_ip = request.headers.get("X-Forwarded-For", request.remote_addr)

    for tx in transactions:
        if tx["id"] == txid and tx["status"] == "new":
            tx["status"] = "approved"
            tx["approver_name"] = user_ip
            tx["approved_time"] = datetime.now()
            tx["customer_user"] = customer_user

            today = datetime.now().strftime("%Y-%m-%d")
            daily_summary_history[today] += tx["amount"]

            save_transactions()
            log_with_time("[APPROVED]", tx)
            break
    return jsonify({"status": "success"})

@app.route("/cancel", methods=["POST"])
def cancel():
    data = request.json
    txid = data.get("id")
    user_ip = request.headers.get("X-Forwarded-For", request.remote_addr)

    for tx in transactions:
        if tx["id"] == txid and tx["status"] == "new":
            tx["status"] = "cancelled"
            tx["canceler_name"] = user_ip
            tx["cancelled_time"] = datetime.now()
            save_transactions()
            log_with_time("[CANCELLED]", tx)
            break
    return jsonify({"status": "success"})

@app.route("/restore", methods=["POST"])
def restore():
    data = request.json
    txid = data.get("id")
    for tx in transactions:
        if tx["id"] == txid and tx["status"] in ["approved", "cancelled"]:
            tx["status"] = "new"
            tx.pop("approver_name", None)
            tx.pop("approved_time", None)
            tx.pop("canceler_name", None)
            tx.pop("cancelled_time", None)
            tx.pop("customer_user", None)
            save_transactions()
            log_with_time("[RESTORED]", tx)
            break
    return jsonify({"status": "success"})

@app.route("/reset_approved", methods=["POST"])
def reset_approved():
    global transactions
    transactions = [t for t in transactions if t["status"] != "approved"]
    save_transactions()
    return jsonify({"status": "success"})

@app.route("/reset_cancelled", methods=["POST"])
def reset_cancelled():
    global transactions
    transactions = [t for t in transactions if t["status"] != "cancelled"]
    save_transactions()
    return jsonify({"status": "success"})

# -------------------- MAIN --------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
