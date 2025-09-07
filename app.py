from flask import Flask, request, jsonify, render_template, send_file
import os, json, jwt, random
from datetime import datetime, timedelta
from collections import defaultdict
from io import BytesIO
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# -------------------- Database Setup --------------------
POSTGRES_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:password@localhost:5432/railway")
app.config['SQLALCHEMY_DATABASE_URI'] = POSTGRES_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# -------------------- Models --------------------
class Transaction(db.Model):
    __tablename__ = "transactions"
    id = db.Column(db.String, primary_key=True)
    event = db.Column(db.String)
    amount = db.Column(db.Integer)
    name = db.Column(db.String)
    bank = db.Column(db.String)
    status = db.Column(db.String)
    time = db.Column(db.DateTime)
    approved_time = db.Column(db.DateTime, nullable=True)
    approver_name = db.Column(db.String, nullable=True)
    cancelled_time = db.Column(db.DateTime, nullable=True)
    canceler_name = db.Column(db.String, nullable=True)
    customer_user = db.Column(db.String, nullable=True)
    slip_data = db.Column(db.LargeBinary, nullable=True)
    slip_filename = db.Column(db.String, nullable=True)

db.create_all()

# -------------------- Globals --------------------
SECRET_KEY = "f557ff6589e6d075581d68df1d4f3af7"
ip_approver_map = {}
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

# -------------------- Helpers --------------------
def fmt_amount(a):
    return f"{a/100:,.2f}" if isinstance(a,(int,float,int)) else str(a)

def random_english_name():
    names = ["Alice","Bob","Charlie","David","Eve","Frank","Grace","Hannah","Ian","Jack","Kathy","Leo","Mia","Nina","Oscar"]
    return random.choice(names)

def log_with_time(*args):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    msg = f"[{ts}] " + " ".join(str(a) for a in args)
    print(msg, flush=True)

# -------------------- Flask Endpoints --------------------
@app.route("/")
def index():
    user_ip = request.remote_addr or "unknown"
    return render_template("index.html", user_ip=user_ip)

@app.route("/get_transactions")
def get_transactions():
    txs_new = Transaction.query.filter_by(status="new").order_by(Transaction.time.desc()).limit(20).all()
    txs_approved = Transaction.query.filter_by(status="approved").order_by(Transaction.approved_time.desc()).limit(20).all()
    txs_cancelled = Transaction.query.filter_by(status="cancelled").order_by(Transaction.cancelled_time.desc()).limit(20).all()

    wallet_total = sum(tx.amount for tx in txs_approved)
    wallet_total_str = fmt_amount(wallet_total)

    def tx_to_dict(tx, approved=False, cancelled=False):
        return {
            "id": tx.id,
            "event": tx.event,
            "amount": tx.amount,
            "amount_str": fmt_amount(tx.amount),
            "name": tx.name,
            "bank": tx.bank,
            "status": tx.status,
            "time_str": tx.time.strftime("%Y-%m-%d %H:%M:%S") if tx.time else "-",
            "approved_time_str": tx.approved_time.strftime("%Y-%m-%d %H:%M:%S") if approved and tx.approved_time else "-",
            "approver_name": tx.approver_name if approved else "-",
            "cancelled_time_str": tx.cancelled_time.strftime("%Y-%m-%d %H:%M:%S") if cancelled and tx.cancelled_time else "-",
            "canceler_name": tx.canceler_name if cancelled else "-",
            "customer_user": tx.customer_user if approved else "-",
            "slip_uploaded": bool(tx.slip_data)
        }

    return jsonify({
        "new_orders": [tx_to_dict(tx) for tx in txs_new],
        "approved_orders": [tx_to_dict(tx, approved=True) for tx in txs_approved],
        "cancelled_orders": [tx_to_dict(tx, cancelled=True) for tx in txs_cancelled],
        "wallet_daily_total": wallet_total_str,
        "daily_summary": []  # สามารถคำนวณเพิ่มได้
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
        tx.approver_name = approver_name
        tx.approved_time = datetime.now()
        tx.customer_user = customer_user
        db.session.commit()
        log_with_time(f"[APPROVED] {txid} by {approver_name} ({user_ip})")
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
        tx.cancelled_time = datetime.now()
        db.session.commit()
        log_with_time(f"[CANCELLED] {txid} by {canceler_name} ({user_ip})")
    return jsonify({"status":"success"})

@app.route("/restore", methods=["POST"])
def restore():
    txid = request.json.get("id")
    tx = Transaction.query.get(txid)
    if tx:
        tx.status = "new"
        tx.approver_name = None
        tx.approved_time = None
        tx.canceler_name = None
        tx.cancelled_time = None
        tx.customer_user = None
        db.session.commit()
        log_with_time(f"[RESTORED] {txid}")
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

        txid = decoded.get("transaction_id") or f"TX{int(datetime.now().timestamp()*1000)}"
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

        time_str = decoded.get("received_time") or datetime.now().isoformat()
        try:
            tx_time = datetime.fromisoformat(time_str[:19])
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
        return jsonify({"status":"success"})
    except Exception as e:
        return jsonify({"status":"error","message":str(e)}),500

# -------------------- Upload / Get Slip --------------------
@app.route("/upload_slip/<txid>", methods=["POST"])
def upload_slip(txid):
    tx = Transaction.query.get(txid)
    if not tx:
        return jsonify({"status":"error","message":"Transaction not found"}),404
    if "file" not in request.files:
        return jsonify({"status":"error","message":"No file part"}),400
    file = request.files["file"]
    if file.filename=="":
        return jsonify({"status":"error","message":"No selected file"}),400
    tx.slip_data = file.read()
    tx.slip_filename = secure_filename(file.filename)
    db.session.commit()
    return jsonify({"status":"success","filename":tx.slip_filename})

@app.route("/slip/<txid>")
def get_slip(txid):
    tx = Transaction.query.get(txid)
    if not tx or not tx.slip_data:
        return "Not found",404
    return send_file(BytesIO(tx.slip_data), download_name=tx.slip_filename)

# -------------------- Automatic DB Cleanup (2 months) --------------------
@app.before_request
def cleanup_old_transactions():
    threshold = datetime.now() - timedelta(days=60)
    old_txs = Transaction.query.filter(Transaction.time < threshold).all()
    for tx in old_txs:
        db.session.delete(tx)
    db.session.commit()

# -------------------- Run App --------------------
if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",8080)), debug=True)
