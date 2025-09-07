from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_sqlalchemy import SQLAlchemy
import os, json, jwt, random
from datetime import datetime
from collections import defaultdict

app = Flask(__name__)

# ---------------- Config ----------------
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', 
    'postgresql://postgres:TzfCyZkvUbFomVpqfRMMeQppGvBjxths@postgres.railway.internal:5432/railway'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

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

# ---------------- DB ----------------
db = SQLAlchemy(app)

class Transaction(db.Model):
    id = db.Column(db.String, primary_key=True)
    event = db.Column(db.String)
    amount = db.Column(db.Integer)
    name = db.Column(db.String)
    bank = db.Column(db.String)
    status = db.Column(db.String, default="new")  # new / approved / cancelled
    time = db.Column(db.DateTime, default=datetime.utcnow)
    approver_name = db.Column(db.String)
    approved_time = db.Column(db.DateTime)
    canceler_name = db.Column(db.String)
    cancelled_time = db.Column(db.DateTime)
    customer_user = db.Column(db.String)
    slip_filename = db.Column(db.String)

db.create_all()

# ---------------- Helpers ----------------
ip_approver_map = {}
daily_summary_history = defaultdict(int)

def random_english_name():
    names = ["Alice","Bob","Charlie","David","Eve","Frank","Grace","Hannah","Ian","Jack","Kathy","Leo","Mia","Nina","Oscar"]
    return random.choice(names)

def fmt_amount(a):
    return f"{a/100:,.2f}" if isinstance(a,(int,float,int)) else str(a)

def fmt_time(dt):
    if not dt:
        return "-"
    if isinstance(dt, str):
        return dt[:19].replace("T"," ")
    return dt.strftime("%Y-%m-%d %H:%M:%S")

# ---------------- Routes ----------------
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

    # daily summary
    daily_summary_history.clear()
    for tx in Transaction.query.filter_by(status="approved").all():
        day = tx.time.strftime("%Y-%m-%d")
        daily_summary_history[day] += tx.amount

    return jsonify({
        "new_orders":[
            {"id":tx.id,"event":tx.event,"amount_str":fmt_amount(tx.amount),"name":tx.name,
             "time_str":fmt_time(tx.time),"bank":tx.bank,"slip_url":f"/slip/{tx.id}" if tx.slip_filename else None}
            for tx in new_orders
        ],
        "approved_orders":[
            {"id":tx.id,"event":tx.event,"amount_str":fmt_amount(tx.amount),"name":tx.name,
             "time_str":fmt_time(tx.time),"bank":tx.bank,"approver_name":tx.approver_name,
             "approved_time_str":fmt_time(tx.approved_time),"customer_user":tx.customer_user,
             "slip_url":f"/slip/{tx.id}" if tx.slip_filename else None}
            for tx in approved_orders
        ],
        "cancelled_orders":[
            {"id":tx.id,"event":tx.event,"amount_str":fmt_amount(tx.amount),"name":tx.name,
             "time_str":fmt_time(tx.time),"bank":tx.bank,"canceler_name":tx.canceler_name,
             "cancelled_time_str":fmt_time(tx.cancelled_time)}
            for tx in cancelled_orders
        ],
        "wallet_daily_total":fmt_amount(wallet_daily_total),
        "daily_summary":[{"date":d,"total":fmt_amount(v)} for d,v in sorted(daily_summary_history.items())]
    })

# ---------------- Approve / Cancel / Restore ----------------
@app.route("/approve", methods=["POST"])
def approve():
    data = request.json
    txid = data.get("id")
    customer_user = data.get("customer_user")
    tx = Transaction.query.get(txid)
    if not tx:
        return jsonify({"status":"error","message":"Transaction not found"}),404

    user_ip = request.remote_addr or "unknown"
    if user_ip not in ip_approver_map:
        ip_approver_map[user_ip] = random_english_name()
    tx.approver_name = ip_approver_map[user_ip]
    tx.approved_time = datetime.utcnow()
    tx.customer_user = customer_user
    tx.status = "approved"
    db.session.commit()
    return jsonify({"status":"success"})

@app.route("/cancel", methods=["POST"])
def cancel():
    data = request.json
    txid = data.get("id")
    tx = Transaction.query.get(txid)
    if not tx:
        return jsonify({"status":"error","message":"Transaction not found"}),404
    user_ip = request.remote_addr or "unknown"
    if user_ip not in ip_approver_map:
        ip_approver_map[user_ip] = random_english_name()
    tx.canceler_name = ip_approver_map[user_ip]
    tx.cancelled_time = datetime.utcnow()
    tx.status = "cancelled"
    db.session.commit()
    return jsonify({"status":"success"})

@app.route("/restore", methods=["POST"])
def restore():
    data = request.json
    txid = data.get("id")
    tx = Transaction.query.get(txid)
    if not tx:
        return jsonify({"status":"error","message":"Transaction not found"}),404
    tx.status = "new"
    tx.approver_name = None
    tx.approved_time = None
    tx.canceler_name = None
    tx.cancelled_time = None
    tx.customer_user = None
    db.session.commit()
    return jsonify({"status":"success"})

@app.route("/reset_approved", methods=["POST"])
def reset_approved():
    for tx in Transaction.query.filter_by(status="approved").all():
        tx.status = "new"
        tx.approver_name = None
        tx.approved_time = None
        tx.customer_user = None
    db.session.commit()
    return jsonify({"status":"success"})

@app.route("/reset_cancelled", methods=["POST"])
def reset_cancelled():
    for tx in Transaction.query.filter_by(status="cancelled").all():
        tx.status = "new"
        tx.canceler_name = None
        tx.cancelled_time = None
    db.session.commit()
    return jsonify({"status":"success"})

# ---------------- Webhook TrueWallet ----------------
@app.route("/truewallet/webhook", methods=["POST"])
def truewallet_webhook():
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"status":"error","message":"No JSON received"}), 400

    message_jwt = data.get("message")
    decoded = {}
    if message_jwt:
        try:
            decoded = jwt.decode(message_jwt, SECRET_KEY, algorithms=["HS256"])
        except Exception as e:
            return jsonify({"status":"error","message":"Invalid JWT"}), 400
    else:
        decoded = data

    txid = decoded.get("transaction_id") or f"TX{random.randint(100000,999999)}"
    if Transaction.query.get(txid):
        return jsonify({"status":"success","message":"Transaction exists"})

    amount = int(decoded.get("amount",0))
    sender_name = decoded.get("sender_name","-")
    sender_mobile = decoded.get("sender_mobile","-")
    name = f"{sender_name} / {sender_mobile}" if sender_mobile else sender_name
    event_type = decoded.get("event_type","ฝาก").upper()
    bank_code = (decoded.get("channel") or "").upper()

    if event_type=="P2P" or bank_code in ["TRUEWALLET","WALLET"]:
        bank_name_th="ทรูวอเลท"
    elif bank_code in BANK_MAP_TH:
        bank_name_th=BANK_MAP_TH[bank_code]
    elif bank_code:
        bank_name_th=bank_code
    else:
        bank_name_th="-"

    time_str = decoded.get("received_time") or datetime.utcnow().isoformat()
    try:
        tx_time = datetime.fromisoformat(time_str[:19])
    except:
        tx_time = datetime.utcnow()

    tx = Transaction(
        id=txid,event=event_type,amount=amount,name=name,bank=bank_name_th,time=tx_time,status="new"
    )
    db.session.add(tx)
    db.session.commit()
    return jsonify({"status":"success"}),200

# ---------------- Upload / View Slip ----------------
@app.route("/upload_slip/<txid>", methods=["POST"])
def upload_slip(txid):
    tx = Transaction.query.get(txid)
    if not tx:
        return jsonify({"status":"error","message":"Transaction not found"}),404
    if 'file' not in request.files:
        return jsonify({"status":"error","message":"No file"}),400
    file = request.files['file']
    filename = f"{txid}_{int(datetime.utcnow().timestamp())}_{file.filename}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    tx.slip_filename = filename
    db.session.commit()
    return jsonify({"status":"success"})

@app.route("/slip/<txid>")
def view_slip(txid):
    tx = Transaction.query.get(txid)
    if not tx or not tx.slip_filename:
        return "ไม่มีสลิป",404
    return send_from_directory(app.config['UPLOAD_FOLDER'], tx.slip_filename)

# ---------------- Run App ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",8080)), debug=True)
