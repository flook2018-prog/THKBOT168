from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
import os, json, jwt, random
from datetime import datetime, timedelta
from collections import defaultdict

# -------------------- Config --------------------
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:password@localhost:5432/railway"
)
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

# -------------------- Database Models --------------------
class Transaction(db.Model):
    __tablename__ = "transactions"
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
    slip_filename = db.Column(db.String, nullable=True)

db.create_all()

# -------------------- Helpers --------------------
ip_approver_map = {}

def random_english_name():
    names = ["Alice","Bob","Charlie","David","Eve","Frank","Grace","Hannah","Ian","Jack","Kathy","Leo","Mia","Nina","Oscar"]
    return random.choice(names)

def fmt_amount(a):
    return f"{a/100:,.2f}" if isinstance(a,(int,float,int)) else str(a)

def fmt_time_th(dt):
    if not dt: return "-"
    # แสดงเวลาไทย
    return (dt + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S")

def clean_old_transactions():
    # ลบ transaction เก่ากว่า 2 เดือน
    threshold = datetime.utcnow() - timedelta(days=60)
    old_tx = Transaction.query.filter(Transaction.time < threshold).all()
    for tx in old_tx:
        # ลบไฟล์สลิปด้วย
        if tx.slip_filename:
            try:
                os.remove(os.path.join(UPLOAD_FOLDER, tx.slip_filename))
            except: pass
        db.session.delete(tx)
    db.session.commit()

# -------------------- Routes --------------------
@app.route("/")
def index():
    user_ip = request.remote_addr or "unknown"
    return render_template("index.html", user_ip=user_ip)

@app.route("/get_transactions")
def get_transactions():
    clean_old_transactions()
    new_orders = Transaction.query.filter_by(status="new").order_by(Transaction.time.desc()).limit(20).all()
    approved_orders = Transaction.query.filter_by(status="approved").order_by(Transaction.approved_time.desc()).limit(20).all()
    cancelled_orders = Transaction.query.filter_by(status="cancelled").order_by(Transaction.cancelled_time.desc()).limit(20).all()

    wallet_daily_total = sum(tx.amount for tx in approved_orders)
    wallet_daily_total_str = fmt_amount(wallet_daily_total)

    daily_summary = defaultdict(int)
    for tx in Transaction.query.filter_by(status="approved").all():
        day = (tx.time + timedelta(hours=7)).strftime("%Y-%m-%d")
        daily_summary[day] += tx.amount

    # แปลงข้อมูลเป็น dict สำหรับ JSON
    def serialize(tx, approved=False, cancelled=False):
        return {
            "id": tx.id,
            "event": tx.event,
            "amount": tx.amount,
            "amount_str": fmt_amount(tx.amount),
            "name": tx.name,
            "bank": tx.bank,
            "status": tx.status,
            "time_str": fmt_time_th(tx.time),
            "approved_time_str": fmt_time_th(tx.approved_time) if approved else None,
            "cancelled_time_str": fmt_time_th(tx.cancelled_time) if cancelled else None,
            "approver_name": tx.approver_name,
            "canceler_name": tx.canceler_name,
            "customer_user": tx.customer_user,
            "slip_filename": tx.slip_filename
        }

    return jsonify({
        "new_orders": [serialize(tx) for tx in new_orders],
        "approved_orders": [serialize(tx, approved=True) for tx in approved_orders],
        "cancelled_orders": [serialize(tx, cancelled=True) for tx in cancelled_orders],
        "wallet_daily_total": wallet_daily_total_str,
        "daily_summary": [{"date": d, "total": fmt_amount(v)} for d,v in sorted(daily_summary.items())]
    })

# -------------------- Approve / Cancel --------------------
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
        tx.approver_name = approver_name
        tx.approved_time = datetime.utcnow()
        tx.customer_user = customer_user
        db.session.commit()
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
        tx.cancelled_time = datetime.utcnow()
        db.session.commit()
    return jsonify({"status":"success"})

# -------------------- Restore / Reset --------------------
@app.route("/restore", methods=["POST"])
def restore():
    txid = request.json.get("id")
    tx = Transaction.query.get(txid)
    if tx and tx.status in ["approved","cancelled"]:
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
    approved = Transaction.query.filter_by(status="approved").all()
    for tx in approved:
        tx.status="new"
        tx.approver_name=None
        tx.approved_time=None
        tx.customer_user=None
    db.session.commit()
    return jsonify({"status":"success"})

@app.route("/reset_cancelled", methods=["POST"])
def reset_cancelled():
    cancelled = Transaction.query.filter_by(status="cancelled").all()
    for tx in cancelled:
        tx.status="new"
        tx.canceler_name=None
        tx.cancelled_time=None
    db.session.commit()
    return jsonify({"status":"success"})

# -------------------- Webhook TrueWallet --------------------
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

        txid = decoded.get("transaction_id") or f"TX{random.randint(1000000,9999999)}"
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

        tx_time = datetime.utcnow()
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

# -------------------- Upload Slip --------------------
@app.route("/upload_slip/<txid>", methods=["POST"])
def upload_slip(txid):
    if "file" not in request.files:
        return jsonify({"status":"error","message":"No file part"}), 400
    file = request.files["file"]
    if file.filename=="":
        return jsonify({"status":"error","message":"No selected file"}), 400
    filename = f"{txid}_{secure_filename(file.filename)}"
    file.save(os.path.join(UPLOAD_FOLDER, filename))

    tx = Transaction.query.get(txid)
    if tx:
        tx.slip_filename = filename
        db.session.commit()
    return jsonify({"status":"success","filename":filename})

@app.route("/slip/<filename>")
def get_slip(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# -------------------- Run --------------------
if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",8080)), debug=True)
