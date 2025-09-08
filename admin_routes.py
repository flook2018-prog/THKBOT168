from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_user, logout_user, login_required, current_user
from models import User, LineOA, LineMessage, ResponsePattern, SlipVerification, db
from line_utils import line_manager
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Admin login page"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password) and user.is_active:
            login_user(user)
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('admin.dashboard'))
        else:
            flash('ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง', 'error')
    
    return render_template('admin/login.html')

@admin_bp.route('/logout')
@login_required
def logout():
    """Admin logout"""
    logout_user()
    flash('ออกจากระบบเรียบร้อยแล้ว', 'success')
    return redirect(url_for('admin.login'))

@admin_bp.route('/dashboard')
@login_required
def dashboard():
    """Admin dashboard"""
    # Get statistics
    stats = {
        'total_line_oas': LineOA.query.filter_by(is_active=True).count(),
        'unread_messages': LineMessage.query.filter_by(status='unread').count(),
        'pending_slips': SlipVerification.query.filter_by(verification_result='pending').count(),
        'active_patterns': ResponsePattern.query.filter_by(is_active=True).count()
    }
    
    # Get recent messages
    recent_messages = LineMessage.query.filter_by(is_from_user=True).order_by(
        LineMessage.timestamp.desc()
    ).limit(10).all()
    
    return render_template('admin/dashboard.html', stats=stats, recent_messages=recent_messages)

@admin_bp.route('/line-oas')
@login_required
def line_oas():
    """Manage LINE OA accounts"""
    oas = LineOA.query.all()
    return render_template('admin/line_oas.html', oas=oas)

@admin_bp.route('/line-oas/add', methods=['POST'])
@login_required
def add_line_oa():
    """Add new LINE OA"""
    try:
        name = request.form.get('name')
        channel_access_token = request.form.get('channel_access_token')
        channel_secret = request.form.get('channel_secret')
        
        if not all([name, channel_access_token, channel_secret]):
            flash('กรุณากรอกข้อมูลให้ครบถ้วน', 'error')
            return redirect(url_for('admin.line_oas'))
        
        # Add LINE OA using line_manager
        result = line_manager.add_line_oa(name, channel_access_token, channel_secret)
        
        if result['success']:
            flash(f'เพิ่ม LINE OA "{name}" เรียบร้อยแล้ว', 'success')
        else:
            flash(f'เกิดข้อผิดพลาด: {result["error"]}', 'error')
    
    except Exception as e:
        logger.error(f"Error adding LINE OA: {str(e)}")
        flash('เกิดข้อผิดพลาดในการเพิ่ม LINE OA', 'error')
    
    return redirect(url_for('admin.line_oas'))

@admin_bp.route('/line-oas/<int:oa_id>/toggle', methods=['POST'])
@login_required
def toggle_line_oa(oa_id):
    """Toggle LINE OA active status"""
    try:
        oa = LineOA.query.get_or_404(oa_id)
        oa.is_active = not oa.is_active
        oa.updated_at = datetime.utcnow()
        db.session.commit()
        
        # Reload line manager
        line_manager.load_line_oas()
        
        status = "เปิดใช้งาน" if oa.is_active else "ปิดใช้งาน"
        flash(f'{status} LINE OA "{oa.name}" แล้ว', 'success')
    
    except Exception as e:
        logger.error(f"Error toggling LINE OA: {str(e)}")
        flash('เกิดข้อผิดพลาดในการเปลี่ยนสถานะ', 'error')
    
    return redirect(url_for('admin.line_oas'))

@admin_bp.route('/messages')
@login_required
def messages():
    """Message management page"""
    oa_id = request.args.get('oa_id', type=int)
    status = request.args.get('status', 'all')
    
    # Build query
    query = LineMessage.query
    
    if oa_id:
        query = query.filter_by(line_oa_id=oa_id)
    
    if status != 'all':
        query = query.filter_by(status=status)
    
    messages = query.order_by(LineMessage.timestamp.desc()).limit(100).all()
    line_oas = LineOA.query.filter_by(is_active=True).all()
    
    return render_template('admin/messages.html', messages=messages, line_oas=line_oas, 
                         selected_oa=oa_id, selected_status=status)

@admin_bp.route('/messages/<int:message_id>/reply', methods=['POST'])
@login_required
def reply_message(message_id):
    """Reply to a message"""
    try:
        message = LineMessage.query.get_or_404(message_id)
        reply_text = request.form.get('reply_text')
        
        if not reply_text:
            return jsonify({'success': False, 'error': 'กรุณาใส่ข้อความตอบกลับ'})
        
        # Send reply using line_manager
        result = line_manager.send_message(
            message.line_oa_id, 
            message.user_id, 
            reply_text, 
            current_user.id
        )
        
        if result['success']:
            # Update message status
            message.status = 'replied'
            message.admin_reply = reply_text
            message.replied_at = datetime.utcnow()
            message.admin_user_id = current_user.id
            db.session.commit()
            
            return jsonify({'success': True, 'message': 'ส่งข้อความเรียบร้อยแล้ว'})
        else:
            return jsonify({'success': False, 'error': result['error']})
    
    except Exception as e:
        logger.error(f"Error replying to message: {str(e)}")
        return jsonify({'success': False, 'error': 'เกิดข้อผิดพลาดในการส่งข้อความ'})

@admin_bp.route('/patterns')
@login_required
def patterns():
    """Response pattern management"""
    patterns = ResponsePattern.query.order_by(ResponsePattern.created_at.desc()).all()
    return render_template('admin/patterns.html', patterns=patterns)

@admin_bp.route('/patterns/add', methods=['POST'])
@login_required
def add_pattern():
    """Add new response pattern"""
    try:
        name = request.form.get('name')
        keywords = request.form.get('keywords', '').split(',')
        response_text = request.form.get('response_text')
        is_auto = request.form.get('is_auto') == 'on'
        
        # Clean keywords
        keywords = [k.strip() for k in keywords if k.strip()]
        
        if not all([name, keywords, response_text]):
            flash('กรุณากรอกข้อมูลให้ครบถ้วน', 'error')
            return redirect(url_for('admin.patterns'))
        
        pattern = ResponsePattern(
            name=name,
            trigger_keywords=keywords,
            response_text=response_text,
            is_auto=is_auto,
            is_active=True,
            created_by=current_user.id
        )
        
        db.session.add(pattern)
        db.session.commit()
        
        flash(f'เพิ่มแพทเทิน "{name}" เรียบร้อยแล้ว', 'success')
    
    except Exception as e:
        logger.error(f"Error adding pattern: {str(e)}")
        flash('เกิดข้อผิดพลาดในการเพิ่มแพทเทิน', 'error')
    
    return redirect(url_for('admin.patterns'))

@admin_bp.route('/patterns/<int:pattern_id>/toggle', methods=['POST'])
@login_required
def toggle_pattern(pattern_id):
    """Toggle pattern active status"""
    try:
        pattern = ResponsePattern.query.get_or_404(pattern_id)
        pattern.is_active = not pattern.is_active
        db.session.commit()
        
        status = "เปิดใช้งาน" if pattern.is_active else "ปิดใช้งาน"
        flash(f'{status} แพทเทิน "{pattern.name}" แล้ว', 'success')
    
    except Exception as e:
        logger.error(f"Error toggling pattern: {str(e)}")
        flash('เกิดข้อผิดพลาดในการเปลี่ยนสถานะ', 'error')
    
    return redirect(url_for('admin.patterns'))

@admin_bp.route('/slips')
@login_required
def slips():
    """Slip verification management"""
    verifications = SlipVerification.query.order_by(
        SlipVerification.verified_at.desc()
    ).limit(100).all()
    
    return render_template('admin/slips.html', verifications=verifications)