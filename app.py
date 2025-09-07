from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
import os, json, jwt, random
from datetime import datetime
from collections import defaultdict

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL") or "sqlite:///data.db"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

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

ip_approver_map = {}
daily_summary_history = defaultdict(float)

# ---------------- Database Models ----------------
class Transaction(db.Model):
    id = db.Column(db.String, primary_key=True)
    event = db.Column(db.String)
    amount = db.Column(db.Integer)
    name = db.Column(db.String)
    bank = db.Column(db.String)
    status = db.Column(db.String, default="new")  # new / approved / cancelled
    time = db.Column(db.String)
    customer_user = db.Column(db.String)
    approver_name = db.Column(db.String)
    approved_time = db.Column(db.String)
    canceler_name = db.Column(db.String)
    cancelled_time = db.Column(db.String)
    slip_data = db.Column(db.LargeBinary)
    slip_filename = db.Column(db.String)

db.create_all()

# -------------------- Helpers --------------------
def random_english_name():
    names = ["Alice","Bob","Charlie","David","Eve","Frank","Grace","Hannah","Ian","Jack","Kathy","Leo","Mia","Nina","Oscar"]
    return random.choice(names)

def fmt_amount(a):
    return f"{a/100:,.2f}" if isinstance(a,(int,float,int)) else str(a)

def fmt_time(t):
    return t if isinstance(t,str) else t.strftime("%Y-%m-%d %H:%M:%S")

# -------------------- Routes --------------------
@app.route("/")
def index():
    user_ip = request.remote_addr or "unknown"
    return render_template("index.html", user_ip=user_ip)

@app.route("/get_transactions")
def get_transactions():
    new_orders = Transaction.query.filter_by(status="new").order_by(Transaction.time.desc()).limit(20).all()
    approved_orders = Transaction.query.filter_by(status="approved").order_by(Transaction.approved_time.desc()).limit(20).all()
    cancelled_orders = Transaction.query.filter_by(status="cancelled").order_by(Transaction.cancelled_time.desc()).limit(20).all()
    
    wallet_daily_total = sum(tx.amount for tx in approved_orders)
    
    return jsonify({
        "new_orders": [{
            "id": tx.id,
            "event": tx.event,
            "amount_str": fmt_amount(tx.amount),
            "name": tx.name,
            "bank": tx.bank,
            "time_str": tx.time,
            "slip": bool(tx.slip_data)
        } for tx in new_orders],
        "approved_orders": [{
            "id": tx.id,
            "event": tx.event,
            "amount_str": fmt_amount(tx.amount),
            "name": tx.name,
            "bank": tx.bank,
            "customer_user": tx.customer_user,
            "approver_name": tx.approver_name,
            "approved_time_str": tx.approved_time,
            "slip": bool(tx.slip_data)
        } for tx in approved_orders],
        "cancelled_orders": [{
            "id": tx.id,
            "event": tx.event,
            "amount_str": fmt_amount(tx.amount),
            "name": tx.name,
            "bank": tx.bank,
            "canceler_name": tx.canceler_name,
            "cancelled_time_str": tx.cancelled_time,
            "slip": bool(tx.slip_data)
        } for tx in cancelled_orders],
        "wallet_daily_total": fmt_amount(wallet_daily_total),
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

    tx = Transaction.query.get(txid)
    if tx and tx.status=="new":
        tx.status = "approved"
        tx.customer_user = customer_user
        tx.approver_name = approver_name
        tx.approved_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.session.commit()
        day = tx.time[:10]
        daily_summary_history[day] += tx.amount
    return jsonify({"status":"success"})

@app.route("/cancel", methods=["POST"])
def cancel():
    txid = request.json.get("id")
    user_ip = request.remote_addr or "unknown"
    if user_ip not in ip_approver_map:
        ip_approver_map[user_ip] = random_english_name()
    canceler_name = ip_approver_map[user_ip]

    tx = Transaction.query.get(txid)
    if tx and tx.status=="new":
        tx.status = "cancelled"
        tx.canceler_name = canceler_name
        tx.cancelled_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.session.commit()
    return jsonify({"status":"success"})

# -------------------- Upload & View Slip --------------------
@app.route("/upload_slip/<txid>", methods=["POST"])
def upload_slip(txid):
    if "file" not in request.files:
        return jsonify({"status":"error","message":"No file part"}), 400
    file = request.files["file"]
    if file.filename=="":
        return jsonify({"status":"error","message":"No selected file"}), 400
    data = file.read()
    tx = Transaction.query.get(txid)
    if not tx:
        return jsonify({"status":"error","message":"Transaction not found"}), 404
    tx.slip_data = data
    tx.slip_filename = file.filename
    db.session.commit()
    return jsonify({"status":"success"})

@app.route("/slip/<txid>")
def get_slip(txid):
    tx = Transaction.query.get(txid)
    if not tx or not tx.slip_data:
        return "No slip found",404
    return tx.slip_data, 200, {'Content-Type':'image/jpeg'}

# -------------------- Run App --------------------
if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",8080)), debug=True)
