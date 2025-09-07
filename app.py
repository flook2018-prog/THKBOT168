from flask import Flask, request, jsonify, render_template, send_from_directory
import os, json, jwt, random
from datetime import datetime, timedelta
from collections import defaultdict
from werkzeug.utils import secure_filename

# -------------------- Config --------------------
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

transactions = {"new": [], "approved": [], "cancelled": []}
daily_summary_history = defaultdict(float)
ip_approver_map = {}

DATA_FILE = "transactions_data.json"
LOG_FILE = "transactions.log"
SECRET_KEY = "f557ff6589e6d075581d68df1d4f3af7"

# กำหนด offset ของเวลา (ใช้ Service Variable บน Railway)
TIME_OFFSET_HOURS = int(os.environ.get("TIME_OFFSET_HOURS", 0))

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

    for tx in approved_orders:
        tx["approved_time_str"] = tx.get("approved_time") or "-"
    for tx in cancelled_orders:
        tx["cancelled_time_str"] = tx.get("cancelled_time") or "-"

    return jsonify({
        "new_orders": new_orders,
        "approved_orders": approved_orders,
        "cancelled_orders": cancelled_orders,
        "wallet_daily_total": wallet_daily_total_str,
        "daily_summary": [{"date": d, "total": fmt_amount(v)} for d,v in sorted(daily_summary_history.items())]
    })

# -------------------- Approve / Cancel / Restore --------------------
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
            tx["approved_time"] = (datetime.utcnow() + timedelta(hours=TIME_OFFSET_HOURS)).strftime("%Y-%m-%d %H:%M:%S")
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
            tx["cancelled_time"] = (datetime.utcnow() + timedelta(hours=TIME_OFFSET_HOURS)).strftime("%Y-%m-%d %H:%M:%S")
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

# -------------------- Upload / View Slip --------------------
@app.route("/upload_slip/<txid>", methods=["POST"])
def upload_slip(txid):
    if "file" not in request.files:
        return jsonify({"status":"error","message":"No file part"}), 400
    file = request.files["file"]
    if file.filename=="":
        return jsonify({"status":"error","message":"No selected file"}), 400
    filename = f"{txid}_{secure_filename(file.filename)}"
    file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

    for lst in [transactions["new"], transactions["approved"], transactions["cancelled"]]:
        for tx in lst:
            if tx["id"]==txid:
                tx["slip_filename"] = filename
                break
    save_transactions()
    return jsonify({"status":"success","filename":filename})

@app.route("/slip/<filename>")
def get_slip(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# -------------------- Run App --------------------
if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",8080)), debug=True)
