from flask import Flask, request, jsonify, render_template_string
import os
from datetime import datetime, date

app = Flask(__name__)

transactions = []  # {"id":.., "event":.., "amount":.., "name":.., "bank":.., "status":.., "time":..}

LOG_FILE = "transactions.log"

def translate_event_type(event_type):
    mapping = {
        "P2P": "วอลเล็ตโอนเงิน",
        "TOPUP": "เติมเงิน",
        "PAYMENT": "จ่ายเงิน",
        "WITHDRAW": "ถอนเงิน"
    }
    return mapping.get(event_type, event_type)

def log_with_time(*args):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    msg = f"[{ts}] " + " ".join(str(a) for a in args)
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

# ================== Dashboard ==================
@app.route("/")
def index():
    return render_template_string(DASHBOARD_HTML)

@app.route("/get_transactions")
def get_transactions():
    today_str = date.today().strftime("%Y-%m-%d")
    new_orders = [tx for tx in transactions if tx["status"] == "new"][-20:][::-1]
    approved_orders = [tx for tx in transactions if tx["status"] == "approved"][-20:][::-1]

    wallet_daily_total = sum(tx["amount"] for tx in transactions
                             if tx["status"] == "approved" and tx["time"].strftime("%Y-%m-%d") == today_str)
    wallet_history = sum(tx["amount"] for tx in transactions if tx["status"] == "approved")

    for tx in new_orders + approved_orders:
        tx["time_str"] = tx["time"].strftime("%Y-%m-%d %H:%M:%S")

    return jsonify({
        "new_orders": new_orders,
        "approved_orders": approved_orders,
        "wallet_daily_total": wallet_daily_total,
        "wallet_history": wallet_history
    })

@app.route("/approve", methods=["POST"])
def approve():
    txid = request.json.get("id")
    for tx in transactions:
        if tx["id"] == txid:
            tx["status"] = "approved"
            log_with_time(f"[UPDATE STATUS] {txid} -> approved")
            break
    return jsonify({"status": "success"}), 200

@app.route("/truewallet/webhook", methods=["POST"])
def webhook():
    try:
        # ตรวจสอบว่ามาเป็น JSON หรือไม่
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form.to_dict()
        if not data:
            log_with_time("[WEBHOOK ERROR] ไม่มีข้อมูล JSON หรือ Form")
            return jsonify({"status": "error", "message": "ไม่มีข้อมูล JSON หรือ Form"}), 400

        txid = data.get("transactionId") or f"TX{len(transactions)+1}"
        event_type = translate_event_type(data.get("event", "Unknown"))
        try:
            amount = float(data.get("amount", 0))
        except:
            amount = 0
        name = data.get("accountName") or data.get("name") or "-"
        bank = data.get("bankCode") or data.get("bank") or "-"
        status = data.get("status", "new")
        now = datetime.now()

        tx = {
            "id": txid,
            "event": event_type,
            "amount": amount,
            "name": name,
            "bank": bank,
            "status": status.lower(),
            "time": now
        }
        transactions.append(tx)
        log_with_time("[WEBHOOK RECEIVED]", tx)
        return jsonify({"status": "success"}), 200

    except Exception as e:
        log_with_time("[WEBHOOK EXCEPTION]", e)
        return jsonify({"status": "error", "message": str(e)}), 500

# ================== HTML ==================
DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>THKBot168 Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; padding: 20px; background: #f0f2f5; }
        h1, h2 { text-align: center; }
        table { width: 100%; border-collapse: collapse; margin-bottom: 20px; background: white; border-radius: 12px; overflow: hidden; }
        th, td { padding: 12px; border-bottom: 1px solid #eee; text-align: center; }
        th { background: #007bff; color: white; }
        tr:hover { background-color: #f9f9f9; }
        .scroll-box { max-height: 400px; overflow-y: auto; margin-bottom: 20px; }
        button { padding:
