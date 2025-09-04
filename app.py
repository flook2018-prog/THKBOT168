from flask import Flask, request, jsonify, render_template_string, session, redirect, url_for
from datetime import datetime, timedelta
import os, threading, time

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY","local_dev_secret")

# ข้อมูล
transactions = []
approved_transactions = []
wallet_daily_total = 0
wallet_history = []
ip_user_mapping = {}

# แปลงประเภท
def translate_event_type(event_type, bank_code=None):
    if event_type in ["P2P","TOPUP","P2P_TRANSFER"]:
        return "วอลเล็ต"
    elif event_type=="PAYMENT":
        return "ชำระเงิน"
    elif event_type=="BANK" and bank_code:
        bank_mapping = {
            "BAY":"กรุงเทพ","SCB":"ไทยพาณิชย์","KBANK":"กสิกร",
            "KTB":"กรุงไทย","TMB":"ทหารไทย","GSB":"ออมสิน","BBL":"กรุงเทพ","CIMB":"CIMB"
        }
        return bank_mapping.get(bank_code,"ไม่ระบุธนาคาร")
    else:
        return "อื่น ๆ"

def ts_to_str(ts):
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M:%S")
    except:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# Login
@app.route("/", methods=["GET","POST"])
def login():
    if request.method=="POST":
        name = request.form.get("name","").strip()
        if not name:
            return render_template_string(login_html,error="กรุณากรอกชื่อ")
        ip = request.remote_addr
        if ip in ip_user_mapping:
            session['username'] = ip_user_mapping[ip]
        else:
            ip_user_mapping[ip] = name
            session['username'] = name
        return redirect(url_for("dashboard"))
    return render_template_string(login_html,error=None)

# Dashboard
@app.route("/dashboard")
def dashboard():
    username = session.get("username")
    if not username:
        return redirect(url_for("login"))

    new_orders = [tx for tx in transactions if tx['status']=="new"]
    approved_orders = approved_transactions

    global wallet_daily_total
    today = datetime.now().date()
    wallet_daily_total = sum(tx['amount'] for tx in approved_orders if datetime.fromtimestamp(tx['timestamp']).date()==today and tx['event']=="วอลเล็ต")

    return render_template_string(dashboard_html,
                                  username=username,
                                  new_orders=new_orders,
                                  approved_orders=approved_orders,
                                  wallet_daily_total=wallet_daily_total,
                                  wallet_history=wallet_history,
                                  ts_to_str=ts_to_str)

# Webhook
@app.route("/truewallet/webhook", methods=["POST"])
def webhook():
    try:
        data = request.json
        if not data:
            return jsonify({"status":"error","message":"ไม่มีข้อมูล JSON"}),400

        # DEBUG LOG
        print("Incoming webhook data:", data)

        # Transaction ID
        txid = data.get("txid") or data.get("transaction_id") or data.get("id") or "N/A"

        # จำนวนเงิน
        amount_raw = data.get("amount") or data.get("value") or 0
        try:
            amount = float(amount_raw)
        except:
            amount = 0.0

        # ประเภท
        event_type_raw = data.get("event") or data.get("type") or data.get("payment_type") or "Other"
        bank_code = data.get("bank_code") or data.get("bank") or data.get("bankName") or None
        event_type = translate_event_type(event_type_raw, bank_code)

        # เวลา
        timestamp = data.get("timestamp") or datetime.now().timestamp()

        # ชื่อ/เบอร์ สำหรับ Wallet
        if event_type=="วอลเล็ต":
            name = data.get("name") or data.get("customer_name") or "-"
            phone = data.get("phone") or data.get("customer_phone") or "-"
            name_phone = f"{name} / {phone}"
        else:
            name_phone = "-"

        # สร้าง transaction dict
        tx = {
            "txid": txid,
            "event": event_type,
            "amount": amount,
            "name_phone": name_phone,
            "timestamp": timestamp,
            "status":"new",
            "approved_by": None,
            "approved_time": None
        }

        transactions.append(tx)
        return jsonify({"status":"success"}),200

    except Exception as e:
        print("Webhook error:", e)
        return jsonify({"status":"error","message": str(e)}),500

# Approve
@app.route("/approve/<txid>", methods=["POST"])
def approve(txid):
    username = session.get("username")
    if not username:
        return jsonify({"status":"error","message":"กรุณา login"}),401

    for tx in transactions:
        if tx['txid']==txid and tx['status']=="new":
            tx['status']="approved"
            tx['approved_by']=username
            tx['approved_time']=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            approved_transactions.append(tx)
            transactions.remove(tx)
            return jsonify({"status":"success"}),200
    return jsonify({"status":"error","message":"ไม่พบรายการหรืออนุมัติแล้ว"}),404

# Background reset daily wallet
def reset_daily_wallet():
    global wallet_daily_total, wallet_history
    last_date = datetime.now().date()
    while True:
        now = datetime.now()
        if now.date() != last_date:
            wallet_history.append({"date": last_date.strftime("%Y-%m-%d"),"total":wallet_daily_total})
            wallet_daily_total=0
            last_date = now.date()
        time.sleep(60)

threading.Thread(target=reset_daily_wallet,daemon=True).start()

# Login HTML
login_html = """..."""  # (เหมือนเดิม)

# Dashboard HTML
dashboard_html = """..."""  # (เหมือนเดิม)

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)))
