from flask import Flask, request, jsonify, render_template
import os, json, random, requests
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

WEBHOOK_FIX_URL = "https://tktruewallet-production.up.railway.app/truewallet/webhook"

# โหลดข้อมูลธุรกรรมเก่า
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

def save_transactions():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump([
            {
                **tx,
                "time": tx["time"].strftime("%Y-%m-%d %H:%M:%S")
            } for tx in transactions
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

@app.route("/fetch_from_wallet", methods=["POST"])
def fetch_from_wallet():
    """
    ดึงข้อมูล transaction จาก URL ของ TrueWallet ที่ฟิกไว้
    """
    try:
        # ส่ง request POST / GET ตาม URL ของ webhook
        resp = requests.get(WEBHOOK_FIX_URL, timeout=10)  # หรือ requests.post() ถ้าเป็น POST
        resp.raise_for_status()
        data_list = resp.json()  # สมมติ JSON ที่ได้เป็น list ของ transaction

        added = 0
        for decoded in data_list:
            txid = decoded.get("transaction_id") or f"TX{len(transactions)+1}"
            amount = float(decoded.get("amount", 0))
            sender_name = decoded.get("sender_name", "-")
            sender_mobile = decoded.get("sender_mobile", "-")
            name = f"{sender_name} / {sender_mobile}" if sender_mobile else sender_name
            bank_code = decoded.get("channel", "-")
            bank_name_th = BANK_MAP_TH.get(bank_code, bank_code)

            time_str = decoded.get("created_at") or decoded.get("time")
            try:
                if "T" in time_str:
                    tx_time = datetime.strptime(time_str, "%Y-%m-%dT%H:%M:%S")
                else:
                    tx_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                tx_time = tx_time + timedelta(hours=7)  # แปลงเวลาไทย
            except:
                tx_time = datetime.now() + timedelta(hours=7)

            tx = {
                "id": txid,
                "event": decoded.get("event_type", "Unknown"),
                "amount": amount,
                "name": name,
                "bank": bank_name_th,
                "status": "new",
                "time": tx_time
            }

            transactions.append(tx)
            added += 1
            log_with_time("[FETCHED]", txid, amount, name)
        save_transactions()
        return jsonify({"status": "success", "added": added}), 200
    except Exception as e:
        log_with_time("[FETCH ERROR]", str(e))
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
