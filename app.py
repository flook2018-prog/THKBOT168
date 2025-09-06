from flask import Flask, request, jsonify, render_template
import os, json, jwt
from datetime import datetime, timedelta, date
from collections import defaultdict

app = Flask(__name__)

transactions = []
daily_summary_history = defaultdict(float)
ip_approver_map = {}

DATA_FILE = "transactions_data.json"
LOG_FILE = "transactions.log"

SECRET_KEY = os.getenv("TRUEWALLET_KEY", "f557ff6589e6d075581d68df1d4f3af7")

last_raw_payload = None

# ---------------- Logger ----------------
def log_with_time(prefix, msg=""):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now()}] {prefix} {msg}\n")

# ---------------- Load / Save ----------------
def load_transactions():
    global transactions
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            try:
                transactions = json.load(f)
                for tx in transactions:
                    if isinstance(tx.get("time"), str):
                        tx["time"] = datetime.strptime(tx["time"], "%Y-%m-%d %H:%M:%S")
            except Exception:
                transactions = []

def save_transactions():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(
            [
                {**tx, "time": tx["time"].strftime("%Y-%m-%d %H:%M:%S")}
                for tx in transactions
            ],
            f,
            ensure_ascii=False,
            indent=2,
        )

# ---------------- Bank Map ----------------
BANK_MAP_TH = {
    "BBL": "กรุงเทพ",
    "KTB": "กรุงไทย",
    "BAY": "กรุงศรีอยุธยา",
    "SCB": "ไทยพาณิชย์",
    "KBANK": "กสิกรไทย",
    "CIMB": "ซีไอเอ็มบี",
    "TMB": "ทหารไทยธนชาต",
    "UOB": "ยูโอบี",
    "GSB": "ออมสิน",
    "BAAC": "ธ.ก.ส.",
    "TRUEWALLET": "ทรูวอเลท"
}

# ---------------- หน้าเว็บ ----------------
@app.route("/")
def index():
    return render_template("index.html", transactions=transactions)

# ---------------- Get Transactions ----------------
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
        tx["name_mobile"] = f"{tx.get('name','-')} / {tx.get('mobile','-')}"
        tx["type"] = tx.get("type", "Unknown")
        tx["bank"] = BANK_MAP_TH.get(tx.get("bank","-"), tx.get("bank","-"))

    daily_list = [{"date": d, "total": f"{v:,.2f}"} for d, v in sorted(daily_summary_history.items())]

    return jsonify({
        "new_orders": new_orders,
        "approved_orders": approved_orders,
        "cancelled_orders": cancelled_orders,
        "wallet_daily_total": wallet_daily_total_str,
        "daily_summary": daily_list
    })

# ---------------- Webhook ----------------
@app.route("/truewallet/webhook", methods=["POST"])
def webhook():
    global last_raw_payload
    try:
        data = request.get_json(force=True, silent=True)

        if not data:
            log_with_time("[WEBHOOK ERROR] No JSON received")
            return jsonify({"status": "error", "message": "No JSON received"}), 400

        last_raw_payload = data
        log_with_time("[WEBHOOK PAYLOAD RAW]", json.dumps(data, ensure_ascii=False))

        token = data.get("token")
        if token:
            try:
                decoded = jwt.decode(
                    token,
                    SECRET_KEY,
                    algorithms=["HS256"],
                    options={"verify_exp": False, "verify_iat": False}
                )
                log_with_time("[WEBHOOK DECODED]", json.dumps(decoded, ensure_ascii=False))
            except Exception as e:
                log_with_time("[JWT ERROR]", str(e))
                return jsonify({"status": "error", "message": "Invalid JWT"}), 400
        else:
            decoded = data
            log_with_time("[WEBHOOK RAW NO TOKEN]", json.dumps(decoded, ensure_ascii=False))

        # ---------------- Mapping ฟิลด์ ----------------
        txid = decoded.get("transaction_id") or f"TX{len(transactions)+1}"
        if any(tx["id"] == txid for tx in transactions):
            return jsonify({"status": "success", "message": "Transaction exists"}), 200

        event = decoded.get("event_type") or decoded.get("event") or "Unknown"
        amount = float(decoded.get("amount", 0) or decoded.get("total", 0))
        sender_name = decoded.get("sender_name") or decoded.get("owner_name") or "-"
        sender_mobile = decoded.get("sender_mobile") or decoded.get("owner_mobile") or "-"
        bank_code = decoded.get("channel") or decoded.get("bank") or "TRUEWALLET"

        # เวลา +7 ชั่วโมง
        time_str = decoded.get("created_at") or decoded.get("time")
        try:
            if time_str and "T" in time_str:
                tx_time = datetime.strptime(time_str[:19], "%Y-%m-%dT%H:%M:%S")
            elif time_str:
                tx_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            else:
                tx_time = datetime.now()
            tx_time += timedelta(hours=7)
        except Exception as e:
            log_with_time("[TIME PARSE ERROR]", str(e))
            tx_time = datetime.now()

        # ---------------- สร้าง transaction ----------------
        tx = {
            "id": txid,
            "type": event,
            "amount": amount,
            "name": sender_name,
            "mobile": sender_mobile,
            "bank": BANK_MAP_TH.get(bank_code, bank_code),
            "status": "new",
            "time": tx_time
        }

        transactions.append(tx)
        save_transactions()
        log_with_time("[WEBHOOK RECEIVED]", json.dumps(tx, ensure_ascii=False, default=str))
        return jsonify({"status": "success"}), 200

    except Exception as e:
        log_with_time("[WEBHOOK ERROR]", str(e))
        return jsonify({"status": "error", "message": str(e)}), 500

# ---------------- Debug ----------------
@app.route("/debug/transactions", methods=["GET"])
def debug_transactions():
    return jsonify({
        "transactions": [
            {**tx, "time": tx["time"].strftime("%Y-%m-%d %H:%M:%S")}
            for tx in transactions
        ],
        "last_raw_payload": last_raw_payload
    }), 200

# ---------------- Main ----------------
if __name__ == "__main__":
    load_transactions()
    app.run(host="0.0.0.0", port=8080, debug=True)
