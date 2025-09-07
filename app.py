from flask import Flask, request, jsonify, render_template
import os, jwt, random
from datetime import datetime
import mysql.connector
from collections import defaultdict

app = Flask(__name__)

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

# -------------------- DB Connection --------------------
def get_db():
    return mysql.connector.connect(
        host=os.getenv("MYSQLHOST"),
        user=os.getenv("MYSQLUSER"),
        password=os.getenv("MYSQLPASSWORD"),
        database=os.getenv("MYSQLDATABASE"),
        port=int(os.getenv("MYSQLPORT", 3306))
    )

# สร้างตารางถ้ายังไม่มี
def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id VARCHAR(50) PRIMARY KEY,
        event VARCHAR(50),
        amount INT,
        name VARCHAR(255),
        bank VARCHAR(100),
        status VARCHAR(20),
        time VARCHAR(30),
        approver_name VARCHAR(50),
        approved_time VARCHAR(30),
        canceler_name VARCHAR(50),
        cancelled_time VARCHAR(30),
        customer_user VARCHAR(100)
    )
    """)
    conn.commit()
    cur.close()
    conn.close()

init_db()

# -------------------- Helpers --------------------
def log_with_time(*args):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    msg = f"[{ts}] " + " ".join(str(a) for a in args)
    print(msg, flush=True)

def random_english_name():
    names = ["Alice","Bob","Charlie","David","Eve","Frank","Grace","Hannah","Ian","Jack","Kathy","Leo","Mia","Nina","Oscar"]
    return random.choice(names)

def fmt_amount(a):
    return f"{a/100:,.2f}" if isinstance(a,(int,float)) else str(a)

# -------------------- Flask Endpoints --------------------
@app.route("/")
def index():
    user_ip = request.remote_addr or "unknown"
    return render_template("index.html", user_ip=user_ip)

@app.route("/get_transactions")
def get_transactions():
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM transactions WHERE status='new' ORDER BY time DESC LIMIT 20")
    new_orders = cur.fetchall()
    cur.execute("SELECT * FROM transactions WHERE status='approved' ORDER BY time DESC LIMIT 20")
    approved_orders = cur.fetchall()
    cur.execute("SELECT * FROM transactions WHERE status='cancelled' ORDER BY time DESC LIMIT 20")
    cancelled_orders = cur.fetchall()

    wallet_daily_total = sum(tx["amount"] for tx in approved_orders)
    wallet_daily_total_str = fmt_amount(wallet_daily_total)

    cur.close()
    conn.close()

    return jsonify({
        "new_orders": new_orders,
        "approved_orders": approved_orders,
        "cancelled_orders": cancelled_orders,
        "wallet_daily_total": wallet_daily_total_str,
        "daily_summary": []  # (เอาไว้ทีหลังทำ SUM GROUP BY DATE)
    })

# -------------------- Approve / Cancel --------------------
@app.route("/approve", methods=["POST"])
def approve():
    txid = request.json.get("id")
    customer_user = request.json.get("customer_user")
    user_ip = request.remote_addr or "unknown"
    approver_name = random_english_name()

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE transactions
        SET status='approved', approver_name=%s, approved_time=%s, customer_user=%s
        WHERE id=%s
    """, (approver_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), customer_user, txid))
    conn.commit()
    cur.close()
    conn.close()

    log_with_time(f"[APPROVED] {txid} by {approver_name} ({user_ip}) for customer {customer_user}")
    return jsonify({"status": "success"}), 200

@app.route("/cancel", methods=["POST"])
def cancel():
    txid = request.json.get("id")
    user_ip = request.remote_addr or "unknown"
    canceler_name = random_english_name()

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE transactions
        SET status='cancelled', canceler_name=%s, cancelled_time=%s
        WHERE id=%s
    """, (canceler_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), txid))
    conn.commit()
    cur.close()
    conn.close()

    log_with_time(f"[CANCELLED] {txid} by {canceler_name} ({user_ip})")
    return jsonify({"status": "success"}), 200

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

        txid = decoded.get("transaction_id") or f"TX{random.randint(100000,999999)}"

        amount = int(decoded.get("amount",0))
        sender_name = decoded.get("sender_name","-")
        sender_mobile = decoded.get("sender_mobile","-")
        name = f"{sender_name} / {sender_mobile}" if sender_mobile else sender_name
        event_type = decoded.get("event_type","ฝาก").upper()
        bank_code = (decoded.get("channel") or "").upper()

        if event_type == "P2P" or bank_code in ["TRUEWALLET","WALLET"]:
            bank_name_th = "ทรูวอเลท"
        elif bank_code in BANK_MAP_TH:
            bank_name_th = BANK_MAP_TH[bank_code]
        elif bank_code:
            bank_name_th = bank_code
        else:
            bank_name_th = "-"

        tx_time = decoded.get("received_time") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO transactions (id,event,amount,name,bank,status,time)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (txid, event_type, amount, name, bank_name_th, "new", tx_time))
        conn.commit()
        cur.close()
        conn.close()

        log_with_time("[WEBHOOK RECEIVED]", txid, amount, name)
        return jsonify({"status":"success"}), 200

    except Exception as e:
        log_with_time("[WEBHOOK EXCEPTION]", str(e))
        return jsonify({"status":"error","message":str(e)}), 500

# -------------------- Run App --------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",8080)), debug=True)
