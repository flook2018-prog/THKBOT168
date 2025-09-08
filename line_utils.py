import logging
import sys

# Add current directory to Python path to enable imports
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from linebot import LineBotApi, WebhookHandler
    from linebot.models import (
        MessageEvent, TextMessage, TextSendMessage, ImageMessage, 
        VideoMessage, AudioMessage, FileMessage, LocationMessage, 
        StickerMessage, QuickReply, QuickReplyButton, MessageAction
    )
    from linebot.exceptions import InvalidSignatureError, LineBotApiError
except ImportError:
    # Fallback if line-bot-sdk is not available
    class LineBotApi:
        def __init__(self, token): pass
        def get_bot_info(self): return None
        def push_message(self, user_id, message): pass
        def get_profile(self, user_id): return None
    
    class WebhookHandler:
        def __init__(self, secret): pass
        def handle(self, body, signature): pass
    
    class LineBotApiError(Exception): pass
    class InvalidSignatureError(Exception): pass
    
    class TextSendMessage:
        def __init__(self, text): self.text = text
    
    class MessageEvent: pass
    class TextMessage: pass

from datetime import datetime

try:
    from models import LineOA, LineMessage, ResponsePattern, db
except ImportError:
    # Fallback during testing
    LineOA = LineMessage = ResponsePattern = db = None

logger = logging.getLogger(__name__)

class LineOAManager:
    def __init__(self):
        self.line_bots = {}  # Store LineBotApi instances
        self.handlers = {}   # Store WebhookHandler instances
        self.load_line_oas()
    
    def load_line_oas(self):
        """Load all active LINE OA configurations"""
        line_oas = LineOA.query.filter_by(is_active=True).all()
        for oa in line_oas:
            try:
                self.line_bots[oa.id] = LineBotApi(oa.channel_access_token)
                self.handlers[oa.id] = WebhookHandler(oa.channel_secret)
                logger.info(f"Loaded LINE OA: {oa.name}")
            except Exception as e:
                logger.error(f"Failed to load LINE OA {oa.name}: {str(e)}")
    
    def add_line_oa(self, name, channel_access_token, channel_secret):
        """Add new LINE OA configuration"""
        try:
            # Test the credentials
            test_bot = LineBotApi(channel_access_token)
            test_bot.get_bot_info()
            
            # Save to database
            oa = LineOA(
                name=name,
                channel_access_token=channel_access_token,
                channel_secret=channel_secret,
                is_active=True
            )
            db.session.add(oa)
            db.session.commit()
            
            # Add to runtime
            self.line_bots[oa.id] = test_bot
            self.handlers[oa.id] = WebhookHandler(channel_secret)
            
            logger.info(f"Added new LINE OA: {name}")
            return {"success": True, "oa_id": oa.id}
            
        except LineBotApiError as e:
            logger.error(f"LINE API Error: {str(e)}")
            return {"success": False, "error": "Invalid LINE credentials"}
        except Exception as e:
            logger.error(f"Error adding LINE OA: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def handle_webhook(self, oa_id, body, signature):
        """Handle LINE webhook for specific OA"""
        if oa_id not in self.handlers:
            logger.error(f"No handler found for OA ID: {oa_id}")
            return False
        
        try:
            handler = self.handlers[oa_id]
            handler.handle(body, signature)
            return True
        except InvalidSignatureError:
            logger.error("Invalid signature for LINE webhook")
            return False
        except Exception as e:
            logger.error(f"Error handling webhook: {str(e)}")
            return False
    
    def store_message(self, oa_id, event):
        """Store incoming message to database"""
        try:
            message_data = {
                'type': event.message.type,
                'id': event.message.id if hasattr(event.message, 'id') else None
            }
            
            message_text = None
            if isinstance(event.message, TextMessage):
                message_text = event.message.text
                message_data['text'] = event.message.text
            elif isinstance(event.message, StickerMessage):
                message_data['package_id'] = event.message.package_id
                message_data['sticker_id'] = event.message.sticker_id
            
            # Get user profile
            user_display_name = None
            try:
                if oa_id in self.line_bots:
                    profile = self.line_bots[oa_id].get_profile(event.source.user_id)
                    user_display_name = profile.display_name
            except:
                pass
            
            # Store message
            line_message = LineMessage(
                line_oa_id=oa_id,
                message_id=event.message.id if hasattr(event.message, 'id') else None,
                user_id=event.source.user_id,
                user_display_name=user_display_name,
                message_type=event.message.type,
                message_text=message_text,
                message_data=message_data,
                is_from_user=True,
                status='unread'
            )
            
            db.session.add(line_message)
            db.session.commit()
            
            logger.info(f"Stored message from user {event.source.user_id}")
            
            # Check for auto-reply patterns
            self.check_auto_reply(oa_id, event.source.user_id, message_text)
            
            return line_message
            
        except Exception as e:
            logger.error(f"Error storing message: {str(e)}")
            db.session.rollback()
            return None
    
    def check_auto_reply(self, oa_id, user_id, message_text):
        """Check if message matches auto-reply patterns"""
        if not message_text:
            return
        
        try:
            patterns = ResponsePattern.query.filter_by(is_auto=True, is_active=True).all()
            
            for pattern in patterns:
                if pattern.trigger_keywords:
                    for keyword in pattern.trigger_keywords:
                        if keyword.lower() in message_text.lower():
                            self.send_message(oa_id, user_id, pattern.response_text)
                            logger.info(f"Auto-replied to user {user_id} with pattern: {pattern.name}")
                            return
        except Exception as e:
            logger.error(f"Error checking auto-reply: {str(e)}")
    
    def send_message(self, oa_id, user_id, message_text, admin_user_id=None):
        """Send message to LINE user"""
        try:
            if oa_id not in self.line_bots:
                return {"success": False, "error": "LINE OA not found"}
            
            line_bot = self.line_bots[oa_id]
            line_bot.push_message(user_id, TextSendMessage(text=message_text))
            
            # Store admin reply
            if admin_user_id:
                line_message = LineMessage(
                    line_oa_id=oa_id,
                    user_id=user_id,
                    message_type='text',
                    message_text=message_text,
                    is_from_user=False,
                    admin_user_id=admin_user_id,
                    replied_at=datetime.utcnow(),
                    status='sent'
                )
                db.session.add(line_message)
                db.session.commit()
            
            logger.info(f"Sent message to user {user_id}")
            return {"success": True}
            
        except LineBotApiError as e:
            logger.error(f"LINE API Error: {str(e)}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"Error sending message: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def get_messages(self, oa_id=None, user_id=None, limit=50):
        """Get messages with optional filtering"""
        query = LineMessage.query
        
        if oa_id:
            query = query.filter_by(line_oa_id=oa_id)
        if user_id:
            query = query.filter_by(user_id=user_id)
        
        messages = query.order_by(LineMessage.timestamp.desc()).limit(limit).all()
        return messages
    
    def mark_as_read(self, message_id):
        """Mark message as read"""
        try:
            message = LineMessage.query.get(message_id)
            if message:
                message.status = 'read'
                db.session.commit()
                return True
        except Exception as e:
            logger.error(f"Error marking message as read: {str(e)}")
        return False

# Global instance
line_manager = LineOAManager()