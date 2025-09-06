from flask import Flask, request, jsonify, render_template
import json, os
from datetime import datetime, timedelta

app = Flask(__name__)

# เก็บรายการทั้งหมด
transactions = {
    "new": [],
    "approved": [],
    "cancelled": []
}

# ฟังก์ชันแปลงเวลาไทย (GMT+7)
def to_thai_time(dt: datetime):
    if not dt:
        return "-"
    thai_dt = dt + timedelta(hours=7)
    return thai_dt.strftime("%Y-%m-%d %H:%M:%S")

# หน้าเว็บหลัก
@app.route("/")
def index():
    user_ip = request.remote_addr
    return render_template("index.html", user_ip=user_ip)

# รับ Webhook
@app.route("/truewallet/webhook", methods=["POST"])
def truewallet_webhook():
    data = request.json if request.is_json else request.form.to_dict()
    print(f"[{datetime.now()}] [WEBHOOK RECEIVED] {data}")

    tx = {
        "id": data.get("id", f"TX{len(transactions['new'])+1}"),
        "event": data.get("event", "-"),
        "amount": float(data.get("amount", 0)),
        "amount_str": f"{float(data.get('amount',0)):,.2f}",
        "name": data.get("name", "-"),
        "bank": data.get("bank", "-"),
        "status": "new",
        "time": datetime.now(),
        "time_str": to_thai_time(datetime.now())
    }
    transactions["new"].append(tx)
    return jsonify({"status": "success"})

# ดึงข้อมูลทั้งหมด
@app.route("/get_transactions")
def get_transactions():
    daily_summary = []
    wallet_daily_total = sum(t["amount"] for t in transactions["new"])

    return jsonify({
        "wallet_daily_total": f"{wallet_daily_total:,.2f}",
        "daily_summary": daily_summary,
        "new_orders": [
            {**t, "time_str": to_thai_time(t["time"])} for t in transactions["new"]
        ],
        "approved_orders": [
            {
                **t,
                "time_str": to_thai_time(t["time"]),
                "approved_time_str": to_thai_time(t.get("approved_time"))
            }
            for t in transactions["approved"]
        ],
        "cancelled_orders": [
            {
                **t,
                "time_str": to_thai_time(t["time"]),
                "cancelled_time_str": to_thai_time(t.get("cancelled_time"))
            }
            for t in transactions["cancelled"]
        ]
    })

# อนุมัติ
@app.route("/approve", methods=["POST"])
def approve():
    data = request.json
    txid = data.get("id")
    customer_user = data.get("customer_user", "-")
    for t in transactions["new"]:
        if t["id"] == txid:
            t["status"] = "approved"
            t["approver_name"] = "Admin"
            t["approved_time"] = datetime.now()
            t["customer_user"] = customer_user
            transactions["approved"].append(t)
            transactions["new"].remove(t)
            break
    return jsonify({"status": "ok"})

# ยกเลิก
@app.route("/cancel", methods=["POST"])
def cancel():
    data = request.json
    txid = data.get("id")
    for t in transactions["new"]:
        if t["id"] == txid:
            t["status"] = "cancelled"
            t["canceler_name"] = "Admin"
            t["cancelled_time"] = datetime.now()
            transactions["cancelled"].append(t)
            transactions["new"].remove(t)
            break
    return jsonify({"status": "ok"})

# คืนกลับเป็น New
@app.route("/restore", methods=["POST"])
def restore():
    data = request.json
    txid = data.get("id")
    for t in transactions["approved"][:]:
        if t["id"] == txid:
            t["status"] = "new"
            transactions["new"].append(t)
            transactions["approved"].remove(t)
            return jsonify({"status": "ok"})
    for t in transactions["cancelled"][:]:
        if t["id"] == txid:
            t["status"] = "new"
            transactions["new"].append(t)
            transactions["cancelled"].remove(t)
            return jsonify({"status": "ok"})
    return jsonify({"status": "not_found"})

# รีเซท
@app.route("/reset_approved", methods=["POST"])
def reset_approved():
    transactions["approved"].clear()
    return jsonify({"status": "ok"})

@app.route("/reset_cancelled", methods=["POST"])
def reset_cancelled():
    transactions["cancelled"].clear()
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
