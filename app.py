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
    "7-ELEVEN": "7-Eleven",
}

# โหลดธุรกรรมเก่า
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            transactions = json.load(f)
            for tx in transactions:
                tx["time"] = datetime.strptime(tx["time"], "%Y-%m-%d %H:%M:%S")
        except:
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
    names = ["Alice","Bob","Charlie","David","Eve","Frank","Grace","Hannah","Ian","Jack","Kathy","Leo","Mia","Nina","Oscar"]
    return random.choice(names)

# -------------------- Flask Endpoints --------------------
@app.route("/")
def index():
    user_ip = request.remote_addr or "unknown"
    return render_template("index.html", user_ip=user_ip)

@app.route("/get_transactions")
def get_transactions():
    # เวลาไทยตอนนี้
    today = datetime.utcnow() + timedelta(hours=7)
    today_str = today.strftime("%Y-%m-%d")

    # เลือกรายการที่เวลาประเทศไทยตรงกับวันนี้
    today_transactions = []
    for tx in transactions:
        tx_local = tx["time"] + timedelta(hours=7)
        if tx_local.strftime("%Y-%m-%d") == today_str:
            today_transactions.append(tx)

    new_orders = [tx for tx in today_transactions if tx["status"] == "new"][-20:][::-1]
    approved_orders = [tx for tx in today_transactions if tx["status"] == "approved"][-20:][::-1]
    cancelled_orders = [tx for tx in today_transactions if tx["status"] == "cancelled"][-20:][::-1]

    wallet_daily_total = sum(tx["amount"] for tx in approved_orders)
    wallet_daily_total_str = f"{wallet_daily_total/100:,.2f}"

    # เตรียมเวลาแสดง +7 ชั่วโมงสำหรับหน้าเว็บ
    for tx in new_orders + approved_orders + cancelled_orders:
        tx_local = tx["time"] + timedelta(hours=7)
        tx["time_str"] = tx_local.strftime("%Y-%m-%d %H:%M:%S")
        tx["amount_str"] = f"{tx['amount']/100:,.2f}"  # แปลงจากสตางค์เป็นบาท
        tx["bank"] = BANK_MAP_TH.get(tx.get("bank","-"), tx.get("bank","-"))
        tx["approved_time_str"] = (tx["approved_time"] + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S") if tx.get("approved_time") else "-"
        tx["cancelled_time_str"] = (tx["cancelled_time"] + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S") if tx.get("cancelled_time") else "-"

    daily_list = [{"date": d, "total": f"{v/100:,.2f}"} for d, v in sorted(daily_summary_history.items())]

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
            tx["approved_time"] = datetime.utcnow()
            tx["customer_user"] = customer_user
            day = (tx["time"] + timedelta(hours=7)).strftime("%Y-%m-%d")
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
            tx["cancelled_time"] = datetime.utcnow()
            tx["canceler_name"] = canceler_name
            log_with_time(f"[CANCELLED] {txid} by {canceler_name} ({user_ip})")
            break
    save_transactions()
    return jsonify({"status": "success"}), 200

# -------------------- Webhook TrueWallet --------------------
@app.route("/truewallet/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True, silent=True)
        if not data:
            log_with_time("[WEBHOOK ERROR] No JSON received")
            return jsonify({"status":"error","message":"No JSON received"}), 400

        # Decode JWT message หากมี
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

        # Transaction ID
        txid = decoded.get("transaction_id") or f"TX{len(transactions)+1}"
        if any(tx["id"] == txid for tx in transactions):
            return jsonify({"status":"success","message":"Transaction exists"}), 200

        # จำนวนเงิน (สตางค์)
        amount = int(decoded.get("amount",0))

        # ชื่อ / เบอร์
        sender_name = decoded.get("sender_name","-")
        sender_mobile = decoded.get("sender_mobile","-")
        name = f"{sender_name} / {sender_mobile}" if sender_mobile else sender_name

        # ธนาคาร / ช่องทาง
        bank_code = (decoded.get("channel") or "TRUEWALLET").upper()
        bank_name_th = BANK_MAP_TH.get(bank_code, "ทรูวอเลท")  # ถ้าเป็น TrueWallet

        # ประเภท event
        event_type = decoded.get("event_type","ฝาก")

        # เวลา received_time ของ TrueWallet
        time_str = decoded.get("received_time") or datetime.utcnow().isoformat()
        try:
            tx_time = datetime.strptime(time_str[:19], "%Y-%m-%dT%H:%M:%S")
        except:
            tx_time = datetime.utcnow()

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
