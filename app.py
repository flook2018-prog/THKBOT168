from flask import Flask, request, jsonify, render_template, send_from_directory
import os, jwt, random
from datetime import datetime, timedelta
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

DB_URL = "postgresql://postgres:TzfCyZkvUbFomVpqfRMMeQppGvBjxths@postgres.railway.internal:5432/railway"

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
def get_db():
    conn = psycopg2.connect(DB_URL)
    return conn

def log_with_time(*args):
    ts = datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S')
    msg = f"[{ts}] " + " ".join(str(a) for a in args)
    print(msg, flush=True)

def fmt_time_local(t):
    if not t:
        return "-"
    if isinstance(t, str):
        dt = datetime.fromisoformat(t)
    else:
        dt = t
    return dt.astimezone(TZ).strftime("%Y-%m-%d %H:%M:%S")

def fmt_amount(a):
    return f"{a/100:,.2f}" if a is not None else "0.00"

def random_english_name():
    names = ["Alice","Bob","Charlie","David","Eve","Frank","Grace","Hannah","Ian","Jack","Kathy","Leo","Mia","Nina","Oscar"]
    return random.choice(names)

# -------------------- Database Init --------------------
def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS transactions(
        id TEXT PRIMARY KEY,
        event TEXT,
        amount BIGINT,
        name TEXT,
        bank TEXT,
        status TEXT,
        time TIMESTAMP,
        approved_time TIMESTAMP,
        cancel_time TIMESTAMP,
        approver_name TEXT,
        canceler_name TEXT,
        customer_user TEXT,
        slip_filename TEXT
    );
    """)
    conn.commit()
    cur.close()
    conn.close()

init_db()

# -------------------- Flask Endpoints --------------------
@app.route("/")
def index():
    user_ip = request.remote_addr or "unknown"
    return render_template("index.html", user_ip=user_ip)

# -------------------- Get Transactions --------------------
@app.route("/get_transactions")
def get_transactions():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM transactions ORDER BY time DESC")
    all_tx = cur.fetchall()
    cur.close()
    conn.close()

    new_orders = [tx for tx in all_tx if tx["status"]=="new"][:20]
    approved_orders = [tx for tx in all_tx if tx["status"]=="approved"][:20]
    cancelled_orders = [tx for tx in all_tx if tx["status"]=="cancelled"][:20]

    daily_summary = {}
    for tx in approved_orders:
        day = tx["time"].strftime("%Y-%m-%d")
        daily_summary[day] = daily_summary.get(day,0)+tx["amount"]

    return jsonify({
        "new_orders": [{**tx, "time_str":fmt_time_local(tx["time"])} for tx in new_orders],
        "approved_orders": [{**tx, "time_str":fmt_time_local(tx["time"]), "approved_time_str":fmt_time_local(tx["approved_time"])} for tx in approved_orders],
        "cancelled_orders": [{**tx, "time_str":fmt_time_local(tx["time"]), "cancelled_time_str":fmt_time_local(tx["cancel_time"])} for tx in cancelled_orders],
        "wallet_daily_total": fmt_amount(sum(tx["amount"] for tx in approved_orders)),
        "daily_summary": [{"date":k,"total":fmt_amount(v)} for k,v in daily_summary.items()]
    })

# -------------------- Approve --------------------
@app.route("/approve", methods=["POST"])
def approve():
    data = request.json
    txid = data.get("id")
    customer_user = data.get("customer_user")
    approver_name = random_english_name()

    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE transactions SET status='approved', approved_time=%s, approver_name=%s, customer_user=%s WHERE id=%s",
                (datetime.utcnow(), approver_name, customer_user, txid))
    conn.commit()
    cur.close()
    conn.close()
    log_with_time(f"[APPROVED] {txid} by {approver_name} for {customer_user}")
    return jsonify({"status":"success"})

# -------------------- Cancel --------------------
@app.route("/cancel", methods=["POST"])
def cancel():
    data = request.json
    txid = data.get("id")
    canceler_name = random_english_name()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE transactions SET status='cancelled', cancel_time=%s, canceler_name=%s WHERE id=%s",
                (datetime.utcnow(), canceler_name, txid))
    conn.commit()
    cur.close()
    conn.close()
    log_with_time(f"[CANCELLED] {txid} by {canceler_name}")
    return jsonify({"status":"success"})

# -------------------- Restore --------------------
@app.route("/restore", methods=["POST"])
def restore():
    txid = request.json.get("id")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE transactions SET status='new', approver_name=NULL, approved_time=NULL, canceler_name=NULL, cancel_time=NULL, customer_user=NULL WHERE id=%s", (txid,))
    conn.commit()
    cur.close()
    conn.close()
    log_with_time(f"[RESTORED] {txid}")
    return jsonify({"status":"success"})

# -------------------- Upload Slip --------------------
@app.route("/upload_slip/<txid>", methods=["POST"])
def upload_slip(txid):
    if "file" not in request.files:
        return jsonify({"status":"error","message":"No file part"}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"status":"error","message":"No selected file"}), 400
    filename = f"{txid}_{file.filename}"
    file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE transactions SET slip_filename=%s WHERE id=%s", (filename, txid))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"status":"success","filename":filename})

@app.route("/slip/<filename>")
def get_slip(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# -------------------- TrueWallet Webhook --------------------
@app.route("/truewallet/webhook", methods=["POST"])
def truewallet_webhook():
    try:
        data = request.get_json(force=True)
        message_jwt = data.get("message")
        decoded = {}
        if message_jwt:
            decoded = jwt.decode(message_jwt, SECRET_KEY, algorithms=["HS256"])
        else:
            decoded = data

        txid = decoded.get("transaction_id") or f"TX{random.randint(1000,9999)}"
        amount = int(decoded.get("amount",0))
        sender_name = decoded.get("sender_name","-")
        sender_mobile = decoded.get("sender_mobile","-")
        name = f"{sender_name} / {sender_mobile}" if sender_mobile and sender_mobile!="-” else sender_name
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
            tx_time = datetime.fromisoformat(time_str)
        except:
            tx_time = datetime.utcnow()

        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO transactions(id,event,amount,name,bank,status,time)
            VALUES(%s,%s,%s,%s,%s,'new',%s) ON CONFLICT(id) DO NOTHING
        """, (txid,event_type,amount,name,bank_name_th,tx_time))
        conn.commit()
        cur.close()
        conn.close()

        log_with_time("[WEBHOOK RECEIVED]", txid, amount, name)
        return jsonify({"status":"success"})
    except Exception as e:
        log_with_time("[WEBHOOK EXCEPTION]", str(e))
        return jsonify({"status":"error","message":str(e)}),500

# -------------------- Run App --------------------
if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",8080)), debug=True)
