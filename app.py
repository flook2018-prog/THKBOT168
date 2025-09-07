from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_sqlalchemy import SQLAlchemy
import os, json, jwt, random
from datetime import datetime
from collections import defaultdict
from werkzeug.utils import secure_filename

# -------------------- Config --------------------
app = Flask(__name__)
app.config['SECRET_KEY'] = "f557ff6589e6d075581d68df1d4f3af7"
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:TzfCyZkvUbFomVpqfRMMeQppGvBjxths@postgres.railway.internal:5432/railway"
)
app.config['UPLOAD_FOLDER'] = "uploads"
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)

# -------------------- DB Models --------------------
class Transaction(db.Model):
    id = db.Column(db.String, primary_key=True)
    event = db.Column(db.String)
    amount = db.Column(db.Integer)
    name = db.Column(db.String)
    time_str = db.Column(db.String)
    bank = db.Column(db.String)
    status = db.Column(db.String, default="new")  # new, approved, cancelled
    approver_name = db.Column(db.String)
    approved_time_str = db.Column(db.String)
    canceler_name = db.Column(db.String)
    cancelled_time_str = db.Column(db.String)
    customer_user = db.Column(db.String)
    slip_filename = db.Column(db.String)

db.create_all()

# -------------------- IP -> Name --------------------
ip_approver_map = {}
names_list = ["Alice","Bob","Charlie","David","Eve","Frank","Grace","Hannah","Ian","Jack","Kathy","Leo","Mia","Nina","Oscar"]

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

def random_name(ip):
    if ip not in ip_approver_map:
        ip_approver_map[ip] = random.choice(names_list)
    return ip_approver_map[ip]

def fmt_amount(a):
    return f"{a/100:,.2f}" if isinstance(a,(int,float)) else str(a)

# -------------------- Routes --------------------
@app.route("/")
def index():
    user_ip = request.remote_addr or "unknown"
    return render_template("index.html", user_ip=user_ip)

@app.route("/get_transactions")
def get_transactions():
    transactions_db = Transaction.query.order_by(Transaction.time_str.desc()).all()
    new_orders = [tx.__dict__ for tx in transactions_db if tx.status=="new"]
    approved_orders = [tx.__dict__ for tx in transactions_db if tx.status=="approved"]
    cancelled_orders = [tx.__dict__ for tx in transactions_db if tx.status=="cancelled"]

    wallet_daily_total = sum(tx['amount'] for tx in approved_orders)
    for tx in approved_orders:
        tx['amount_str'] = fmt_amount(tx['amount'])
        tx['approved_time_str'] = tx.get('approved_time_str') or "-"

    for tx in new_orders+cancelled_orders:
        tx['amount_str'] = fmt_amount(tx['amount'])
    for tx in cancelled_orders:
        tx['cancelled_time_str'] = tx.get('cancelled_time_str') or "-"

    # daily summary
    daily_summary = defaultdict(int)
    for tx in approved_orders:
        day = tx['time_str'][:10]
        daily_summary[day] += tx['amount']

    return jsonify({
        "new_orders": new_orders,
        "approved_orders": approved_orders,
        "cancelled_orders": cancelled_orders,
        "wallet_daily_total": fmt_amount(wallet_daily_total),
        "daily_summary": [{"date": d,"total":fmt_amount(v)} for d,v in sorted(daily_summary.items())]
    })

@app.route("/approve", methods=["POST"])
def approve():
    txid = request.json.get("id")
    customer_user = request.json.get("customer_user")
    user_ip = request.remote_addr or "unknown"
    approver_name = random_name(user_ip)

    tx = Transaction.query.get(txid)
    if tx and tx.status=="new":
        tx.status = "approved"
        tx.approver_name = approver_name
        tx.approved_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tx.customer_user = customer_user
        db.session.commit()
    return jsonify({"status":"success"}),200

@app.route("/cancel", methods=["POST"])
def cancel():
    txid = request.json.get("id")
    user_ip = request.remote_addr or "unknown"
    canceler_name = random_name(user_ip)

    tx = Transaction.query.get(txid)
    if tx and tx.status=="new":
        tx.status = "cancelled"
        tx.canceler_name = canceler_name
        tx.cancelled_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.session.commit()
    return jsonify({"status":"success"}),200

@app.route("/restore", methods=["POST"])
def restore():
    txid = request.json.get("id")
    tx = Transaction.query.get(txid)
    if tx and tx.status in ["approved","cancelled"]:
        tx.status="new"
        tx.approver_name=None
        tx.approved_time_str=None
        tx.canceler_name=None
        tx.cancelled_time_str=None
        tx.customer_user=None
        db.session.commit()
    return jsonify({"status":"success"}),200

@app.route("/reset_approved", methods=["POST"])
def reset_approved():
    for tx in Transaction.query.filter_by(status="approved").all():
        tx.status="new"
        tx.approver_name=None
        tx.approved_time_str=None
        tx.customer_user=None
    db.session.commit()
    return jsonify({"status":"success"}),200

@app.route("/reset_cancelled", methods=["POST"])
def reset_cancelled():
    for tx in Transaction.query.filter_by(status="cancelled").all():
        tx.status="new"
        tx.canceler_name=None
        tx.cancelled_time_str=None
    db.session.commit()
    return jsonify({"status":"success"}),200

@app.route("/truewallet/webhook", methods=["POST"])
def truewallet_webhook():
    data = request.get_json(force=True)
    message_jwt = data.get("message")
    decoded = {}
    if message_jwt:
        try:
            decoded = jwt.decode(message_jwt, app.config['SECRET_KEY'], algorithms=["HS256"])
        except:
            return jsonify({"status":"error","message":"Invalid JWT"}),400
    else:
        decoded = data

    txid = decoded.get("transaction_id") or f"TX{random.randint(1000,9999)}"
    if Transaction.query.get(txid):
        return jsonify({"status":"success","message":"exists"}),200

    amount = int(decoded.get("amount",0))
    sender_name = decoded.get("sender_name","-")
    sender_mobile = decoded.get("sender_mobile","-")
    name = f"{sender_name} / {sender_mobile}" if sender_mobile else sender_name
    event_type = decoded.get("event_type","ฝาก").upper()
    bank_code = (decoded.get("channel") or "").upper()
    bank_name_th = BANK_MAP_TH.get(bank_code, bank_code or "-")

    time_str = decoded.get("received_time") or datetime.now().isoformat()
    tx_time = time_str[:19].replace("T"," ")

    tx = Transaction(id=txid,event=event_type,amount=amount,name=name,time_str=tx_time,bank=bank_name_th)
    db.session.add(tx)
    db.session.commit()
    return jsonify({"status":"success"}),200

# -------------------- Upload Slip --------------------
@app.route("/upload_slip/<txid>", methods=["POST"])
def upload_slip(txid):
    tx = Transaction.query.get(txid)
    if not tx: return "Not found",404
    file = request.files.get("file")
    if file:
        filename = secure_filename(f"{txid}_{file.filename}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        tx.slip_filename = filename
        db.session.commit()
    return "OK",200

@app.route("/uploads/<filename>")
def serve_slip(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# -------------------- Run --------------------
if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",8080)), debug=True)
