from flask import Flask, request, jsonify, render_template
import os, jwt, random
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

# -------------------- Config --------------------
SECRET_KEY = "f557ff6589e6d075581d68df1d4f3af7"
DATABASE_URL = os.environ.get("DATABASE_URL") or "postgresql://postgres:TzfCyZkvUbFomVpqfRMMeQppGvBjxths@postgres.railway.internal:5432/railway"

# แผนที่ธนาคารเป็นภาษาไทย
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

# -------------------- Connect PostgreSQL --------------------
conn = psycopg2.connect(DATABASE_URL, sslmode="require")
cursor = conn.cursor(cursor_factory=RealDictCursor)

# -------------------- Create Table Automatically --------------------
cursor.execute("""
CREATE TABLE IF NOT EXISTS transactions (
    id TEXT PRIMARY KEY,
    event TEXT,
    amount BIGINT,
    name TEXT,
    bank TEXT,
    status TEXT,
    time TIMESTAMP,
    approver_name TEXT,
    approved_time TIMESTAMP,
    canceler_name TEXT,
    cancelled_time TIMESTAMP,
    customer_user TEXT
)
""")
conn.commit()

# -------------------- Helpers --------------------
ip_approver_map = {}

def log_with_time(*args):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{ts}] " + " ".join(str(a) for a in args), flush=True)

def random_english_name():
    names = ["Alice","Bob","Charlie","David","Eve","Frank","Grace","Hannah","Ian","Jack","Kathy","Leo","Mia","Nina","Oscar"]
    return random.choice(names)

def fmt_amount(a):
    return f"{a/100:,.2f}" if isinstance(a,(int,float,int)) else str(a)

def get_transactions_by_status(status):
    cursor.execute("SELECT * FROM transactions WHERE status=%s ORDER BY time DESC LIMIT 20;", (status,))
    return cursor.fetchall()

def update_daily_summary():
    cursor.execute("""
        SELECT DATE(time) AS day, SUM(amount) AS total
        FROM transactions
        WHERE status='approved'
        GROUP BY DATE(time)
        ORDER BY DATE(time)
    """)
    return cursor.fetchall()

# -------------------- Flask Endpoints --------------------
@app.route("/")
def index():
    user_ip = request.remote_addr or "unknown"
    return render_template("index.html", user_ip=user_ip)

@app.route("/get_transactions")
def get_transactions():
    new_orders = get_transactions_by_status("new")
    approved_orders = get_transactions_by_status("approved")
    cancelled_orders = get_transactions_by_status("cancelled")

    wallet_daily_total = sum(tx["amount"] for tx in approved_orders)
    wallet_daily_total_str = fmt_amount(wallet_daily_total)
    daily_summary = [{"date": str(d["day"]), "total": fmt_amount(d["total"])} for d in update_daily_summary()]

    # แปลงชื่อธนาคารเป็นไทย
    for lst in [new_orders, approved_orders, cancelled_orders]:
        for tx in lst:
            if tx["bank"] in BANK_MAP_TH:
                tx["bank"] = BANK_MAP_TH[tx["bank"]]

    return jsonify({
        "new_orders": new_orders,
        "approved_orders": approved_orders,
        "cancelled_orders": cancelled_orders,
        "wallet_daily_total": wallet_daily_total_str,
        "daily_summary": daily_summary
    })

# -------------------- Approve / Cancel / Restore --------------------
@app.route("/approve", methods=["POST"])
def approve():
    txid = request.json.get("id")
    customer_user = request.json.get("customer_user")
    user_ip = request.remote_addr or "unknown"

    # ฟิกชื่อผู้อนุมัติ ตาม IP
    if user_ip not in ip_approver_map:
        ip_approver_map[user_ip] = random_english_name()
    approver_name = ip_approver_map[user_ip]

    cursor.execute("SELECT * FROM transactions WHERE id=%s AND status='new';", (txid,))
    tx = cursor.fetchone()
    if tx:
        approved_time = datetime.now()
        cursor.execute("""
            UPDATE transactions
            SET status='approved', approver_name=%s, approved_time=%s, customer_user=%s
            WHERE id=%s
        """, (approver_name, approved_time, customer_user, txid))
        conn.commit()
        log_with_time(f"[APPROVED] {txid} by {approver_name} ({user_ip}) for customer {customer_user}")
    return jsonify({"status": "success"}), 200

@app.route("/cancel", methods=["POST"])
def cancel():
    txid = request.json.get("id")
    user_ip = request.remote_addr or "unknown"

    if user_ip not in ip_approver_map:
        ip_approver_map[user_ip] = random_english_name()
    canceler_name = ip_approver_map[user_ip]

    cursor.execute("SELECT * FROM transactions WHERE id=%s AND status='new';", (txid,))
    tx = cursor.fetchone()
    if tx:
        cancelled_time = datetime.now()
        cursor.execute("""
            UPDATE transactions
            SET status='cancelled', canceler_name=%s, cancelled_time=%s
            WHERE id=%s
        """, (canceler_name, cancelled_time, txid))
        conn.commit()
        log_with_time(f"[CANCELLED] {txid} by {canceler_name} ({user_ip})")
    return jsonify({"status": "success"}), 200

@app.route("/restore", methods=["POST"])
def restore():
    txid = request.json.get("id")
    cursor.execute("SELECT * FROM transactions WHERE id=%s AND status IN ('approved','cancelled');", (txid,))
    tx = cursor.fetchone()
    if tx:
        cursor.execute("""
            UPDATE transactions
            SET status='new', approver_name=NULL, approved_time=NULL,
                canceler_name=NULL, cancelled_time=NULL, customer_user=NULL
            WHERE id=%s
        """, (txid,))
        conn.commit()
        log_with_time(f"[RESTORED] {txid}")
    return jsonify({"status": "success"}), 200

# -------------------- Webhook TrueWallet --------------------
@app.route("/truewallet/webhook", methods=["POST"])
def truewallet_webhook():
    try:
        data = request.get_json(force=True)
        if not data:
            log_with_time("[WEBHOOK ERROR] No JSON received")
            return jsonify({"status":"error","message":"No JSON received"}), 400

        message_jwt = data.get("message")
        decoded = {}
        if message_jwt:
            decoded = jwt.decode(message_jwt, SECRET_KEY, algorithms=["HS256"])
        else:
            decoded = data

        txid = decoded.get("transaction_id") or f"TX{random.randint(10000,99999)}"
        cursor.execute("SELECT id FROM transactions WHERE id=%s;", (txid,))
        if cursor.fetchone():
            return jsonify({"status":"success","message":"Transaction exists"}), 200

        amount = int(decoded.get("amount",0))
        sender_name = decoded.get("sender_name","-")
        sender_mobile = decoded.get("sender_mobile","-")
        name = f"{sender_name} / {sender_mobile}" if sender_mobile else sender_name
        event_type = decoded.get("event_type","ฝาก").upper()
        bank_code = (decoded.get("channel") or "").upper()

        # แปลงธนาคารเป็นภาษาไทย
        if event_type == "P2P" or bank_code in ["TRUEWALLET","WALLET"]:
            bank_name_th = "ทรูวอเลท"
        elif bank_code in BANK_MAP_TH:
            bank_name_th = BANK_MAP_TH[bank_code]
        elif bank_code:
            bank_name_th = bank_code
        else:
            bank_name_th = "-"

        time_str = decoded.get("received_time") or datetime.now().isoformat()
        tx_time = time_str[:19].replace("T"," ")

        cursor.execute("""
            INSERT INTO transactions (id,event,amount,name,bank,status,time)
            VALUES (%s,%s,%s,%s,%s,'new',%s)
        """, (txid, event_type, amount, name, bank_name_th, tx_time))
        conn.commit()
        log_with_time("[WEBHOOK RECEIVED]", txid, amount, name)
        return jsonify({"status":"success"}), 200

    except Exception as e:
        log_with_time("[WEBHOOK EXCEPTION]", str(e))
        return jsonify({"status":"error","message":str(e)}), 500

# -------------------- Run App --------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",8080)), debug=True)
