from flask import Flask, request, jsonify, render_template, send_from_directory
import os, json, jwt, random, re
from datetime import datetime, timedelta
from collections import defaultdict
from werkzeug.utils import secure_filename
import pytz
import psycopg2
from psycopg2.extras import RealDictCursor

# -------------------- Config --------------------
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
SECRET_KEY = "f557ff6589e6d075581d68df1d4f3af7"

TZ = pytz.timezone("Asia/Bangkok")

DATABASE_URL = os.environ.get("DATABASE_URL") or "postgresql://postgres:TzfCyZkvUbFomVpqfRMMeQppGvBjxths@postgres.railway.internal:5432/railway"
conn = psycopg2.connect(DATABASE_URL)

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
def fmt_time_local(t):
    if isinstance(t, str):
        try:
            dt = datetime.fromisoformat(t)
        except:
            return t
    elif isinstance(t, datetime):
        dt = t
    else:
        return str(t)
    return dt.astimezone(TZ).strftime("%Y-%m-%d %H:%M:%S")

def fmt_amount(a):
    return f"{a/100:,.2f}" if isinstance(a,(int,float,int)) else str(a)

def log_with_time(*args):
    ts = datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S')
    msg = f"[{ts}] " + " ".join(str(a) for a in args)
    print(msg, flush=True)

def insert_transaction(tx):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO transactions(id,event,amount,name,bank,status,time,slip_filename)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO NOTHING
        """, (
            tx["id"], tx["event"], tx["amount"], tx["name"], tx["bank"], tx["status"],
            tx["time"], tx.get("slip_filename")
        ))
        conn.commit()

def update_approve(txid, approver_name, customer_user, approved_time):
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE transactions
            SET status='approved', approver_name=%s, customer_user=%s, approved_time=%s
            WHERE id=%s
        """, (approver_name, customer_user, approved_time, txid))
        conn.commit()

def update_cancel(txid, canceler_name, cancel_time):
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE transactions
            SET status='cancelled', canceler_name=%s, cancel_time=%s
            WHERE id=%s
        """, (canceler_name, cancel_time, txid))
        conn.commit()

def restore_tx(txid):
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE transactions
            SET status='new', approver_name=NULL, approved_time=NULL, canceler_name=NULL, cancel_time=NULL, customer_user=NULL
            WHERE id=%s
        """, (txid,))
        conn.commit()

def fetch_transactions():
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT * FROM transactions ORDER BY time DESC LIMIT 50")
        txs = cur.fetchall()
    # แบ่งตาม status
    new_orders = [tx for tx in txs if tx['status']=='new']
    approved_orders = [tx for tx in txs if tx['status']=='approved']
    cancelled_orders = [tx for tx in txs if tx['status']=='cancelled']
    return new_orders, approved_orders, cancelled_orders

def fetch_daily_summary_top_users():
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT customer_user, DATE(time) as day, SUM(amount) as total
            FROM transactions
            WHERE customer_user IS NOT NULL AND customer_user ~ '^thk\d+$'
            GROUP BY day, customer_user
        """)
        data = cur.fetchall()
    # จัดกลุ่มเป็น {day:[{user,total}]}
    summary = defaultdict(list)
    for d in data:
        summary[str(d["day"])].append({"user":d["customer_user"],"total":d["total"]})
    # เลือก top 5 ต่อวัน
    for day in summary:
        summary[day] = sorted(summary[day], key=lambda x:-x["total"])[:5]
    return summary

# -------------------- Flask Endpoints --------------------
@app.route("/")
def index():
    user_ip = request.remote_addr or "unknown"
    return render_template("index.html", user_ip=user_ip)

@app.route("/get_transactions")
def get_transactions():
    new_orders, approved_orders, cancelled_orders = fetch_transactions()
    daily_summary = fetch_daily_summary_top_users()

    # ฟอร์แมตเวลาและจำนวนเงิน
    for tx in new_orders+approved_orders+cancelled_orders:
        tx['time_str'] = fmt_time_local(tx['time'])
        tx['amount_str'] = fmt_amount(tx['amount'])
        if 'approved_time' in tx and tx['approved_time']:
            tx['approved_time_str'] = fmt_time_local(tx['approved_time'])
        if 'cancel_time' in tx and tx['cancel_time']:
            tx['cancelled_time_str'] = fmt_time_local(tx['cancel_time'])
    # สรุปยอด wallet วันนี้
    wallet_total = sum(tx['amount'] for tx in approved_orders if tx['time'].date()==datetime.now(TZ).date())
    wallet_total_str = fmt_amount(wallet_total)

    return jsonify({
        "new_orders": new_orders,
        "approved_orders": approved_orders,
        "cancelled_orders": cancelled_orders,
        "wallet_daily_total": wallet_total_str,
        "daily_summary_top_users": daily_summary
    })

# -------------------- Approve / Cancel / Restore --------------------
@app.route("/approve", methods=["POST"])
def approve():
    txid = request.json.get("id")
    customer_user = request.json.get("customer_user")
    user_ip = request.remote_addr or "unknown"
    approver_name = f"Approver_{user_ip[-3:]}"  # ชื่อจำลอง

    update_approve(txid, approver_name, customer_user, datetime.utcnow())
    log_with_time(f"[APPROVED] {txid} by {approver_name} for {customer_user}")
    return jsonify({"status":"success"}),200

@app.route("/cancel", methods=["POST"])
def cancel():
    txid = request.json.get("id")
    user_ip = request.remote_addr or "unknown"
    canceler_name = f"Canceler_{user_ip[-3:]}"
    update_cancel(txid, canceler_name, datetime.utcnow())
    log_with_time(f"[CANCELLED] {txid} by {canceler_name}")
    return jsonify({"status":"success"}),200

@app.route("/restore", methods=["POST"])
def restore():
    txid = request.json.get("id")
    restore_tx(txid)
    log_with_time(f"[RESTORED] {txid}")
    return jsonify({"status":"success"}),200

# -------------------- Webhook TrueWallet --------------------
@app.route("/truewallet/webhook", methods=["POST"])
def truewallet_webhook():
    try:
        data = request.get_json(force=True, silent=True)
        if not data:
            log_with_time("[WEBHOOK ERROR] No JSON received")
            return jsonify({"status":"error","message":"No JSON received"}), 400

        message_jwt = data.get("message")
        decoded = {}
        if message_jwt:
            try:
                decoded = jwt.decode(message_jwt, SECRET_KEY, algorithms=["HS256"])
            except Exception as e:
                log_with_time("[JWT ERROR]", str(e))
                return jsonify({"status":"error","message":"Invalid JWT"}), 400
        else:
            decoded = data

        txid = decoded.get("transaction_id") or f"TX{random.randint(1000,999999)}"
        # ตรวจสอบซ้ำ
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM transactions WHERE id=%s", (txid,))
            if cur.fetchone():
                return jsonify({"status":"success","message":"Transaction exists"}), 200

        amount = int(decoded.get("amount",0))
        sender_name = decoded.get("sender_name","-")
        sender_mobile = decoded.get("sender_mobile","-")
        # แก้ปัญหาสตริง
        name = f"{sender_name} / {sender_mobile}" if sender_mobile and sender_mobile!="-”" else sender_name

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
            tx_time_utc = datetime.fromisoformat(time_str)
        except:
            tx_time_utc = datetime.utcnow()

        tx = {
            "id": txid,
            "event": event_type,
            "amount": amount,
            "name": name,
            "bank": bank_name_th,
            "status": "new",
            "time": tx_time_utc,
            "slip_filename": None
        }
        insert_transaction(tx)
        log_with_time("[WEBHOOK RECEIVED]", tx)
        return jsonify({"status":"success"}),200

    except Exception as e:
        log_with_time("[WEBHOOK EXCEPTION]", str(e))
        return jsonify({"status":"error","message":str(e)}),500

# -------------------- Upload Slip --------------------
@app.route("/upload_slip/<txid>", methods=["POST"])
def upload_slip(txid):
    if "file" not in request.files:
        return jsonify({"status":"error","message":"No file part"}), 400
    file = request.files["file"]
    if file.filename=="":
        return jsonify({"status":"error","message":"No selected file"}), 400
    filename = f"{txid}_{secure_filename(file.filename)}"
    file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
    with conn.cursor() as cur:
        cur.execute("UPDATE transactions SET slip_filename=%s WHERE id=%s", (filename, txid))
        conn.commit()
    return jsonify({"status": "success","filename":filename})

@app.route("/slip/<filename>")
def get_slip(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# -------------------- Run App --------------------
if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",8080)), debug=True)
