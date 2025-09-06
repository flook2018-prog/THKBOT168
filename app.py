from flask import Flask, request, jsonify, render_template
import os, json, jwt, random
from datetime import datetime, timedelta, date
from collections import defaultdict

app = Flask(__name__)

transactions = []
daily_summary_history = defaultdict(float)
ip_approver_map = {}

DATA_FILE = "transactions_data.json"
LOG_FILE = "transactions.log"
SECRET_KEY = "f557ff6589e6d075581d68df1d4f3af7"
BANK_MAP_TH = {
    "BBL": "กรุงเทพ",
    "KBANK": "กสิกรไทย",
    "SCB": "ไทยพาณิชย์",
    "KTB": "กรุงไทย",
    "BAY": "กรุงศรีอยุธยา",
    "TMB": "ทหารไทย",
    "TRUEWALLET": "ทรูวอเลท",
}

# โหลดธุรกรรมเก่า
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            transactions = json.load(f)
            for tx in transactions:
                tx["time"] = datetime.strptime(tx["time"], "%Y-%m-%d %H:%M:%S")
                if tx.get("approved_time"):
                    tx["approved_time"] = datetime.strptime(tx["approved_time"], "%Y-%m-%d %H:%M:%S")
                if tx.get("cancelled_time"):
                    tx["cancelled_time"] = datetime.strptime(tx["cancelled_time"], "%Y-%m-%d %H:%M:%S")
        except:
            transactions = []

def save_transactions():
    def serialize_tx(tx):
        d = tx.copy()
        d["time"] = d["time"].strftime("%Y-%m-%d %H:%M:%S")
        if d.get("approved_time"):
            d["approved_time"] = d["approved_time"].strftime("%Y-%m-%d %H:%M:%S")
        if d.get("cancelled_time"):
            d["cancelled_time"] = d["cancelled_time"].strftime("%Y-%m-%d %H:%M:%S")
        return d
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump([serialize_tx(tx) for tx in transactions], f, ensure_ascii=False, indent=2)

def log_with_time(*args):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    msg = f"[{ts}] " + " ".join(str(a) for a in args)
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

def random_english_name():
    names = ["Alice","Bob","Charlie","David","Eve","Frank","Grace","Hannah","Ian","Jack","Kathy","Leo","Mia","Nina","Oscar"]
    return random.choice(names)

# -------------------- Flask Endpoints --------------------
@app.route("/")
def index():
    user_ip = request.remote_addr or "unknown"
    return render_template("index.html", user_ip=user_ip)

@app.route("/get_transactions")
def get_transactions():
    for tx in transactions:
        # เวลาแสดงบนเว็บเป็น +7 ชั่วโมง
        tx["_display_time"] = tx["time"] + timedelta(hours=7)
        tx["_approved_display_time"] = tx["approved_time"] + timedelta(hours=7) if tx.get("approved_time") else None
        tx["_cancelled_display_time"] = tx["cancelled_time"] + timedelta(hours=7) if tx.get("cancelled_time") else None

    new_orders = [tx for tx in transactions if tx["status"] == "new"][::-1]
    approved_orders = [tx for tx in transactions if tx["status"] == "approved"][::-1]
    cancelled_orders = [tx for tx in transactions if tx["status"] == "cancelled"][::-1]

    wallet_daily_total = sum(tx["amount"] for tx in approved_orders)
    wallet_daily_total_str = f"{wallet_daily_total:,.2f}"

    # แสดงรายการใหม่
    for tx in new_orders:
        tx["time_str"] = tx["_display_time"].strftime("%Y-%m-%d %H:%M:%S")
        tx["amount_str"] = f"{tx['amount']:,.2f}"
        tx["name"] = tx.get("name","-")
        tx["bank"] = BANK_MAP_TH.get(tx.get("bank","-"), tx.get("bank","-"))

    # แสดงรายการ approved
    for tx in approved_orders:
        tx["time_str"] = tx["_display_time"].strftime("%Y-%m-%d %H:%M:%S")
        tx["approved_time_str"] = tx["_approved_display_time"].strftime("%Y-%m-%d %H:%M:%S") if tx["_approved_display_time"] else "-"
        tx["amount_str"] = f"{tx['amount']:,.2f}"
        tx["name"] = tx.get("name","-")
        tx["bank"] = BANK_MAP_TH.get(tx.get("bank","-"), tx.get("bank","-"))
        tx["customer_user"] = tx.get("customer_user","-")

    # แสดงรายการ cancelled
    for tx in cancelled_orders:
        tx["time_str"] = tx["_display_time"].strftime("%Y-%m-%d %H:%M:%S")
        tx["cancelled_time_str"] = tx["_cancelled_display_time"].strftime("%Y-%m-%d %H:%M:%S") if tx["_cancelled_display_time"] else "-"
        tx["amount_str"] = f"{tx['amount']:,.2f}"
        tx["name"] = tx.get("name","-")
        tx["bank"] = BANK_MAP_TH.get(tx.get("bank","-"), tx.get("bank","-"))

    daily_list = [{"date": d, "total": f"{v:,.2f}"} for d, v in sorted(daily_summary_history.items())]

    return jsonify({
        "new_orders": new_orders,
        "approved_orders": approved_orders,
        "cancelled_orders": cancelled_orders,
        "wallet_daily_total": wallet_daily_total_str,
        "daily_summary": daily_list
    })

# -------------------- Approve / Cancel / Restore / Reset --------------------
@app.route("/approve", methods=["POST"])
def approve():
    txid = request.json.get("id")
    customer_user = request.json.get("customer_user")
    user_ip = request.remote_addr or "unknown"
    if user_ip not in ip_approver_map:
        ip_approver_map[user_ip] = random_english_name()
    approver_name = ip_approver_map[user_ip]

    for tx in transactions:
        if tx["id"] == txid:
            tx["status"] = "approved"
            tx["approver_name"] = approver_name
            tx["approved_time"] = datetime.now()  # เวลากระทำจริง
            tx["customer_user"] = customer_user
            day = tx["time"].strftime("%Y-%m-%d")
            daily_summary_history[day] += tx["amount"]
            log_with_time(f"[APPROVED] {txid} by {approver_name} ({user_ip}) for customer {customer_user}")
            break
    save_transactions()
    return jsonify({"status": "success"}), 200

@app.route("/cancel", methods=["POST"])
def cancel():
    txid = request.json.get("id")
    user_ip = request.remote_addr or "unknown"
    if user_ip not in ip_approver_map:
        ip_approver_map[user_ip] = random_english_name()
    canceler_name = ip_approver_map[user_ip]

    for tx in transactions:
        if tx["id"] == txid and tx["status"] == "new":
            tx["status"] = "cancelled"
            tx["cancelled_time"] = datetime.now()  # เวลากระทำจริง
            tx["canceler_name"] = canceler_name
            log_with_time(f"[CANCELLED] {txid} by {canceler_name} ({user_ip})")
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
            tx.pop("customer_user", None)
            tx.pop("canceler_name", None)
            log_with_time(f"[RESTORED] {txid} -> new")
            break
    save_transactions()
    return jsonify({"status": "success"}), 200

@app.route("/reset_approved", methods=["POST"])
def reset_approved():
    global transactions
    transactions = [tx for tx in transactions if tx.get("status") != "approved"]
    log_with_time("[RESET APPROVED] All approved orders removed")
    save_transactions()
    return jsonify({"status": "success"}), 200

@app.route("/reset_cancelled", methods=["POST"])
def reset_cancelled():
    global transactions
    transactions = [tx for tx in transactions if tx.get("status") != "cancelled"]
    log_with_time("[RESET CANCELLED] All cancelled orders removed")
    save_transactions()
    return jsonify({"status": "success"}), 200

# -------------------- Webhook --------------------
@app.route("/truewallet/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True, silent=True)
        if not data:
            log_with_time("[WEBHOOK ERROR] No JSON received")
            return jsonify({"status":"error","message":"No JSON received"}), 400

        token = data.get("token")
        if token:
            try:
                decoded = jwt.decode(token, SECRET_KEY, algorithms=["HS256"], options={"verify_iat": False})
            except Exception as e:
                log_with_time("[JWT ERROR]", str(e))
                return jsonify({"status":"error","message":"Invalid JWT"}), 400
        else:
            decoded = data

        txid = decoded.get("transaction_id") or f"TX{len(transactions)+1}"
        if any(tx["id"] == txid for tx in transactions):
            return jsonify({"status":"success","message":"Transaction exists"}), 200

        amount = float(decoded.get("amount",0))
        sender_name = decoded.get("sender_name","-")
        sender_mobile = decoded.get("sender_mobile","-")
        name = f"{sender_name} / {sender_mobile}" if sender_mobile else sender_name

        bank_code = decoded.get("channel","-")
        bank_name_th = BANK_MAP_TH.get(bank_code.upper(), bank_code)

        event_type = decoded.get("event_type","ฝาก")

        time_str = decoded.get("created_at") or decoded.get("time")
        try:
            if "T" in time_str:
                tx_time = datetime.strptime(time_str, "%Y-%m-%dT%H:%M:%S")
            else:
                tx_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        except:
            tx_time = datetime.now()

        tx = {
            "id": txid,
            "event": event_type,
            "amount": amount,
            "name": name,
            "bank": bank_name_th,
            "status": "new",
            "time": tx_time
        }

        transactions.append(tx)
        save_transactions()
        log_with_time("[WEBHOOK RECEIVED]", tx)
        return jsonify({"status":"success"}), 200

    except Exception as e:
        log_with_time("[WEBHOOK ERROR]", str(e))
        return jsonify({"status":"error","message": str(e)}), 500

# -------------------- Run Flask --------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT",8080))
    app.run(host="0.0.0.0", port=port)
