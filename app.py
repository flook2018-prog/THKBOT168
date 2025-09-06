from flask import Flask, request, jsonify, render_template
import os, json
from datetime import datetime
from collections import defaultdict

app = Flask(__name__)

# เก็บรายการธุรกรรม
transactions = {
    "new": [],
    "approved": [],
    "cancelled": []
}

# ฟังก์ชัน helper แปลงเป็น string
def fmt_time(dt):
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return str(dt)

def fmt_amount(amount):
    try:
        return f"{float(amount):,.2f}"
    except:
        return str(amount)

@app.route("/")
def index():
    user_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    return render_template("index.html", user_ip=user_ip)

@app.route("/truewallet/webhook", methods=["POST"])
def truewallet_webhook():
    data = request.json or {}
    print(f"[WEBHOOK RECEIVED] {data}", flush=True)

    tx = {
        "id": data.get("id", f"TX{len(transactions['new'])+1}"),
        "event": data.get("event", "-"),
        "amount": data.get("amount", 0),
        "amount_str": fmt_amount(data.get("amount", 0)),
        "name": data.get("name", "-"),
        "bank": data.get("bank", "-"),
        "status": "new",
        "time": data.get("time", datetime.utcnow()),
        "time_str": fmt_time(data.get("time", datetime.utcnow()))
    }

    transactions["new"].append(tx)
    return jsonify({"status": "success", "received": tx}), 200

@app.route("/get_transactions")
def get_transactions():
    # รวมยอด Wallet วันนี้
    today = datetime.utcnow().strftime("%Y-%m-%d")
    wallet_daily_total = sum(
        tx["amount"] for tx in transactions["approved"]
        if tx.get("time_str", "").startswith(today)
    )

    # daily summary
    summary = defaultdict(float)
    for tx in transactions["approved"]:
        if "time_str" in tx and tx["time_str"]:
            day = tx["time_str"].split(" ")[0]
            summary[day] += tx["amount"]

    daily_summary = [{"date": d, "total": fmt_amount(a)} for d, a in summary.items()]

    return jsonify({
        "wallet_daily_total": fmt_amount(wallet_daily_total),
        "daily_summary": daily_summary,
        "new_orders": transactions["new"],
        "approved_orders": transactions["approved"],
        "cancelled_orders": transactions["cancelled"]
    })

@app.route("/approve", methods=["POST"])
def approve():
    data = request.json
    tx_id = data.get("id")
    customer_user = data.get("customer_user")
    approver_name = "admin"

    for tx in transactions["new"]:
        if tx["id"] == tx_id:
            tx["status"] = "approved"
            tx["approver_name"] = approver_name
            tx["approved_time_str"] = fmt_time(datetime.utcnow())
            tx["customer_user"] = customer_user
            transactions["approved"].append(tx)
            transactions["new"].remove(tx)
            break
    return jsonify({"status": "ok"})

@app.route("/cancel", methods=["POST"])
def cancel():
    data = request.json
    tx_id = data.get("id")
    canceler_name = "admin"

    for tx in transactions["new"]:
        if tx["id"] == tx_id:
            tx["status"] = "cancelled"
            tx["canceler_name"] = canceler_name
            tx["cancelled_time_str"] = fmt_time(datetime.utcnow())
            transactions["cancelled"].append(tx)
            transactions["new"].remove(tx)
            break
    return jsonify({"status": "ok"})

@app.route("/restore", methods=["POST"])
def restore():
    data = request.json
    tx_id = data.get("id")

    for group in ["approved", "cancelled"]:
        for tx in transactions[group]:
            if tx["id"] == tx_id:
                tx["status"] = "new"
                if "approver_name" in tx: tx.pop("approver_name")
                if "approved_time_str" in tx: tx.pop("approved_time_str")
                if "canceler_name" in tx: tx.pop("canceler_name")
                if "cancelled_time_str" in tx: tx.pop("cancelled_time_str")
                if "customer_user" in tx: tx.pop("customer_user")
                transactions["new"].append(tx)
                transactions[group].remove(tx)
                break
    return jsonify({"status": "ok"})

@app.route("/reset_approved", methods=["POST"])
def reset_approved():
    transactions["approved"].clear()
    return jsonify({"status": "reset approved"})

@app.route("/reset_cancelled", methods=["POST"])
def reset_cancelled():
    transactions["cancelled"].clear()
    return jsonify({"status": "reset cancelled"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
