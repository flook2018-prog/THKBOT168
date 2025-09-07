from flask import Flask, request, jsonify, render_template, send_file
from flask_sqlalchemy import SQLAlchemy
import os, json, jwt, random, io, base64
from datetime import datetime, timedelta
from collections import defaultdict

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL",
    "sqlite:///transactions.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
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

db = SQLAlchemy(app)

# -------------------- Database Model --------------------
class Transaction(db.Model):
    id = db.Column(db.String, primary_key=True)
    event = db.Column(db.String)
    amount = db.Column(db.Integer)
    name = db.Column(db.String)
    bank = db.Column(db.String)
    status = db.Column(db.String)  # new / approved / cancelled
    time = db.Column(db.DateTime)
    approved_time = db.Column(db.DateTime, nullable=True)
    approver_name = db.Column(db.String, nullable=True)
    cancelled_time = db.Column(db.DateTime, nullable=True)
    canceler_name = db.Column(db.String, nullable=True)
    customer_user = db.Column(db.String, nullable=True)
    slip_data = db.Column(db.LargeBinary, nullable=True)
    slip_filename = db.Column(db.String, nullable=True)

with app.app_context():
    db.create_all()

# -------------------- Helpers --------------------
ip_approver_map = {}
daily_summary_history = defaultdict(int)

def random_english_name():
    names = ["Alice","Bob","Charlie","David","Eve","Frank","Grace","Hannah","Ian","Jack","Kathy","Leo","Mia","Nina","Oscar"]
    return random.choice(names)

def fmt_time(t):
    return t.strftime("%Y-%m-%d %H:%M:%S") if t else "-"

def fmt_amount(a):
    return f"{a/100:,.2f}" if a else "0.00"

def cleanup_old_transactions():
    """ลบข้อมูลเก่าที่เกิน 2 เดือน"""
    two_months_ago = datetime.now() - timedelta(days=60)
    old_tx = Transaction.query.filter(Transaction.time < two_months_ago).all()
    for tx in old_tx:
        db.session.delete(tx)
    db.session.commit()

# -------------------- Routes --------------------
@app.route("/")
def index():
    user_ip = request.remote_addr or "unknown"
    cleanup_old_transactions()
    return render_template("index.html", user_ip=user_ip)

@app.route("/get_transactions")
def get_transactions():
    transactions_new = Transaction.query.filter_by(status="new").order_by(Transaction.time.desc()).limit(20).all()
    transactions_approved = Transaction.query.filter_by(status="approved").order_by(Transaction.approved_time.desc()).limit(20).all()
    transactions_cancelled = Transaction.query.filter_by(status="cancelled").order_by(Transaction.cancelled_time.desc()).limit(20).all()

    wallet_daily_total = sum(tx.amount for tx in transactions_approved)

    daily_summary = defaultdict(int)
    for tx in transactions_approved:
        day = tx.time.strftime("%Y-%m-%d")
        daily_summary[day] += tx.amount

    def serialize(tx):
        return {
            "id": tx.id,
            "event": tx.event,
            "amount": tx.amount,
            "amount_str": fmt_amount(tx.amount),
            "name": tx.name,
            "bank": tx.bank,
            "status": tx.status,
            "time_str": fmt_time(tx.time),
            "approved_time_str": fmt_time(tx.approved_time),
            "approver_name": tx.approver_name,
            "cancelled_time_str": fmt_time(tx.cancelled_time),
            "canceler_name": tx.canceler_name,
            "customer_user": tx.customer_user,
            "has_slip": bool(tx.slip_data),
        }

    return jsonify({
        "new_orders": [serialize(tx) for tx in transactions_new],
        "approved_orders": [serialize(tx) for tx in transactions_approved],
        "cancelled_orders": [serialize(tx) for tx in transactions_cancelled],
        "wallet_daily_total": fmt_amount(wallet_daily_total),
        "daily_summary": [{"date": d, "total": fmt_amount(v)} for d,v in sorted(daily_summary.items())]
    })

# -------------------- Approve / Cancel / Restore --------------------
@app.route("/approve", methods=["POST"])
def approve():
    data = request.json
    tx = Transaction.query.filter_by(id=data["id"]).first()
    if not tx:
        return jsonify({"status":"error","message":"Transaction not found"}), 404

    user_ip = request.remote_addr or "unknown"
    if user_ip not in ip_approver_map:
        ip_approver_map[user_ip] = random_english_name()

    tx.status = "approved"
    tx.approver_name = ip_approver_map[user_ip]
    tx.approved_time = datetime.now()
    tx.customer_user = data.get("customer_user")
    db.session.commit()
    return jsonify({"status":"success"})

@app.route("/cancel", methods=["POST"])
def cancel():
    data = request.json
    tx = Transaction.query.filter_by(id=data["id"]).first()
    if not tx:
        return jsonify({"status":"error","message":"Transaction not found"}), 404

    user_ip = request.remote_addr or "unknown"
    if user_ip not in ip_approver_map:
        ip_approver_map[user_ip] = random_english_name()

    tx.status = "cancelled"
    tx.canceler_name = ip_approver_map[user_ip]
    tx.cancelled_time = datetime.now()
    db.session.commit()
    return jsonify({"status":"success"})

@app.route("/restore", methods=["POST"])
def restore():
    data = request.json
    tx = Transaction.query.filter_by(id=data["id"]).first()
    if not tx:
        return jsonify({"status":"error","message":"Transaction not found"}), 404
    tx.status = "new"
    tx.approver_name = None
    tx.approved_time = None
    tx.canceler_name = None
    tx.cancelled_time = None
    tx.customer_user = None
    db.session.commit()
    return jsonify({"status":"success"})

# -------------------- Upload / Get Slip --------------------
@app.route("/upload_slip/<txid>", methods=["POST"])
def upload_slip(txid):
    if "file" not in request.files:
        return jsonify({"status":"error","message":"No file part"}), 400
    file = request.files["file"]
    if file.filename=="":
        return jsonify({"status":"error","message":"No selected file"}), 400
    tx = Transaction.query.filter_by(id=txid).first()
    if not tx:
        return jsonify({"status":"error","message":"Transaction not found"}), 404

    tx.slip_data = file.read()
    tx.slip_filename = file.filename
    db.session.commit()
    return jsonify({"status":"success"})

@app.route("/slip/<txid>")
def get_slip(txid):
    tx = Transaction.query.filter_by(id=txid).first()
    if not tx or not tx.slip_data:
        return "Not Found", 404
    return send_file(io.BytesIO(tx.slip_data), download_name=tx.slip_filename)

# -------------------- Webhook --------------------
@app.route("/truewallet/webhook", methods=["POST"])
def truewallet_webhook():
    try:
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({"status":"error","message":"No JSON received"}), 400

        message_jwt = data.get("message")
        decoded = {}
        if message_jwt:
            decoded = jwt.decode(message_jwt, SECRET_KEY, algorithms=["HS256"])
        else:
            decoded = data

        txid = decoded.get("transaction_id") or f"TX{Transaction.query.count()+1}"
        if Transaction.query.filter_by(id=txid).first():
            return jsonify({"status":"success","message":"Transaction exists"}), 200

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

        time_str = decoded.get("received_time") or datetime.now().isoformat()
        try:
            tx_time = datetime.strptime(time_str[:19], "%Y-%m-%dT%H:%M:%S")
        except:
            tx_time = datetime.now()

        tx = Transaction(
            id=txid,
            event=event_type,
            amount=amount,
            name=name,
            bank=bank_name_th,
            status="new",
            time=tx_time
        )
        db.session.add(tx)
        db.session.commit()
        return jsonify({"status":"success"}), 200
    except Exception as e:
        return jsonify({"status":"error","message":str(e)}), 500

# -------------------- Run App --------------------
if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",8080)), debug=True)
