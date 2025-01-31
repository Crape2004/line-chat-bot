import hmac
import hashlib
import base64
from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import sqlite3
from apscheduler.schedulers.background import BackgroundScheduler
import datetime
import json
from linebot.models import FlexSendMessage

LINE_CHANNEL_ACCESS_TOKEN = 'j439mGdFC5EcytTbm+dmZAfn15HrEoa3ey5sn0uNMGgjdWA4M1bHJxeD3W+7Xloo2q1QQ2pDD+SgBKq+PR1sJZrUBkYAht3obUcLlEdA6jI3aIWndg5fwLPp5noZwJ9ZTjFQrec0x5G0xGYjeQEMhgdB04t89/1O/w1cDnyilFU='
LINE_CHANNEL_SECRET = 'a94cf964732a9952e2d989784d1b2cc3'

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

app = Flask(__name__)

def verify_signature(signature, body):
    secret = bytes(LINE_CHANNEL_SECRET, 'utf-8')
    hash = hmac.new(secret, body.encode('utf-8'), hashlib.sha256).digest()
    calculated_signature = base64.b64encode(hash).decode()
    return hmac.compare_digest(signature, calculated_signature)

@app.route('/callback', methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    if not verify_signature(signature, body):
        return 'Invalid signature', 400
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        return 'Invalid signature', 400
    return 'OK', 200

def init_db():
    with sqlite3.connect('db.sqlite') as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            due_date TEXT NOT NULL,
            user_id TEXT NOT NULL,
            next_notify TEXT
        )''')
        conn.commit()

def add_next_notify_column():
    with sqlite3.connect('db.sqlite') as conn:
        c = conn.cursor()

        # ตรวจสอบว่ามีคอลัมน์ next_notify หรือไม่
        c.execute("PRAGMA table_info(tasks);")
        columns = [column[1] for column in c.fetchall()]
        
        if 'next_notify' not in columns:
            c.execute('''ALTER TABLE tasks ADD COLUMN next_notify TEXT;''')
            print("Column next_notify added.")
        else:
            print("Column next_notify already exists.")

        conn.commit()

init_db()
add_next_notify_column()

scheduler = BackgroundScheduler()
scheduler.start()

def send_notifications():
    today = datetime.date.today().strftime('%Y-%m-%d')
    with sqlite3.connect('db.sqlite') as conn:
        c = conn.cursor()
        c.execute('SELECT name, due_date, user_id FROM tasks WHERE due_date = ?', (today,))
        tasks = c.fetchall()
        for task in tasks:
            name, due_date, user_id = task  # เปลี่ยนลำดับของตัวแปรให้ตรง
            line_bot_api.push_message(user_id, TextSendMessage(text=f"📌 งาน '{name}' ครบกำหนดส่ง {due_date}!"))

scheduler.add_job(send_notifications, 'interval', days=1)

def setup_custom_notifications(event, days_interval):
    with sqlite3.connect('db.sqlite') as conn:
        c = conn.cursor()
        c.execute('SELECT name, user_id, due_date FROM tasks')
        tasks = c.fetchall()

        for task in tasks:
            name, user_id, due_date = task
            due_date = datetime.datetime.strptime(due_date, "%Y-%m-%d").date()
            
            # คำนวณวันที่ถัดไปจากวันปัจจุบัน
            today = datetime.date.today()
            next_notification = today + datetime.timedelta(days=days_interval)

            if next_notification < today:  # ถ้าวันที่คำนวณออกมาก่อนวันปัจจุบัน ให้ใช้วันนี้แทน
                next_notification = today

            c.execute('UPDATE tasks SET next_notify = ? WHERE name = ? AND user_id = ?', 
                      (next_notification.strftime('%Y-%m-%d'), name, user_id))
            conn.commit()

            # สร้างงานใน scheduler เพื่อส่งการแจ้งเตือนตามรอบเวลา
            scheduler.add_job(send_custom_notification, 'interval', days=days_interval, 
                              start_date=next_notification, args=[user_id, name, next_notification])

    line_bot_api.push_message(event.reply_token, TextSendMessage(text=f"✅ ตั้งค่าแจ้งเตือนสำเร็จ ทุกๆ {days_interval} วัน!"))

def send_custom_notification(user_id, task_name, next_notification):
    line_bot_api.push_message(user_id, TextSendMessage(text=f"📌 งาน '{task_name}' จะครบกำหนดส่งในวันที่ {next_notification}!"))

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text.strip()

    if text == "เมนู":
        flex_content = {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": "🔹 กรุณาเลือกเมนู", "weight": "bold", "size": "lg"},
                    {"type": "button", "style": "primary", "action": {"type": "message", "label": "📝 เพิ่มงาน", "text": "บันทึกงาน"}},
                    {"type": "button", "style": "primary", "action": {"type": "message", "label": "📋 ดูงานทั้งหมด", "text": "ดูงานทั้งหมด"}},
                    {"type": "button", "style": "primary", "action": {"type": "message", "label": "🗑 ลบงาน", "text": "ลบงาน"}},
                    {"type": "button", "style": "primary", "action": {"type": "message", "label": "🗑 ลบงานทั้งหมด", "text": "ลบงานทั้งหมด"}},
                    {"type": "button", "style": "primary", "action": {"type": "message", "label": "⏰ ตั้งค่าแจ้งเตือน", "text": "ตั้งค่าแจ้งเตือน"}},
                    {"type": "button", "style": "primary", "action": {"type": "message", "label": "⏰ ดูเวลาแจ้งเตือน", "text": "ดูเวลาแจ้งเตือน"}}
                ]
            }
        }

        message = FlexSendMessage(alt_text="เมนูของคุณ", contents=flex_content)
        line_bot_api.reply_message(event.reply_token, message)

    elif text == "บันทึกงาน":
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="ส่งข้อมูลในรูปแบบ: ชื่องาน,YYYY-MM-DD")
        )

    elif "," in text:
        try:
            name, due_date = map(str.strip, text.split(","))
            try:
                datetime.datetime.strptime(due_date, "%Y-%m-%d")
            except ValueError:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ รูปแบบวันที่ไม่ถูกต้อง กรุณาตรวจสอบใหม่"))
                return
            with sqlite3.connect('db.sqlite') as conn:
                c = conn.cursor()
                c.execute('INSERT INTO tasks (name, due_date, user_id, next_notify) VALUES (?, ?, ?, ?)', 
                          (name, due_date, user_id, due_date))
                conn.commit()
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="✅ บันทึกงานสำเร็จ!"))
        except Exception as e:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ รูปแบบไม่ถูกต้อง กรุณาลองใหม่"))

    elif text == "ดูงานทั้งหมด":
        with sqlite3.connect('db.sqlite') as conn:
            c = conn.cursor()
            c.execute('SELECT id, name, due_date FROM tasks WHERE user_id = ?', (user_id,))
            tasks = c.fetchall()

        if tasks:
            task_list = "\n".join([f"{task[0]}. {task[1]} - {task[2]}" for task in tasks])
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"📋 งานทั้งหมด:\n{task_list}"))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🔍 ไม่มีงานในระบบ"))

    elif text == "ลบงาน":
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="❓ ต้องการลบงานที่เท่าไร? (กรุณาตอบหมายเลขงาน เช่น 'งาน 1', 'งาน 2')")
        )

    elif text.startswith('งาน'):  # ตรวจสอบว่าเป็นหมายเลขงาน
        task_id = text[4:]  # ตัดคำว่า "งาน" ออก
        if task_id.isdigit():  # ตรวจสอบว่าเป็นตัวเลข
            task_id = int(task_id)  # แปลงเป็นตัวเลข
            conn = sqlite3.connect('db.sqlite')
            c = conn.cursor()

            # ตรวจสอบว่ามีงานในตารางหรือไม่
            c.execute('SELECT * FROM tasks WHERE id = ? AND user_id = ?', (task_id, user_id))
            task = c.fetchone()

            if task:
                task_name = task[1]  # ชื่อของงานที่ลบ
                # ลบงานที่ระบุ
                c.execute('DELETE FROM tasks WHERE id = ? AND user_id = ?', (task_id, user_id))

                # รีเซ็ตค่า AUTOINCREMENT ให้เริ่มนับใหม่จาก 1
                c.execute('''UPDATE SQLITE_SEQUENCE SET SEQ=0 WHERE NAME='tasks' ''')
                conn.commit()
                conn.close()

                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"🗑️ ลบงานที่ '{task_name}' สำเร็จ!"))
            else:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ ไม่พบงานหรือรูปแบบผิดพลาด"))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ กรุณากรอกหมายเลขงานที่ถูกต้อง"))

    elif text == "ดูเวลาแจ้งเตือน":
        with sqlite3.connect('db.sqlite') as conn:
            c = conn.cursor()
            c.execute('SELECT name, next_notify FROM tasks WHERE user_id = ?', (user_id,))
            tasks = c.fetchall()

        if tasks:
            task_list = "\n".join([f"งาน '{task[0]}' จะได้รับการแจ้งเตือนถัดไปในวันที่ {task[1]}" for task in tasks])
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"⏰ เวลาแจ้งเตือนถัดไป:\n{task_list}"))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🔍 ไม่มีงานในระบบ"))

    elif text == "ลบงานทั้งหมด":
        try:
            conn = sqlite3.connect('db.sqlite')
            c = conn.cursor()

            # ลบงานทั้งหมด
            c.execute('DELETE FROM tasks WHERE user_id = ?', (user_id,))

            # รีเซ็ตค่า AUTOINCREMENT ให้เริ่มนับใหม่จาก 1
            c.execute('''UPDATE SQLITE_SEQUENCE SET SEQ=0 WHERE NAME='tasks' ''')

            conn.commit()
            conn.close()

            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🗑️ ลบงานทั้งหมดสำเร็จ!"))
        except Exception as e:
            print(f"Error: {e}")
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ เกิดข้อผิดพลาดในการลบงานทั้งหมด"))

    elif text == "ตั้งค่าแจ้งเตือน":
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="ต้องการตั้งค่าแจ้งเตือนสำเร็จ ทุกๆ กี่วัน! (ตอบเป็นจำนวนวัน)")
        )

    elif text.isdigit():  # ตรวจสอบว่าข้อความที่ตอบกลับเป็นตัวเลข
        days = int(text)  # แปลงจำนวนวันที่เป็นตัวเลข

        if days > 0:
            notification_interval = days
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"✅ ตั้งค่าแจ้งเตือนสำเร็จ ทุกๆ {days} วัน!")
            )
            setup_custom_notifications(event, days)  # ตั้งค่าแจ้งเตือนในงานทั้งหมด
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="❌ กรุณากรอกจำนวนวันที่มากกว่า 0")
            )

if __name__ == "__main__":
    app.run(port=8000)
