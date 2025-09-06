from flask import Flask, request, jsonify, render_template
import os, json, random, threading, time
from datetime import datetime, date, timedelta
from collections import defaultdict

app = Flask(__name__)

transactions = []
daily_summary_history = defaultdict(float)
ip_approver_map = {}

DATA_FILE = "transactions_data.json"
LOG_FILE = "transactions.log"

BANK_MAP_TH = {
    "BBL": "กรุงเทพ",
    "KBANK": "กสิกรไทย",
    "SCB": "ไทยพาณิชย์",
    "KTB": "กรุงไทย",
    "BAY": "กรุงศรีอยุธยา",
    "TMB": "ทหารไทย",
    "TRUEWALLET": "True Wallet",
}

# -----------------------------------------
# โหลดข้อมูลเก่า
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            transactions = json.load(f)
            for tx in transactions:
                tx["time"] = datetime.strptime(tx["time"], "%Y-%m-%d %H:%M:%S")
        except:
            transactions = []
else:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump([], f)

# -----------------------------------------
# ฟังก์ชันช่วยเหลือ
def save_transactions():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump([
            {**tx, "time": tx["time"].strftime("%Y-%m-%d %H:%M:%S")} for tx in transactions
        ], f, ensure_ascii=False, indent=2)

def log_with_time(*args):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    msg = f"[{ts}] " + " ".join(str(a) for a in args)
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

def random_english_name():
    names = ["Alice","Bob","Charlie","David","Eve","Frank","Grace","Hannah","Ian","Jack","Kathy","Leo","Mia","Nina","Oscar"]
    return random.choice(names)

# -----------------------------------------
# Background auto-fetch (ถ้าอยากต่อยอด)
# ตอนนี้เวอร์ชันทดสอบ webhook จบแค่รับ request
# สามารถเพิ่ม auto-fetch ได้ทีหลัง

# -----------------------------------------
# Flask Endpoints

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

    wallet_daily_total = sum(tx["amount"] for tx in approved_orders)
    wallet_daily_total_str = f"{wallet_daily_total:,.2f}"

    for tx in new_orders + approved_orders + cancelled_orders:
        tx["time_str"] = tx["time"].strftime("%Y-%m-%d %H:%M:%S")
        tx["amount_str"] = f"{tx['amount']:,.2f}"
        tx["name"] = tx.get("name","-")
        tx["bank"] = BANK_MAP_TH.get(tx.get("bank","-"), tx.get("bank","-"))
        tx["customer_user"] = tx.get("customer_user","-")

    daily_list = [{"date": d, "total": f"{v:,.2f}"} for d, v in sorted(daily_summary_history.items())]

    return jsonify({
        "new_orders": new_orders,
        "approved_orders": approved_orders,
        "cancelled_orders": cancelled_orders,
        "wallet_daily_total": wallet_daily_total_str,
        "daily_summary": daily_list
    })

# -----------------------------------------
# Approve / Cancel / Restore / Reset

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
            tx["approved_time"] = datetime.now()
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
            tx["cancelled_time"] = datetime.now()
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

# -----------------------------------------
# Webhook endpoint (รับข้อมูลจาก TrueWallet)
@app.route("/truewallet/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True)
        print("[WEBHOOK RECEIVED]", data)  # แสดงข้อมูลจริงใน console / log
        return jsonify({"status": "success"}), 200
    except Exception as e:
        print("[WEBHOOK ERROR]", str(e))
        return jsonify({"status": "error", "message": str(e)}), 500

# -----------------------------------------
# Run Flask
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
