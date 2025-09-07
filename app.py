from flask import Flask, request, jsonify, render_template, send_file
from flask_sqlalchemy import SQLAlchemy
import os, jwt, random, io
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename

app = Flask(__name__)
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

ip_approver_map = {}

# -------------------- Database Models --------------------
class Transaction(db.Model):
    __tablename__ = "transactions"
    id = db.Column(db.String, primary_key=True)
    event = db.Column(db.String)
    amount = db.Column(db.Integer)
    name = db.Column(db.String)
    bank = db.Column(db.String)
    status = db.Column(db.String)
    time = db.Column(db.DateTime)
    approved_time = db.Column(db.DateTime)
    cancel_time = db.Column(db.DateTime)
    approver_name = db.Column(db.String)
    canceler_name = db.Column(db.String)
    customer_user = db.Column(db.String)
    slip_filename = db.Column(db.String)
    slip_data = db.Column(db.LargeBinary)

db.create_all()

# -------------------- Helpers --------------------
def fmt_amount(a):
    return f"{a/100:,.2f}" if a is not None else "0.00"

def fmt_time(t):
    return t.strftime("%Y-%m-%d %H:%M:%S") if t else "-"

def cleanup_old_transactions():
    threshold = datetime.utcnow() - timedelta(days=60)
    old_tx = Transaction.query.filter(Transaction.time < threshold).all()
    for tx in old_tx:
        db.session.delete(tx)
    db.session.commit()

# -------------------- Flask Endpoints --------------------
@app.route("/")
def index():
    user_ip = request.remote_addr or "unknown"
    return render_template("index.html", user_ip=user_ip)

@app.route("/get_transactions")
def get_transactions():
    cleanup_old_transactions()
    new_orders = Transaction.query.filter_by(status="new").order_by(Transaction.time.desc()).limit(20).all()
    approved_orders = Transaction.query.filter_by(status="approved").order_by(Transaction.approved_time.desc()).limit(20).all()
    cancelled_orders = Transaction.query.filter_by(status="cancelled").order_by(Transaction.cancel_time.desc()).limit(20).all()

    wallet_daily_total = sum(tx.amount for tx in approved_orders)
    daily_summary = {}
    for tx in approved_orders:
        day = tx.time.strftime("%Y-%m-%d")
        daily_summary[day] = daily_summary.get(day, 0) + tx.amount

    return jsonify({
        "new_orders": [{
            "id": tx.id,
            "event": tx.event,
            "amount_str": fmt_amount(tx.amount),
            "name": tx.name,
            "bank": tx.bank,
            "time_str": fmt_time(tx.time)
        } for tx in new_orders],
        "approved_orders": [{
            "id": tx.id,
            "event": tx.event,
            "amount_str": fmt_amount(tx.amount),
            "name": tx.name,
            "bank": tx.bank,
            "time_str": fmt_time(tx.time),
            "approved_time_str": fmt_time(tx.approved_time),
            "approver_name": tx.approver_name,
            "customer_user": tx.customer_user
        } for tx in approved_orders],
        "cancelled_orders": [{
            "id": tx.id,
            "event": tx.event,
            "amount_str": fmt_amount(tx.amount),
            "name": tx.name,
            "bank": tx.bank,
            "time_str": fmt_time(tx.time),
            "cancelled_time_str": fmt_time(tx.cancel_time),
            "canceler_name": tx.canceler_name
        } for tx in cancelled_orders],
        "wallet_daily_total": fmt_amount(wallet_daily_total),
        "daily_summary": [{"date": d, "total": fmt_amount(v)} for d,v in sorted(daily_summary.items())]
    })

# -------------------- Approve / Cancel --------------------
@app.route("/approve", methods=["POST"])
def approve():
    txid = request.json.get("id")
    customer_user = request.json.get("customer_user")
    user_ip = request.remote_addr or "unknown"
    if user_ip not in ip_approver_map:
        ip_approver_map[user_ip] = f"User{random.randint(100,999)}"
    approver_name = ip_approver_map[user_ip]

    tx = Transaction.query.get(txid)
    if tx and tx.status=="new":
        tx.status="approved"
        tx.approver_name=approver_name
        tx.approved_time=datetime.utcnow()
        tx.customer_user=customer_user
        db.session.commit()
    return jsonify({"status":"success"})

@app.route("/cancel", methods=["POST"])
def cancel():
    txid = request.json.get("id")
    user_ip = request.remote_addr or "unknown"
    if user_ip not in ip_approver_map:
        ip_approver_map[user_ip] = f"User{random.randint(100,999)}"
    canceler_name = ip_approver_map[user_ip]

    tx = Transaction.query.get(txid)
    if tx and tx.status=="new":
        tx.status="cancelled"
        tx.canceler_name=canceler_name
        tx.cancel_time=datetime.utcnow()
        db.session.commit()
    return jsonify({"status":"success"})

@app.route("/restore", methods=["POST"])
def restore():
    txid = request.json.get("id")
    tx = Transaction.query.get(txid)
    if tx:
        tx.status="new"
        tx.approver_name=None
        tx.approved_time=None
        tx.canceler_name=None
        tx.cancel_time=None
        tx.customer_user=None
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
        tx.cancel_time=None
    db.session.commit()
    return jsonify({"status":"success"})

# -------------------- TrueWallet Webhook --------------------
@app.route("/truewallet/webhook", methods=["POST"])
def truewallet_webhook():
    try:
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({"status":"error","message":"No JSON received"}), 400
        message_jwt = data.get("message")
        decoded = jwt.decode(message_jwt, SECRET_KEY, algorithms=["HS256"]) if message_jwt else data

        txid = decoded.get("transaction_id") or f"TX{random.randint(1000000,9999999)}"
        if Transaction.query.get(txid):
            return jsonify({"status":"success","message":"Transaction exists"}), 200

        amount = int(decoded.get("amount",0))
        sender_name = decoded.get("sender_name","-")
        sender_mobile = decoded.get("sender_mobile","-")
        name = f"{sender_name} / {sender_mobile}" if sender_mobile else sender_name
        event_type = decoded.get("event_type","ฝาก").upper()
        bank_code = (decoded.get("channel") or "").upper()
        bank_name_th = BANK_MAP_TH.get(bank_code, "ทรูวอเลท" if event_type=="P2P" else bank_code or "-")

        time_str = decoded.get("received_time") or datetime.utcnow().isoformat()
        tx_time = datetime.strptime(time_str[:19], "%Y-%m-%dT%H:%M:%S") if "T" in time_str else datetime.utcnow()

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
        return jsonify({"status":"error","message":str(e)}), 500

# -------------------- Upload Slip --------------------
@app.route("/upload_slip/<txid>", methods=["POST"])
def upload_slip(txid):
    if "file" not in request.files:
        return jsonify({"status":"error","message":"No file part"}),400
    file = request.files["file"]
    if file.filename=="":
        return jsonify({"status":"error","message":"No selected file"}),400
    tx = Transaction.query.get(txid)
    if tx:
        tx.slip_filename = secure_filename(file.filename)
        tx.slip_data = file.read()
        db.session.commit()
        return jsonify({"status":"success","filename":tx.slip_filename})
    return jsonify({"status":"error","message":"Transaction not found"}),404

@app.route("/slip/<txid>")
def get_slip(txid):
    tx = Transaction.query.get(txid)
    if tx and tx.slip_data:
        return send_file(io.BytesIO(tx.slip_data), download_name=tx.slip_filename)
    return "Slip not found",404

# -------------------- Run App --------------------
if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",8080)), debug=True)
