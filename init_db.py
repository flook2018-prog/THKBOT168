#!/usr/bin/env python3
"""
Database initialization script for THKBOT168
Creates all tables and initial admin user
"""

import os
import sys
from flask import Flask
from config import Config
from models import db, User, LineOA, ResponsePattern
import logging

def create_app():
    """Create Flask application for database initialization"""
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Initialize database
    db.init_app(app)
    
    return app

def init_database():
    """Initialize database with tables and default data"""
    app = create_app()
    
    with app.app_context():
        # Create all tables
        db.create_all()
        print("✅ Database tables created successfully")
        
        # Create default admin user if not exists
        admin_user = User.query.filter_by(username=Config.ADMIN_USERNAME).first()
        if not admin_user:
            admin_user = User(
                username=Config.ADMIN_USERNAME,
                email=Config.ADMIN_EMAIL,
                role='admin',
                is_active=True
            )
            admin_user.set_password(Config.ADMIN_PASSWORD)
            db.session.add(admin_user)
            db.session.commit()
            print(f"✅ Created admin user: {Config.ADMIN_USERNAME}")
        else:
            print(f"ℹ️  Admin user already exists: {Config.ADMIN_USERNAME}")
        
        # Create default response patterns
        default_patterns = [
            {
                "name": "สวัสดี",
                "trigger_keywords": ["สวัสดี", "หวัดดี", "ดี", "hello", "hi"],
                "response_text": "สวัสดีครับ! ยินดีให้บริการ มีอะไรให้ช่วยเหลือไหมครับ?",
                "is_auto": True
            },
            {
                "name": "สอบถามยอดเงิน",
                "trigger_keywords": ["ยอดเงิน", "เช็คยอด", "ดูยอด", "balance"],
                "response_text": "กรุณารอสักครู่ เรากำลังตรวจสอบยอดเงินให้คะ",
                "is_auto": False
            },
            {
                "name": "ขอบคุณ",
                "trigger_keywords": ["ขอบคุณ", "thank", "thanks", "thx"],
                "response_text": "ด้วยความยินดีครับ! หากมีอะไรให้ช่วยเหลือเพิ่มเติม สามารถติดต่อมาได้เสมอนะครับ",
                "is_auto": True
            }
        ]
        
        for pattern_data in default_patterns:
            existing = ResponsePattern.query.filter_by(name=pattern_data["name"]).first()
            if not existing:
                pattern = ResponsePattern(
                    name=pattern_data["name"],
                    trigger_keywords=pattern_data["trigger_keywords"],
                    response_text=pattern_data["response_text"],
                    is_auto=pattern_data["is_auto"],
                    is_active=True,
                    created_by=admin_user.id
                )
                db.session.add(pattern)
        
        db.session.commit()
        print("✅ Created default response patterns")
        
        print("\n🎉 Database initialization completed!")
        print(f"📝 Admin credentials:")
        print(f"   Username: {Config.ADMIN_USERNAME}")
        print(f"   Password: {Config.ADMIN_PASSWORD}")
        print(f"   Email: {Config.ADMIN_EMAIL}")

if __name__ == "__main__":
    try:
        init_database()
    except Exception as e:
        print(f"❌ Error initializing database: {str(e)}")
        sys.exit(1)