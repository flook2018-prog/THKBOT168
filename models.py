from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import bcrypt

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = "users"
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    role = db.Column(db.String(20), default='admin')  # admin, moderator, viewer
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    def set_password(self, password):
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    def check_password(self, password):
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))

class LineOA(db.Model):
    __tablename__ = "line_oas"
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    channel_access_token = db.Column(db.Text, nullable=False)
    channel_secret = db.Column(db.String(100), nullable=False)
    webhook_url = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    messages = db.relationship('LineMessage', backref='line_oa', lazy=True, cascade='all, delete-orphan')
    
class LineMessage(db.Model):
    __tablename__ = "line_messages"
    
    id = db.Column(db.Integer, primary_key=True)
    line_oa_id = db.Column(db.Integer, db.ForeignKey('line_oas.id'), nullable=False)
    message_id = db.Column(db.String(100))  # LINE message ID
    user_id = db.Column(db.String(100), nullable=False)  # LINE user ID
    user_display_name = db.Column(db.String(100))
    message_type = db.Column(db.String(20), default='text')  # text, image, video, audio, file, location, sticker
    message_text = db.Column(db.Text)
    message_data = db.Column(db.JSON)  # For storing complex message data
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_from_user = db.Column(db.Boolean, default=True)  # True if from user, False if from admin
    admin_reply = db.Column(db.Text)
    admin_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    replied_at = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='unread')  # unread, read, replied
    
    # Relationships
    admin_user = db.relationship('User', backref='line_messages')

class ResponsePattern(db.Model):
    __tablename__ = "response_patterns"
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    trigger_keywords = db.Column(db.JSON)  # Array of keywords
    response_text = db.Column(db.Text, nullable=False)
    is_auto = db.Column(db.Boolean, default=False)  # Auto-reply or quick response
    is_active = db.Column(db.Boolean, default=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    creator = db.relationship('User', backref='response_patterns')

class SlipVerification(db.Model):
    __tablename__ = "slip_verifications"
    
    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.String(100), db.ForeignKey('transactions.id'))
    slip_image_path = db.Column(db.String(255))
    verification_result = db.Column(db.String(20))  # genuine, fake, suspicious, pending
    verification_score = db.Column(db.Float)  # Confidence score 0-1
    verification_details = db.Column(db.JSON)  # Detailed analysis results
    verified_by = db.Column(db.String(50))  # system, manual, ai
    verified_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text)

class Transaction(db.Model):
    __tablename__ = "transactions"

    id = db.Column(db.String, primary_key=True)
    event = db.Column(db.String)
    amount = db.Column(db.Integer)
    name = db.Column(db.String)
    bank = db.Column(db.String)
    status = db.Column(db.String, default="new")
    time = db.Column(db.String)           # เวลาเข้ารายการ
    time_str = db.Column(db.String)
    approved_time = db.Column(db.String, nullable=True)
    approved_time_str = db.Column(db.String, nullable=True)
    approver_name = db.Column(db.String, nullable=True)
    canceler_name = db.Column(db.String, nullable=True)
    cancelled_time = db.Column(db.String, nullable=True)
    cancelled_time_str = db.Column(db.String, nullable=True)
    customer_user = db.Column(db.String, nullable=True)
    slip_filename = db.Column(db.String, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    slip_verification = db.relationship('SlipVerification', backref='transaction', uselist=False)
