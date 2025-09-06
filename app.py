from flask import Flask, request, jsonify, render_template
import os, json, jwt, random
from datetime import datetime
from collections import defaultdict

app = Flask(__name__)

transactions = {"new": [], "approved": [], "cancelled": []}
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
    "7-ELEVEN": "7-Eleven",
}

# -------------------- Helpers --------------------
def save_transactions():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(transactions, f, ensure_ascii=False, indent=2)

def log_with_time(*args):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    msg = f"[{ts}] " + " ".join(str(a) for a in args)
    print(msg, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

def random_english_name():
    names = ["Alice","Bob","Charlie","David","Eve","Frank","Grace","Hannah","Ian","Jack","Kathy","Leo","Mia","Nina","Oscar"]
    return random.choice(names)

def fmt_time(t):
    if isinstance(t, str):
        try:
            return t[:19].replace("T"," ")
        except:
            return str(t)
    elif isinstance(t, datetime):
        return t.strftime("%Y-%m-%d %H:%M:%S")
    return str(t)

def fmt_amount(a):
    return f"{a/100:,.2f}" if isinstance(a,(int,float)) else str(a)

# -------------------- Flask Endpoints --------------------
@app.route("/")
def index():
    user_ip = request.remote_addr or "unknown"
    return render_template("index.html", user_ip=user_ip)

@app.route("/get_transactions")
def get_transactions():
    new_orders = transactions["new"][-20:][::-1]
    approved_orders = transactions["approved"][-20:][::-1]
    cancelled_orders = transactions["cancelled"][-20:][::-1]

    wallet_daily_total = sum(tx["amount"] for tx in approved_orders)
    wallet_daily_total_str = fmt_amount(wallet_daily_total)

    return jsonify({
        "new_orders": new_orders,
        "approved_orders": approved_orders,
        "cancelled_orders": cancelled_orders,
        "wallet_daily_total": wallet_daily_total_str,
        "daily_summary": [{"date": d, "total": fmt_amount(v)} for d,v in sorted(daily_summary_history.items())]
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

    for tx in transactions["new"]:
        if tx["id"] == txid:
            tx["status"] = "approved"
            tx["approver_name"] = approver_name
            tx["approved_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            tx["customer_user"] = customer_user
            transactions["approved"].append(tx)
            transactions["new"].remove(tx)
            day = tx["time"][:10] if isinstance(tx["time"], str) else tx["time"].strftime("%Y-%m-%d")
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

    for tx in transactions["new"]:
        if tx["id"] == txid:
            tx["status"] = "cancelled"
            tx["cancelled_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            tx["canceler_name"] = canceler_name
            transactions["cancelled"].append(tx)
            transactions["new"].remove(tx)
            log_with_time(f"[CANCELLED] {txid} by {canceler_name} ({user_ip})")
            break
    save_transactions()
    return jsonify({"status": "success"}), 200

@app.route("/restore", methods=["POST"])
def restore():
    txid = request.json.get("id")
    for lst in [transactions["approved"], transactions["cancelled"]]:
        for tx in lst:
            if tx["id"] == txid:
                tx["status"] = "new"
                tx.pop("approver_name", None)
                tx.pop("approved_time", None)
                tx.pop("canceler_name", None)
                tx.pop("cancelled_time", None)
                tx.pop("customer_user", None)
                transactions["new"].append(tx)
                lst.remove(tx)
                log_with_time(f"[RESTORED] {txid}")
                break
    save_transactions()
    return jsonify({"status": "success"}), 200

@app.route("/reset_approved", methods=["POST"])
def reset_approved():
    for tx in transactions["approved"]:
        tx["status"] = "new"
        tx.pop("approver_name", None)
        tx.pop("approved_time", None)
        tx.pop("customer_user", None)
        transactions["new"].append(tx)
    transactions["approved"].clear()
    save_transactions()
    return jsonify({"status": "success"}), 200

@app.route("/reset_cancelled", methods=["POST"])
def reset_cancelled():
    for tx in transactions["cancelled"]:
        tx["status"] = "new"
        tx.pop("canceler_name", None)
        tx.pop("cancelled_time", None)
        transactions["new"].append(tx)
    transactions["cancelled"].clear()
    save_transactions()
    return jsonify({"status": "success"}), 200

# -------------------- Webhook TrueWallet --------------------
@app.route("/truewallet/webhook", methods=["POST"])
def truewallet_webhook():
    try:
        data = request.get_json(force=True, silent=True)
        if not data:
            log_with_time("[WEBHOOK ERROR] No JSON received")
            return jsonify({"status":"error","message":"No JSON received"}), 400

        message_jwt = data.get("message")
        decoded = {}
        if message_jwt:
            try:
                decoded = jwt.decode(message_jwt, SECRET_KEY, algorithms=["HS256"])
            except Exception as e:
                log_with_time("[JWT ERROR]", str(e))
                return jsonify({"status":"error","message":"Invalid JWT"}), 400
        else:
            decoded = data

        txid = decoded.get("transaction_id") or f"TX{len(transactions['new'])+len(transactions['approved'])+len(transactions['cancelled'])+1}"
        if any(tx["id"] == txid for lst in transactions.values() for tx in lst):
            return jsonify({"status":"success","message":"Transaction exists"}), 200

        amount = int(decoded.get("amount",0))
        sender_name = decoded.get("sender_name","-")
        sender_mobile = decoded.get("sender_mobile","-")
        name = f"{sender_name} / {sender_mobile}" if sender_mobile else sender_name
        bank_code = (decoded.get("channel") or "-").upper()
        bank_name_th = BANK_MAP_TH.get(bank_code, bank_code)
        event_type = decoded.get("event_type","ฝาก")
        time_str = decoded.get("received_time") or datetime.now().isoformat()
        try:
            tx_time = time_str[:19].replace("T"," ")
        except:
            tx_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        tx = {
            "id": txid,
            "event": event_type,
            "amount": amount,
            "amount_str": fmt_amount(amount),
            "name": name,
            "bank": bank_name_th,
            "status": "new",
            "time": tx_time,
            "time_str": tx_time
        }

        transactions["new"].append(tx)
        save_transactions()
        log_with_time("[WEBHOOK RECEIVED]", tx)
        return jsonify({"status":"success"}), 200

    except Exception as e:
        log_with_time("[WEBHOOK EXCEPTION]", str(e))
        return jsonify({"status":"error","message":str(e)}), 500

# -------------------- Run App --------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",8080)), debug=True)
