import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'f557ff6589e6d075581d68df1d4f3af7'
    
    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///thkbot168.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # File Upload
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER') or 'uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    
    # LINE Bot
    LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
    LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
    
    # TrueWallet
    TRUEWALLET_SECRET_KEY = os.environ.get('TRUEWALLET_SECRET_KEY') or 'f557ff6589e6d075581d68df1d4f3af7'
    
    # Admin
    ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME') or 'admin'
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD') or 'admin123'
    ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL') or 'admin@thkbot168.com'
    
    # Timezone
    TIMEZONE = 'Asia/Bangkok'
    
    # Slip Verification
    SLIP_VERIFICATION_ENABLED = os.environ.get('SLIP_VERIFICATION_ENABLED', 'true').lower() == 'true'
    SLIP_AI_CONFIDENCE_THRESHOLD = float(os.environ.get('SLIP_AI_CONFIDENCE_THRESHOLD', '0.8'))