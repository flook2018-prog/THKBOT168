from flask import Flask, request, jsonify, render_template
import os, json, jwt, random
from datetime import datetime, date, timedelta
from collections import defaultdict

app = Flask(__name__)

transactions = []
daily_summary_history = defaultdict(float)
ip_approver_map = {}

DATA_FILE = "transactions_data.json"
LOG_FILE = "transactions.log"
SECRET_KEY = "8d2909e5a59bc24bbf14059e9e591402"

# โหลดข้อมูลธุรกรรมเก่า
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            transactions = json.load(f)
            for tx in transactions:
                tx["time"] = datetime.strptime(tx["time"], "%Y-%m-%d %H:%M:%S")
        except Exception:
            transactions = []

def save_transactions():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump([{**tx, "time": tx["time"].strftime("%Y-%m-%d %H:%M:%S")} for tx in transactions], f, ensure_ascii=False, indent=2)

def log_with_time(*args):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    msg = f"[{ts}] " + " ".join(str(a) for a in args)
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

def random_english_name():
    first_names = ["Alice","Bob","Charlie","David","Eve","Frank","Grace","Hannah","Ian","Jack","Kathy","Leo","Mia","Nina","Oscar"]
    return random.choice(first_names)

@app.route("/")
def index():
    user_ip = request.remote_addr or "unknown"
    return render_template("index.html", user_ip=user_ip)

@app.route("/get_transactions")
def get_transactions():
    today_str = date.today().strftime("%Y-%m-%d")
    today_transactions = [tx for tx in transactions if tx["time"].strftime("%Y-%m-%d") == today_str]

    new_orders = [tx for tx in today_transactions if tx["status"] == "new"][-20:][::-1]
    approved_orders = [tx for tx in today_transactions if tx["status"] == "approved"][-20:][::-1]
    cancelled_orders = [tx for tx in today_transactions if tx["status"] == "cancelled"][-20:][::-1]

    wallet_daily_total = daily_summary_history.get(today_str, 0)

    for tx in new_orders + approved_orders + cancelled_orders:
        tx["time_str"] = tx["time"].strftime("%Y-%m-%d %H:%M:%S")
        tx["amount_str"] = f"{tx['amount']:,.2f}"

    daily_list = [{"date": d, "total": f"{v:,.2f}"} for d, v in sorted(daily_summary_history.items())]

    return jsonify({
        "new_orders": new_orders,
        "approved_orders": approved_orders,
        "cancelled_orders": cancelled_orders,
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
            # เวลาอนุมัติตรงกับเวลาลูกค้า + UTC+7
            tx["approved_time"] = tx["time"].strftime("%Y-%m-%d %H:%M:%S")
            day = tx["time"].strftime("%Y-%m-%d")
            daily_summary_history[day] += tx["amount"]
            log_with_time(f"[APPROVED] {txid} by {approver_name} ({user_ip})")
            break
    save_transactions()
    return jsonify({"status": "success"}), 200

@app.route("/cancel", methods=["POST"])
def cancel():
    txid = request.json.get("id")
    for tx in transactions:
        if tx["id"] == txid and tx["status"] == "new":
            tx["status"] = "cancelled"
            # เวลา Cancel ตรงกับเวลาลูกค้า + UTC+7
            tx["cancelled_time"] = tx["time"].strftime("%Y-%m-%d %H:%M:%S")
            log_with_time(f"[CANCELLED] {txid}")
            break
    save_transactions()
    return jsonify({"status": "success"}), 200

@app.route("/restore", methods=["POST"])
def restore():
    txid = request.json.get("id")
    for tx in transactions:
        if tx["id"] == txid and tx["status"] in ["approved","cancelled"]:
            if tx["status"] == "approved":
                day = tx["time"].strftime("%Y-%m-%d")
                daily_summary_history[day] -= tx["amount"]
            tx["status"] = "new"
            tx.pop("approver_name", None)
            tx.pop("approved_time", None)
            tx.pop("cancelled_time", None)
            log_with_time(f"[RESTORED] {txid} -> new")
            break
    save_transactions()
    return jsonify({"status": "success"}), 200

@app.route("/truewallet/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True)
        token = data.get("message", "")
        decoded = jwt.decode(token, SECRET_KEY, algorithms=["HS256"], options={"verify_iat": False})

        txid = decoded.get("transaction_id") or f"TX{len(transactions)+1}"
        amount = int(decoded.get("amount", 0)) / 100
        sender_name = decoded.get("sender_name", "-")
        sender_mobile = decoded.get("sender_mobile", "-")
        name = f"{sender_name} / {sender_mobile}" if sender_mobile else sender_name
        bank_code = decoded.get("channel", "-")

        time_str = decoded.get("created_at") or decoded.get("time")
        try:
            if "T" in time_str:
                tx_time = datetime.strptime(time_str, "%Y-%m-%dT%H:%M:%S")
            else:
                tx_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            tx_time = tx_time + timedelta(hours=7)
        except:
            tx_time = datetime.now()

        tx = {
            "id": txid,
            "event": decoded.get("event_type", "Unknown"),
            "amount": amount,
            "name": name,
            "bank": bank_code,
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
