from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from datetime import datetime, timedelta
import secrets
import re
import os
import sqlite3
import traceback
import base64
from werkzeug.utils import secure_filename
from PIL import Image
from io import BytesIO
from flask_mail import Mail, Message

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# Configuration for file uploads
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Email configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'bayandasaziso6@gmail.com'
app.config['MAIL_PASSWORD'] = 'deqruzucediihuzf'
app.config['MAIL_DEFAULT_SENDER'] = 'bayandasaziso6@gmail.com'

mail = Mail(app)

# Create upload folders if they don't exist
os.makedirs(os.path.join(UPLOAD_FOLDER, 'lost'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'found'), exist_ok=True)

# Admin configuration
ADMIN_EMAIL = "bayandasaziso6@gmail.com"
ADMIN_PASSWORD = "S@zirh ngc0bo"

def is_admin_login(email, password):
    return email.lower() == ADMIN_EMAIL.lower() and password == ADMIN_PASSWORD

# Database setup
def get_db():
    conn = sqlite3.connect('lost_and_found.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize all database tables"""
    conn = sqlite3.connect('lost_and_found.db')
    c = conn.cursor()
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  student_number TEXT UNIQUE NOT NULL,
                  full_name TEXT NOT NULL,
                  email TEXT UNIQUE NOT NULL,
                  id_number TEXT UNIQUE NOT NULL,
                  phone TEXT,
                  password TEXT NOT NULL,
                  role TEXT DEFAULT 'user',
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Lost Items table
    c.execute('''CREATE TABLE IF NOT EXISTS lost_items
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  item_name TEXT NOT NULL,
                  category TEXT NOT NULL,
                  description TEXT NOT NULL,
                  date_lost DATE NOT NULL,
                  location TEXT NOT NULL,
                  latitude REAL,
                  longitude REAL,
                  contact_name TEXT NOT NULL,
                  contact_email TEXT NOT NULL,
                  contact_phone TEXT,
                  reward_offered BOOLEAN DEFAULT 0,
                  image_path TEXT,
                  status TEXT DEFAULT 'pending',
                  resolved_at TIMESTAMP,
                  resolved_by INTEGER,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (user_id) REFERENCES users(id),
                  FOREIGN KEY (resolved_by) REFERENCES users(id))''')
    
    # Found Items table
    c.execute('''CREATE TABLE IF NOT EXISTS found_items
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  item_name TEXT NOT NULL,
                  category TEXT NOT NULL,
                  description TEXT NOT NULL,
                  date_found DATE NOT NULL,
                  location TEXT NOT NULL,
                  latitude REAL,
                  longitude REAL,
                  contact_name TEXT NOT NULL,
                  contact_email TEXT NOT NULL,
                  contact_phone TEXT,
                  image_path TEXT,
                  status TEXT DEFAULT 'available',
                  resolved_at TIMESTAMP,
                  resolved_by INTEGER,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (user_id) REFERENCES users(id),
                  FOREIGN KEY (resolved_by) REFERENCES users(id))''')
    
    # Claims table
    c.execute('''CREATE TABLE IF NOT EXISTS claims
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  item_id INTEGER NOT NULL,
                  item_type TEXT NOT NULL,
                  claimant_id INTEGER NOT NULL,
                  message TEXT,
                  status TEXT DEFAULT 'pending',
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  reviewed_by INTEGER,
                  reviewed_at TIMESTAMP,
                  FOREIGN KEY (claimant_id) REFERENCES users(id),
                  FOREIGN KEY (reviewed_by) REFERENCES users(id))''')
    
    # Notifications table - Check if reference_id exists, if not add it
    c.execute("PRAGMA table_info(notifications)")
    columns = [col[1] for col in c.fetchall()]
    
    if not columns:
        # Create new table
        c.execute('''CREATE TABLE IF NOT EXISTS notifications
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id INTEGER NOT NULL,
                      type TEXT NOT NULL,
                      message TEXT NOT NULL,
                      reference_id INTEGER,
                      is_read BOOLEAN DEFAULT 0,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY (user_id) REFERENCES users(id))''')
        print("Notifications table created with reference_id")
    elif 'reference_id' not in columns:
        # Add missing column
        try:
            c.execute("ALTER TABLE notifications ADD COLUMN reference_id INTEGER")
            print("Added reference_id column to notifications table")
        except Exception as e:
            print(f"Error adding column: {e}")
    
    # History table
    c.execute('''CREATE TABLE IF NOT EXISTS item_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  item_id INTEGER NOT NULL,
                  item_type TEXT NOT NULL,
                  item_name TEXT NOT NULL,
                  category TEXT NOT NULL,
                  lost_by_id INTEGER,
                  found_by_id INTEGER,
                  claimed_by_id INTEGER,
                  resolved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  resolved_by INTEGER,
                  notes TEXT,
                  FOREIGN KEY (lost_by_id) REFERENCES users(id),
                  FOREIGN KEY (found_by_id) REFERENCES users(id),
                  FOREIGN KEY (claimed_by_id) REFERENCES users(id),
                  FOREIGN KEY (resolved_by) REFERENCES users(id))''')
    
    # Password reset tokens table
    c.execute('''CREATE TABLE IF NOT EXISTS password_resets
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER NOT NULL,
                  token TEXT UNIQUE NOT NULL,
                  expires_at TIMESTAMP NOT NULL,
                  used BOOLEAN DEFAULT 0,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (user_id) REFERENCES users(id))''')
    
    # Check if admin exists
    c.execute("SELECT * FROM users WHERE email = ?", (ADMIN_EMAIL,))
    admin = c.fetchone()
    if not admin:
        c.execute('''INSERT INTO users (student_number, full_name, email, id_number, phone, password, role)
                     VALUES (?, ?, ?, ?, ?, ?, ?)''',
                  ('ADMIN001', 'Bayanda Saziso', ADMIN_EMAIL, '0000000000000', '0712345678', ADMIN_PASSWORD, 'admin'))
        print(f"Admin user created: {ADMIN_EMAIL}")
    
    conn.commit()
    conn.close()
    print("Database initialized successfully!")

# Initialize database
init_db()

# DUT4Life email pattern
DUT_EMAIL_PATTERN = r'^\d{8}@dut4life\.ac\.za$'
PASSWORD_PATTERN = r'^\$\$Dut\d{6}$'

def is_dut_email(email):
    return re.match(DUT_EMAIL_PATTERN, email.lower()) is not None

def is_valid_password(password):
    return re.match(PASSWORD_PATTERN, password) is not None

def extract_student_number(email):
    if is_dut_email(email):
        return email.split('@')[0]
    return None

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_base64_image(base64_data, user_id, folder):
    try:
        if 'base64,' in base64_data:
            base64_data = base64_data.split('base64,')[1]
        
        image_data = base64.b64decode(base64_data)
        image = Image.open(BytesIO(image_data))
        
        filename = f"{user_id}_{int(datetime.now().timestamp())}_camera.jpg"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], folder, filename)
        
        image.save(filepath, 'JPEG', quality=85)
        return f"uploads/{folder}/{filename}"
    except Exception as e:
        print(f"Error saving base64 image: {e}")
        return None

# ==================== EMAIL FUNCTIONS ====================
def send_claim_approved_notification(claim_id):
    conn = None
    try:
        conn = get_db()
        
        claim = conn.execute('''
            SELECT 
                c.id,
                c.message as claim_message,
                claimant.id as claimant_id,
                claimant.full_name as claimant_name,
                claimant.email as claimant_email,
                claimant.phone as claimant_phone,
                lost_owner.id as lost_owner_id,
                lost_owner.full_name as lost_owner_name,
                lost_owner.email as lost_owner_email,
                lost_owner.phone as lost_owner_phone,
                found_owner.id as found_owner_id,
                found_owner.full_name as found_owner_name,
                found_owner.email as found_owner_email,
                found_owner.phone as found_owner_phone,
                CASE 
                    WHEN c.item_type = 'lost' THEN li.item_name
                    ELSE fi.item_name
                END as item_name,
                li.item_name as lost_item_name,
                fi.item_name as found_item_name,
                li.description as lost_description,
                fi.description as found_description,
                li.location as lost_location,
                fi.location as found_location,
                c.item_type
            FROM claims c
            JOIN users claimant ON c.claimant_id = claimant.id
            LEFT JOIN lost_items li ON li.id = CASE WHEN c.item_type = 'lost' THEN c.item_id ELSE NULL END
            LEFT JOIN found_items fi ON fi.id = CASE WHEN c.item_type = 'found' THEN c.item_id ELSE NULL END
            LEFT JOIN users lost_owner ON li.user_id = lost_owner.id
            LEFT JOIN users found_owner ON fi.user_id = found_owner.id
            WHERE c.id = ?
        ''', (claim_id,)).fetchone()
        
        conn.close()
        
        if not claim:
            return False
        
        claim = dict(claim)
        
        if claim['item_type'] == 'found':
            loser = {'name': claim['claimant_name'], 'email': claim['claimant_email'], 'phone': claim['claimant_phone']}
            finder = {'name': claim['found_owner_name'], 'email': claim['found_owner_email'], 'phone': claim['found_owner_phone']}
            item_name = claim['found_item_name']
        else:
            finder = {'name': claim['claimant_name'], 'email': claim['claimant_email'], 'phone': claim['claimant_phone']}
            loser = {'name': claim['lost_owner_name'], 'email': claim['lost_owner_email'], 'phone': claim['lost_owner_phone']}
            item_name = claim['lost_item_name']
        
        # Send email to loser
        try:
            subject = f"🎉 Good news! Your lost item has been found - DUT Lost & Found"
            msg = Message(subject=subject, recipients=[loser['email']])
            msg.body = f"""
Good news! Your lost item ({item_name}) has been found.

Finder's contact: {finder['name']} - {finder['email']}
Please contact them to arrange pickup.
            """
            mail.send(msg)
            print(f"Email sent to loser: {loser['email']}")
        except Exception as e:
            print(f"Error sending email: {e}")
        
        # Send email to finder
        try:
            subject = f"✅ Claim approved for the item you found - DUT Lost & Found"
            msg = Message(subject=subject, recipients=[finder['email']])
            msg.body = f"""
Claim approved! The item you found ({item_name}) belongs to {loser['name']}.

Owner's contact: {loser['email']}
Please contact them to arrange return.
            """
            mail.send(msg)
            print(f"Email sent to finder: {finder['email']}")
        except Exception as e:
            print(f"Error sending email: {e}")
        
        return True
        
    except Exception as e:
        if conn:
            conn.close()
        print(f"Error: {e}")
        return False

def send_password_reset_email(email, name, token):
    reset_link = url_for('reset_password', token=token, _external=True)
    subject = "Password Reset Request - DUT Lost & Found"
    
    try:
        msg = Message(subject=subject, recipients=[email])
        msg.body = f"""
Dear {name},

We received a request to reset your password.

Click this link to reset your password:
{reset_link}

This link will expire in 24 hours.
If you didn't request this, please ignore this email.

© 2026 Durban University of Technology
        """
        mail.send(msg)
        print(f"Password reset email sent to: {email}")
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

# ==================== ROUTES ====================

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name = request.form['full_name']
        id_number = request.form['id_number']
        email = request.form['email'].lower()
        phone = request.form.get('phone', '')
        password = request.form['password']
        student_number = extract_student_number(email)

        if not is_dut_email(email):
            flash("Please use your DUT4Life email (studentnumber@dut4life.ac.za)", "danger")
            return render_template('register.html')

        if not is_valid_password(password):
            flash("Password must be in format: $$Dut followed by 6 digits (YYMMDD)", "danger")
            return render_template('register.html')

        conn = get_db()
        
        existing = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            flash("Email already registered!", "danger")
            conn.close()
            return render_template('register.html')
        
        existing_id = conn.execute("SELECT * FROM users WHERE id_number = ?", (id_number,)).fetchone()
        if existing_id:
            flash("ID number already registered!", "danger")
            conn.close()
            return render_template('register.html')
        
        conn.execute('''INSERT INTO users (student_number, full_name, email, id_number, phone, password)
                        VALUES (?, ?, ?, ?, ?, ?)''',
                     (student_number, full_name, email, id_number, phone, password))
        conn.commit()
        conn.close()
        
        flash(f"Account created for {full_name}! Please login.", "success")
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].lower()
        password = request.form['password']

        if is_admin_login(email, password):
            conn = get_db()
            admin_user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            
            if not admin_user:
                conn.execute('''INSERT INTO users 
                                (student_number, full_name, email, id_number, phone, password, role)
                                VALUES (?, ?, ?, ?, ?, ?, ?)''',
                             ('ADMIN001', 'Bayanda Saziso', email, '0000000000000', '0712345678', password, 'admin'))
                conn.commit()
                admin_user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            
            conn.close()
            
            session['user'] = {
                'id': admin_user['id'],
                'full_name': 'Bayanda Saziso',
                'email': admin_user['email'],
                'student_number': admin_user['student_number'],
                'phone': admin_user['phone'],
                'role': 'admin'
            }
            flash("Welcome Admin!", "success")
            return redirect(url_for('admin_dashboard'))
        
        else:
            if not is_dut_email(email):
                flash("Students must use DUT4Life email", "danger")
                return render_template('login.html')

            if not is_valid_password(password):
                flash("Password must be in format: $$Dut followed by 6 digits", "danger")
                return render_template('login.html')

            conn = get_db()
            user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            conn.close()

            if user and user['password'] == password:
                session['user'] = {
                    'id': user['id'],
                    'full_name': user['full_name'],
                    'email': user['email'],
                    'student_number': user['student_number'],
                    'phone': user['phone'],
                    'role': user['role']
                }
                flash(f"Welcome back, {user['full_name']}!", "success")
                return redirect(url_for('dashboard'))
            else:
                flash("Invalid email or password!", "danger")

    return render_template('login.html')

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').lower().strip()
        
        if not email:
            flash("Please enter your email address.", "danger")
            return render_template('forgot_password.html')
        
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        
        if user:
            token = secrets.token_urlsafe(32)
            expires_at = datetime.now() + timedelta(hours=24)
            
            conn.execute("DELETE FROM password_resets WHERE user_id = ? AND used = 0", (user['id'],))
            conn.execute('''INSERT INTO password_resets (user_id, token, expires_at)
                            VALUES (?, ?, ?)''', (user['id'], token, expires_at))
            conn.commit()
            
            email_sent = send_password_reset_email(user['email'], user['full_name'], token)
            
            if email_sent:
                flash("Password reset instructions have been sent to your email.", "success")
            else:
                flash("Error sending email. Please try again.", "danger")
                conn.execute("DELETE FROM password_resets WHERE token = ?", (token,))
                conn.commit()
        else:
            flash("If your email is registered, you will receive reset instructions.", "info")
        
        conn.close()
        return redirect(url_for('forgot_password'))
    
    return render_template('forgot_password.html')

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    conn = get_db()
    
    reset = conn.execute('''
        SELECT pr.*, u.email, u.full_name 
        FROM password_resets pr
        JOIN users u ON pr.user_id = u.id
        WHERE pr.token = ? AND pr.used = 0 AND pr.expires_at > CURRENT_TIMESTAMP
    ''', (token,)).fetchone()
    
    if not reset:
        conn.close()
        flash("Invalid or expired reset link. Please request a new one.", "danger")
        return redirect(url_for('forgot_password'))
    
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not is_valid_password(password):
            flash("Password must be in format: $$Dut followed by 6 digits (YYMMDD)", "danger")
            return render_template('reset_password.html', token=token)
        
        if password != confirm_password:
            flash("Passwords do not match!", "danger")
            return render_template('reset_password.html', token=token)
        
        conn.execute("UPDATE users SET password = ? WHERE id = ?", (password, reset['user_id']))
        conn.execute("UPDATE password_resets SET used = 1 WHERE id = ?", (reset['id'],))
        conn.commit()
        conn.close()
        
        flash("Your password has been reset successfully!", "success")
        return redirect(url_for('login'))
    
    conn.close()
    return render_template('reset_password.html', token=token)

# ==================== DASHBOARD ====================
@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        flash("Please login first!", "warning")
        return redirect(url_for('login'))
    
    user = session['user']
    now = datetime.now()
    
    conn = get_db()
    
    # Get user's lost items
    lost_items = conn.execute('''SELECT * FROM lost_items 
                                  WHERE user_id = ? 
                                  ORDER BY created_at DESC''', 
                              (user['id'],)).fetchall()
    
    # Get user's found items
    found_items = conn.execute('''SELECT * FROM found_items 
                                   WHERE user_id = ? 
                                   ORDER BY created_at DESC''', 
                               (user['id'],)).fetchall()
    
    # Get user's claims
    claims = conn.execute('''SELECT c.*, 
                              CASE 
                                  WHEN c.item_type = 'lost' THEN li.item_name
                                  ELSE fi.item_name
                              END as item_name
                           FROM claims c
                           LEFT JOIN lost_items li ON c.item_id = li.id AND c.item_type = 'lost'
                           LEFT JOIN found_items fi ON c.item_id = fi.id AND c.item_type = 'found'
                           WHERE c.claimant_id = ?
                           ORDER BY c.created_at DESC''', 
                       (user['id'],)).fetchall()
    
    # Get relevant found items
    lost_categories = [item['category'] for item in lost_items]
    if lost_categories:
        placeholders = ','.join(['?'] * len(set(lost_categories)))
        relevant_found_items = conn.execute(f'''
            SELECT * FROM found_items 
            WHERE status = 'available' 
            AND category IN ({placeholders})
            ORDER BY created_at DESC
        ''', tuple(set(lost_categories))).fetchall()
    else:
        relevant_found_items = []
    
    # Get potential matches
    matches_list = []
    for lost in lost_items:
        for found in relevant_found_items:
            score = calculate_match_score(dict(lost), dict(found))
            if score >= 50:
                matches_list.append({
                    'lost_id': lost['id'],
                    'lost_name': lost['item_name'],
                    'found_id': found['id'],
                    'found_name': found['item_name'],
                    'found_location': found['location'],
                    'found_date': found['date_found'],
                    'found_image': found['image_path'],
                    'confidence': score
                })
    
    seen = set()
    unique_matches = []
    for match in matches_list:
        if match['found_id'] not in seen:
            seen.add(match['found_id'])
            unique_matches.append(match)
    
    unique_matches.sort(key=lambda x: x['confidence'], reverse=True)
    
    # Create notifications for new matches
    for match in unique_matches[:10]:
        existing = conn.execute('''SELECT id FROM notifications 
                                   WHERE user_id = ? 
                                   AND type = 'match' 
                                   AND message LIKE ? 
                                   AND created_at > datetime('now', '-7 days')''',
                               (user['id'], f'%{match["found_name"]}%')).fetchone()
        
        if not existing:
            message = f"🔍 Potential match found! '{match['found_name']}' was found at {match['found_location']}. {match['confidence']}% match confidence."
            conn.execute('''INSERT INTO notifications (user_id, type, message, created_at, is_read)
                           VALUES (?, ?, ?, ?, 0)''',
                        (user['id'], 'match', message, datetime.now().isoformat()))
            conn.commit()
    
    # Get notifications
    notifications = conn.execute('''SELECT * FROM notifications 
                                     WHERE user_id = ? 
                                     ORDER BY created_at DESC 
                                     LIMIT 20''', 
                                 (user['id'],)).fetchall()
    
    unread_count = conn.execute('''SELECT COUNT(*) as count FROM notifications 
                                     WHERE user_id = ? AND is_read = 0''', 
                                 (user['id'],)).fetchone()['count']
    
    # Get recent activities
    recent_activities = []
    
    for item in lost_items[:5]:
        recent_activities.append({
            'type': 'lost',
            'icon': 'fa-archive',
            'message': f'You reported "{item["item_name"]}" as lost',
            'time': item['created_at'][:10] if item['created_at'] else item['date_lost'],
            'status': 'pending',
            'status_label': item['status']
        })
    
    for item in found_items[:5]:
        recent_activities.append({
            'type': 'found',
            'icon': 'fa-hand-holding-heart',
            'message': f'You reported "{item["item_name"]}" as found',
            'time': item['created_at'][:10] if item['created_at'] else item['date_found'],
            'status': 'success',
            'status_label': item['status']
        })
    
    for claim in claims[:5]:
        recent_activities.append({
            'type': 'match',
            'icon': 'fa-handshake',
            'message': f'You submitted a claim for "{claim["item_name"]}"',
            'time': claim['created_at'][:10] if claim['created_at'] else '',
            'status': 'pending',
            'status_label': claim['status']
        })
    
    recent_activities.sort(key=lambda x: x['time'], reverse=True)
    
    match_count = len(unique_matches)
    
    conn.close()
    
    return render_template(
        'dashboard.html',
        user=user,
        lost_items=[dict(ix) for ix in lost_items],
        found_items=[dict(fx) for fx in found_items],
        claims=[dict(cx) for cx in claims],
        relevant_found_items=[dict(rf) for rf in relevant_found_items],
        matches=unique_matches[:10],
        match_count=match_count,
        notifications=[dict(n) for n in notifications],
        unread_count=unread_count,
        recent_activities=recent_activities[:10],
        now=now
    )

# ==================== NOTIFICATION ROUTES ====================
@app.route('/mark-notification-read/<int:notification_id>', methods=['POST'])
def mark_notification_read(notification_id):
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    conn = get_db()
    conn.execute('UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?',
                (notification_id, session['user']['id']))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/mark-all-notifications-read', methods=['POST'])
def mark_all_notifications_read():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    conn = get_db()
    conn.execute('UPDATE notifications SET is_read = 1 WHERE user_id = ?',
                (session['user']['id'],))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/api/notifications/count')
def notification_count():
    if 'user' not in session:
        return jsonify({'count': 0})
    
    conn = get_db()
    count = conn.execute('''SELECT COUNT(*) as count FROM notifications 
                            WHERE user_id = ? AND is_read = 0''',
                         (session['user']['id'],)).fetchone()['count']
    conn.close()
    
    return jsonify({'count': count})

# ==================== MATCH FUNCTIONS ====================
def calculate_match_score(lost_item, found_item):
    score = 0
    
    if lost_item['category'] == found_item['category']:
        score += 30
    
    name_similarity = calculate_text_similarity(lost_item['item_name'], found_item['item_name'])
    score += name_similarity * 30
    
    if lost_item['location'] == found_item['location']:
        score += 25
    
    try:
        lost_date = datetime.strptime(lost_item['date_lost'], '%Y-%m-%d')
        found_date = datetime.strptime(found_item['date_found'], '%Y-%m-%d')
        days_diff = (found_date - lost_date).days
        
        if 0 <= days_diff <= 30:
            if days_diff <= 7:
                score += 20
            elif days_diff <= 14:
                score += 15
            else:
                score += 10
    except:
        pass
    
    if lost_item['description'] and found_item['description']:
        desc_similarity = calculate_text_similarity(lost_item['description'], found_item['description'])
        score += desc_similarity * 15
    
    return min(100, round(score))

def calculate_text_similarity(text1, text2):
    if not text1 or not text2:
        return 0
    
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())
    
    common_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 
                   'of', 'with', 'by', 'from', 'up', 'about', 'into', 'through', 'during',
                   'before', 'after', 'my', 'your', 'his', 'her', 'its', 'their'}
    
    words1 = words1 - common_words
    words2 = words2 - common_words
    
    if not words1 or not words2:
        return 0
    
    intersection = words1.intersection(words2)
    union = words1.union(words2)
    
    return len(intersection) / len(union)

# ==================== ADMIN ROUTES ====================
@app.route('/admin/dashboard')
def admin_dashboard():
    if 'user' not in session or session['user']['role'] != 'admin':
        flash("Access denied!", "danger")
        return redirect(url_for('login'))
    
    conn = get_db()
    now = datetime.now()
    
    total_users = conn.execute("SELECT COUNT(*) as count FROM users").fetchone()['count']
    total_lost = conn.execute("SELECT COUNT(*) as count FROM lost_items").fetchone()['count']
    total_found = conn.execute("SELECT COUNT(*) as count FROM found_items").fetchone()['count']
    pending_claims = conn.execute("SELECT COUNT(*) as count FROM claims WHERE status = 'pending'").fetchone()['count']
    resolved_count = conn.execute("SELECT COUNT(*) as count FROM item_history").fetchone()['count']
    
    recent_lost = conn.execute('''SELECT * FROM lost_items WHERE status = 'pending'
                                   ORDER BY created_at DESC LIMIT 5''').fetchall()
    recent_found = conn.execute('''SELECT * FROM found_items WHERE status = 'available'
                                    ORDER BY created_at DESC LIMIT 5''').fetchall()
    
    conn.close()
    
    return render_template('admin_dashboard.html',
                         user=session['user'],
                         total_users=total_users,
                         total_lost=total_lost,
                         total_found=total_found,
                         pending_claims=pending_claims,
                         resolved_count=resolved_count,
                         lost_items=[dict(l) for l in recent_lost],
                         found_items=[dict(f) for f in recent_found],
                         now=now)

@app.route('/admin/lost-items')
def admin_lost_items():
    if 'user' not in session or session['user']['role'] != 'admin':
        flash("Access denied!", "danger")
        return redirect(url_for('login'))
    
    page = int(request.args.get('page', 1))
    per_page = 20
    search = request.args.get('search', '')
    category = request.args.get('category', '')
    status = request.args.get('status', 'all')
    
    conn = get_db()
    
    sql = """SELECT li.*, u.full_name as reporter_name, u.email as reporter_email 
             FROM lost_items li JOIN users u ON li.user_id = u.id WHERE 1=1"""
    params = []
    
    if search:
        sql += " AND (li.item_name LIKE ? OR li.description LIKE ? OR li.location LIKE ?)"
        search_term = f'%{search}%'
        params.extend([search_term, search_term, search_term])
    
    if category:
        sql += " AND li.category = ?"
        params.append(category)
    
    if status != 'all':
        sql += " AND li.status = ?"
        params.append(status)
    
    count_sql = sql.replace("li.*, u.full_name as reporter_name, u.email as reporter_email", "COUNT(*) as count")
    total = conn.execute(count_sql, params).fetchone()['count']
    
    sql += " ORDER BY li.created_at DESC LIMIT ? OFFSET ?"
    params.extend([per_page, (page-1)*per_page])
    
    items = conn.execute(sql, params).fetchall()
    
    total_lost = conn.execute("SELECT COUNT(*) as count FROM lost_items").fetchone()['count']
    total_found = conn.execute("SELECT COUNT(*) as count FROM found_items").fetchone()['count']
    pending_claims = conn.execute("SELECT COUNT(*) as count FROM claims WHERE status = 'pending'").fetchone()['count']
    resolved_count = conn.execute("SELECT COUNT(*) as count FROM item_history").fetchone()['count']
    
    conn.close()
    
    total_pages = (total + per_page - 1) // per_page
    
    return render_template('admin_lost_items.html',
                         user=session['user'],
                         items=[dict(item) for item in items],
                         total=total,
                         page=page,
                         total_pages=total_pages,
                         search=search,
                         category=category,
                         status=status,
                         total_lost=total_lost,
                         total_found=total_found,
                         pending_claims=pending_claims,
                         resolved_count=resolved_count,
                         now=datetime.now())

@app.route('/admin/found-items')
def admin_found_items():
    if 'user' not in session or session['user']['role'] != 'admin':
        flash("Access denied!", "danger")
        return redirect(url_for('login'))
    
    page = int(request.args.get('page', 1))
    per_page = 20
    search = request.args.get('search', '')
    category = request.args.get('category', '')
    status = request.args.get('status', 'all')
    
    conn = get_db()
    
    sql = """SELECT fi.*, u.full_name as reporter_name, u.email as reporter_email 
             FROM found_items fi JOIN users u ON fi.user_id = u.id WHERE 1=1"""
    params = []
    
    if search:
        sql += " AND (fi.item_name LIKE ? OR fi.description LIKE ? OR fi.location LIKE ?)"
        search_term = f'%{search}%'
        params.extend([search_term, search_term, search_term])
    
    if category:
        sql += " AND fi.category = ?"
        params.append(category)
    
    if status != 'all':
        sql += " AND fi.status = ?"
        params.append(status)
    
    count_sql = sql.replace("fi.*, u.full_name as reporter_name, u.email as reporter_email", "COUNT(*) as count")
    total = conn.execute(count_sql, params).fetchone()['count']
    
    sql += " ORDER BY fi.created_at DESC LIMIT ? OFFSET ?"
    params.extend([per_page, (page-1)*per_page])
    
    items = conn.execute(sql, params).fetchall()
    
    total_lost = conn.execute("SELECT COUNT(*) as count FROM lost_items").fetchone()['count']
    total_found = conn.execute("SELECT COUNT(*) as count FROM found_items").fetchone()['count']
    pending_claims = conn.execute("SELECT COUNT(*) as count FROM claims WHERE status = 'pending'").fetchone()['count']
    resolved_count = conn.execute("SELECT COUNT(*) as count FROM item_history").fetchone()['count']
    
    conn.close()
    
    total_pages = (total + per_page - 1) // per_page
    
    return render_template('admin_found_items.html',
                         user=session['user'],
                         items=[dict(item) for item in items],
                         total=total,
                         page=page,
                         total_pages=total_pages,
                         search=search,
                         category=category,
                         status=status,
                         total_lost=total_lost,
                         total_found=total_found,
                         pending_claims=pending_claims,
                         resolved_count=resolved_count,
                         now=datetime.now())
@app.route('/admin/pending-claims')
def admin_pending_claims():
    if 'user' not in session or session['user']['role'] != 'admin':
        flash("Access denied! This area is for administrators only.", "danger")
        return redirect(url_for('login'))
    
    conn = get_db()
    now = datetime.now()
    
    # Get all pending claims
    pending_claims_list = conn.execute('''
        SELECT 
            c.id,
            c.message,
            c.created_at,
            c.status,
            c.claimant_id,
            c.item_id as found_item_id,
            
            -- Claimant details
            claimant.full_name as claimant_name,
            claimant.email as claimant_email,
            claimant.phone as claimant_phone,
            claimant.student_number as claimant_student_number,
            
            -- Found item details
            fi.id as found_item_id,
            fi.item_name as found_item_name,
            fi.description as found_item_description,
            fi.date_found as found_item_date,
            fi.location as found_item_location,
            fi.image_path as found_item_image,
            fi.category as found_item_category,
            fi.user_id as finder_id,
            fi.contact_name as finder_contact_name,
            fi.contact_email as finder_contact_email,
            fi.contact_phone as finder_contact_phone,
            
            -- Finder details
            finder.full_name as finder_name,
            finder.email as finder_email,
            finder.phone as finder_phone
            
        FROM claims c
        JOIN users claimant ON c.claimant_id = claimant.id
        JOIN found_items fi ON c.item_id = fi.id
        JOIN users finder ON fi.user_id = finder.id
        WHERE c.status = 'pending'
        ORDER BY c.created_at DESC
    ''').fetchall()
    
    # Process each claim to get the claimant's lost items
    processed_claims = []
    for claim in pending_claims_list:
        claim_dict = dict(claim)
        
        # Get the claimant's lost items (what they reported as lost)
        lost_items = conn.execute('''
            SELECT 
                id,
                item_name,
                description,
                date_lost,
                location,
                image_path,
                category,
                contact_name,
                contact_email,
                contact_phone
            FROM lost_items 
            WHERE user_id = ? AND status = 'pending'
            ORDER BY created_at DESC
            LIMIT 1
        ''', (claim_dict['claimant_id'],)).fetchone()
        
        if lost_items:
            claim_dict['lost_item_name'] = lost_items['item_name']
            claim_dict['lost_item_description'] = lost_items['description'] or ''
            claim_dict['lost_item_location'] = lost_items['location'] or ''
            claim_dict['lost_item_date'] = lost_items['date_lost'] or ''
            claim_dict['lost_item_image'] = lost_items['image_path'] or ''
            claim_dict['lost_item_category'] = lost_items['category'] or ''
            claim_dict['lost_owner_name'] = lost_items['contact_name'] or claim_dict['claimant_name']
            claim_dict['lost_owner_email'] = lost_items['contact_email'] or claim_dict['claimant_email']
            claim_dict['lost_owner_phone'] = lost_items['contact_phone'] or claim_dict['claimant_phone']
        else:
            claim_dict['lost_item_name'] = 'No lost item reported'
            claim_dict['lost_item_description'] = 'This user has not reported any lost items'
            claim_dict['lost_item_location'] = 'N/A'
            claim_dict['lost_item_date'] = 'N/A'
            claim_dict['lost_item_image'] = ''
            claim_dict['lost_item_category'] = 'N/A'
            claim_dict['lost_owner_name'] = claim_dict['claimant_name']
            claim_dict['lost_owner_email'] = claim_dict['claimant_email']
            claim_dict['lost_owner_phone'] = claim_dict['claimant_phone']
        
        # Set found item fields
        claim_dict['found_item_name'] = claim_dict.get('found_item_name') or ''
        claim_dict['found_item_description'] = claim_dict.get('found_item_description') or ''
        claim_dict['found_item_location'] = claim_dict.get('found_item_location') or ''
        claim_dict['found_item_date'] = claim_dict.get('found_item_date') or ''
        claim_dict['found_item_image'] = claim_dict.get('found_item_image') or ''
        claim_dict['found_item_category'] = claim_dict.get('found_item_category') or ''
        claim_dict['found_owner_name'] = claim_dict.get('finder_name') or ''
        claim_dict['found_owner_email'] = claim_dict.get('finder_email') or ''
        claim_dict['found_owner_phone'] = claim_dict.get('finder_phone') or ''
        
        processed_claims.append(claim_dict)
    
    pending_claims_count = len(pending_claims_list)
    conn.close()
    
    return render_template('admin_claims.html',
                         user=session['user'],
                         claims=processed_claims,
                         pending_claims=pending_claims_count,
                         now=now)

     @app.route('/admin/history')
def admin_history():
    if 'user' not in session or session['user']['role'] != 'admin':
        flash("Access denied! This area is for administrators only.", "danger")
        return redirect(url_for('login'))
    
    conn = get_db()
    now = datetime.now()
    
    # Get all resolved items from history
    history_items = conn.execute('''
        SELECT 
            h.*,
            lost_user.full_name as lost_by_name,
            found_user.full_name as found_by_name,
            claimed_user.full_name as claimed_by_name,
            admin_user.full_name as resolved_by_name
        FROM item_history h
        LEFT JOIN users lost_user ON h.lost_by_id = lost_user.id
        LEFT JOIN users found_user ON h.found_by_id = found_user.id
        LEFT JOIN users claimed_user ON h.claimed_by_id = claimed_user.id
        LEFT JOIN users admin_user ON h.resolved_by = admin_user.id
        ORDER BY h.resolved_at DESC
        LIMIT 100
    ''').fetchall()
    
    # Get statistics
    total_resolved = conn.execute("SELECT COUNT(*) as count FROM item_history").fetchone()['count']
    total_lost_resolved = conn.execute("SELECT COUNT(*) as count FROM item_history WHERE item_type = 'lost'").fetchone()['count']
    total_found_resolved = conn.execute("SELECT COUNT(*) as count FROM item_history WHERE item_type = 'found'").fetchone()['count']
    
    # Get counts for sidebar badges
    total_lost = conn.execute("SELECT COUNT(*) as count FROM lost_items").fetchone()['count']
    total_found = conn.execute("SELECT COUNT(*) as count FROM found_items").fetchone()['count']
    pending_claims = conn.execute("SELECT COUNT(*) as count FROM claims WHERE status = 'pending'").fetchone()['count']
    resolved_count = total_resolved
    
    conn.close()
    
    return render_template('admin_history.html',
                         user=session['user'],
                         history=[dict(h) for h in history_items],
                         total_resolved=total_resolved,
                         total_lost_resolved=total_lost_resolved,
                         total_found_resolved=total_found_resolved,
                         total_lost=total_lost,
                         total_found=total_found,
                         pending_claims=pending_claims,
                         resolved_count=resolved_count,
                         now=now)
@app.route('/admin/claim/<int:claim_id>/<string:action>', methods=['POST'])
def admin_handle_claim(claim_id, action):
    if 'user' not in session or session['user']['role'] != 'admin':
        flash("Access denied!", "danger")
        return redirect(url_for('login'))
    
    if action not in ['approve', 'reject']:
        flash("Invalid action", "danger")
        return redirect(url_for('admin_dashboard'))
    
    conn = get_db()
    status = 'approved' if action == 'approve' else 'rejected'
    
    conn.execute('''UPDATE claims SET status = ?, reviewed_by = ?, reviewed_at = CURRENT_TIMESTAMP
                    WHERE id = ?''', (status, session['user']['id'], claim_id))
    
    if status == 'approved':
        conn.execute('''INSERT INTO notifications (user_id, type, message, created_at, is_read)
                        SELECT claimant_id, 'claim_approved', 
                        'Your claim has been approved! You can now arrange pickup.', ?, 0
                        FROM claims WHERE id = ?''', (datetime.now().isoformat(), claim_id))
        conn.commit()
        
        try:
            send_claim_approved_notification(claim_id)
        except Exception as e:
            print(f"Email error: {e}")
    
    conn.commit()
    conn.close()
    
    flash(f"Claim {status}!", "success")
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete/lost/<int:item_id>', methods=['POST'])
def admin_delete_lost(item_id):
    if 'user' not in session or session['user']['role'] != 'admin':
        flash("Access denied!", "danger")
        return redirect(url_for('login'))
    
    conn = get_db()
    item = conn.execute("SELECT * FROM lost_items WHERE id = ?", (item_id,)).fetchone()
    
    if item:
        conn.execute("DELETE FROM lost_items WHERE id = ?", (item_id,))
        conn.commit()
        flash(f"Lost item deleted!", "success")
    else:
        flash("Item not found!", "danger")
    
    conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete/found/<int:item_id>', methods=['POST'])
def admin_delete_found(item_id):
    if 'user' not in session or session['user']['role'] != 'admin':
        flash("Access denied!", "danger")
        return redirect(url_for('login'))
    
    conn = get_db()
    item = conn.execute("SELECT * FROM found_items WHERE id = ?", (item_id,)).fetchone()
    
    if item:
        conn.execute("DELETE FROM found_items WHERE id = ?", (item_id,))
        conn.commit()
        flash(f"Found item deleted!", "success")
    else:
        flash("Item not found!", "danger")
    
    conn.close()
    return redirect(url_for('admin_dashboard'))

# ==================== REPORT ROUTES ====================
@app.route('/report-lost', methods=['GET', 'POST'])
def report_lost():
    if 'user' not in session:
        flash("Please login to report a lost item", "warning")
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        try:
            user_id = session['user']['id']
            item_name = request.form['item_name']
            category = request.form['category']
            description = request.form['description']
            date_lost = request.form['date_lost']
            location = request.form['location']
            contact_name = request.form['contact_name']
            contact_email = request.form['contact_email']
            contact_phone = request.form.get('contact_phone', '')
            reward_offered = 1 if request.form.get('reward_offered') else 0
            
            image_path = None
            if 'image' in request.files:
                file = request.files['image']
                if file and file.filename and allowed_file(file.filename):
                    filename = secure_filename(f"{user_id}_{datetime.now().timestamp()}_{file.filename}")
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], 'lost', filename))
                    image_path = f"uploads/lost/{filename}"
            
            conn = get_db()
            conn.execute('''INSERT INTO lost_items 
                            (user_id, item_name, category, description, date_lost, location,
                             contact_name, contact_email, contact_phone, reward_offered, image_path)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                         (user_id, item_name, category, description, date_lost, location,
                          contact_name, contact_email, contact_phone, reward_offered, image_path))
            conn.commit()
            conn.close()
            
            flash("Lost item reported successfully!", "success")
            return redirect(url_for('dashboard'))
            
        except Exception as e:
            flash(f"Error reporting item: {str(e)}", "danger")
            return redirect(url_for('report_lost'))
    
    now = datetime.now()
    return render_template('report_lost.html', user=session['user'], now=now)

@app.route('/report-found', methods=['GET', 'POST'])
def report_found():
    if 'user' not in session:
        flash("Please login to report a found item", "warning")
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        try:
            user_id = session['user']['id']
            item_name = request.form['item_name']
            category = request.form['category']
            description = request.form['description']
            date_found = request.form['date_found']
            location = request.form['location']
            contact_name = request.form['contact_name']
            contact_email = request.form['contact_email']
            contact_phone = request.form.get('contact_phone', '')
            
            image_path = None
            if 'image' in request.files:
                file = request.files['image']
                if file and file.filename and allowed_file(file.filename):
                    filename = secure_filename(f"{user_id}_{datetime.now().timestamp()}_{file.filename}")
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], 'found', filename))
                    image_path = f"uploads/found/{filename}"
            
            conn = get_db()
            conn.execute('''INSERT INTO found_items 
                            (user_id, item_name, category, description, date_found, location,
                             contact_name, contact_email, contact_phone, image_path)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                         (user_id, item_name, category, description, date_found, location,
                          contact_name, contact_email, contact_phone, image_path))
            conn.commit()
            conn.close()
            
            flash("Found item reported successfully!", "success")
            return redirect(url_for('dashboard'))
            
        except Exception as e:
            flash(f"Error reporting item: {str(e)}", "danger")
            return redirect(url_for('report_found'))
    
    now = datetime.now()
    return render_template('report_found.html', user=session['user'], now=now)

# ==================== VIEW ROUTES ====================
@app.route('/all-lost')
def all_lost_items():
    if 'user' not in session:
        flash("Please login to view items", "warning")
        return redirect(url_for('login'))
    
    conn = get_db()
    items = conn.execute('''SELECT li.*, u.full_name as reporter_name 
                            FROM lost_items li 
                            JOIN users u ON li.user_id = u.id 
                            ORDER BY li.created_at DESC''').fetchall()
    conn.close()
    
    return render_template('all_lost_items.html',
                         user=session['user'],
                         items=[dict(item) for item in items])

@app.route('/all-found')
def all_found_items():
    if 'user' not in session:
        flash("Please login to view items", "warning")
        return redirect(url_for('login'))
    
    conn = get_db()
    items = conn.execute('''SELECT fi.*, u.full_name as reporter_name 
                            FROM found_items fi 
                            JOIN users u ON fi.user_id = u.id 
                            WHERE fi.status = 'available'
                            ORDER BY fi.created_at DESC''').fetchall()
    conn.close()
    
    return render_template('all_found_items.html',
                         user=session['user'],
                         items=[dict(item) for item in items])

@app.route('/my-lost-items')
def my_lost_items():
    if 'user' not in session:
        flash("Please login first!", "warning")
        return redirect(url_for('login'))
    
    conn = get_db()
    items = conn.execute('''SELECT * FROM lost_items 
                            WHERE user_id = ? 
                            ORDER BY created_at DESC''', 
                        (session['user']['id'],)).fetchall()
    conn.close()
    
    return render_template('my_lost_items.html',
                         user=session['user'],
                         lost_items=[dict(item) for item in items])

@app.route('/my-found-items')
def my_found_items():
    if 'user' not in session:
        flash("Please login first!", "warning")
        return redirect(url_for('login'))
    
    conn = get_db()
    items = conn.execute('''SELECT * FROM found_items 
                            WHERE user_id = ? 
                            ORDER BY created_at DESC''', 
                        (session['user']['id'],)).fetchall()
    conn.close()
    
    return render_template('my_found_items.html',
                         user=session['user'],
                         found_items=[dict(item) for item in items])

@app.route('/matches')
def view_matches():
    if 'user' not in session:
        flash("Please login to view matches", "warning")
        return redirect(url_for('login'))
    
    user_id = session['user']['id']
    
    # Get filter parameters
    min_score = int(request.args.get('min_score', 0))
    category = request.args.get('category', '')
    sort = request.args.get('sort', 'score')
    
    conn = get_db()
    
    # Get user's lost items
    lost_items = conn.execute('''SELECT * FROM lost_items 
                                  WHERE user_id = ? AND status = 'pending'
                                  ORDER BY created_at DESC''', 
                              (user_id,)).fetchall()
    
    # Get available found items
    found_items = conn.execute('''SELECT * FROM found_items 
                                   WHERE status = 'available'
                                   ORDER BY created_at DESC''').fetchall()
    
    matches = []
    high_confidence = 0
    
    # Compare each lost item with each found item
    for lost in lost_items:
        lost_dict = dict(lost)
        for found in found_items:
            found_dict = dict(found)
            
            # Calculate match score
            score = calculate_match_score(lost_dict, found_dict)
            
            # Apply filters
            if score < min_score:
                continue
            
            if category and lost_dict['category'] != category:
                continue
            
            # Get match factors
            factors = get_match_factors(lost_dict, found_dict)
            
            matches.append({
                'score': score,
                'lost_item': lost_dict,
                'found_item': found_dict,
                'factors': factors,
                'date': found_dict['date_found']
            })
            
            if score >= 70:
                high_confidence += 1
    
    # Sort matches
    if sort == 'score':
        matches.sort(key=lambda x: x['score'], reverse=True)
    elif sort == 'date':
        matches.sort(key=lambda x: x['date'], reverse=True)
    
    # Get user's pending claims count
    pending_claims = conn.execute('''SELECT COUNT(*) as count FROM claims 
                                      WHERE claimant_id = ? AND status = 'pending' ''',
                                  (user_id,)).fetchone()['count']
    
    # Get categories for filter
    categories = conn.execute("SELECT DISTINCT category FROM lost_items WHERE user_id = ?", (user_id,)).fetchall()
    categories = [c['category'] for c in categories]
    
    conn.close()
    
    return render_template('matches.html',
                         user=session['user'],
                         matches=matches,
                         total_matches=len(matches),
                         high_confidence_matches=high_confidence,
                         pending_claims=pending_claims,
                         min_score=min_score,
                         category=category,
                         sort=sort,
                         categories=categories)

def get_match_factors(lost_item, found_item):
    """Get detailed factors for why items match"""
    factors = {
        'category_match': lost_item['category'] == found_item['category'],
        'name_similarity': round(calculate_text_similarity(
            lost_item['item_name'], found_item['item_name']
        ) * 100),
        'location_match': lost_item['location'] == found_item['location'],
        'date_proximity': 0,
        'description_match': False,
        'exact_match': False
    }
    
    # Check date proximity
    try:
        lost_date = datetime.strptime(lost_item['date_lost'], '%Y-%m-%d')
        found_date = datetime.strptime(found_item['date_found'], '%Y-%m-%d')
        days_diff = (found_date - lost_date).days
        
        if 0 <= days_diff <= 30:
            if days_diff <= 7:
                factors['date_proximity'] = 20
            elif days_diff <= 14:
                factors['date_proximity'] = 15
            else:
                factors['date_proximity'] = 10
    except:
        pass
    
    # Check description similarity
    if lost_item.get('description') and found_item.get('description'):
        similarity = calculate_text_similarity(
            lost_item['description'],
            found_item['description']
        )
        factors['description_match'] = similarity > 0.3
    
    # Check for exact match
    if (lost_item['item_name'].lower() == found_item['item_name'].lower() and
        lost_item['category'] == found_item['category']):
        factors['exact_match'] = True
    
    return factors

@app.route('/item/<string:item_type>/<int:item_id>')
def view_item(item_type, item_id):
    if 'user' not in session:
        flash("Please login to view item details", "warning")
        return redirect(url_for('login'))
    
    conn = get_db()
    
    if item_type == 'lost':
        item = conn.execute('''SELECT li.*, u.full_name as reporter_name
                               FROM lost_items li
                               JOIN users u ON li.user_id = u.id
                               WHERE li.id = ?''', (item_id,)).fetchone()
    else:
        item = conn.execute('''SELECT fi.*, u.full_name as reporter_name
                               FROM found_items fi
                               JOIN users u ON fi.user_id = u.id
                               WHERE fi.id = ?''', (item_id,)).fetchone()
    
    conn.close()
    
    if not item:
        flash("Item not found", "danger")
        return redirect(url_for('search'))
    
    return render_template('item_details.html',
                         user=session['user'],
                         item=dict(item),
                         item_type=item_type)

@app.route('/claim/<string:item_type>/<int:item_id>', methods=['POST'])
def submit_claim(item_type, item_id):
    if 'user' not in session:
        flash("Please login to submit a claim", "warning")
        return redirect(url_for('login'))
    
    claimant_id = session['user']['id']
    message = request.form.get('message', '')
    
    conn = get_db()
    
    existing = conn.execute('''SELECT * FROM claims 
                                WHERE item_id = ? AND item_type = ? AND claimant_id = ?''',
                             (item_id, item_type, claimant_id)).fetchone()
    
    if existing:
        conn.close()
        flash("You have already submitted a claim for this item", "danger")
        return redirect(url_for('view_item', item_type=item_type, item_id=item_id))
    
    conn.execute('''INSERT INTO claims (item_id, item_type, claimant_id, message)
                    VALUES (?, ?, ?, ?)''',
                 (item_id, item_type, claimant_id, message))
    conn.commit()
    conn.close()
    
    flash("Claim submitted successfully! An admin will review it.", "success")
    return redirect(url_for('dashboard'))

@app.route('/search')
def search():
    if 'user' not in session:
        flash("Please login to search items", "warning")
        return redirect(url_for('login'))
    
    query = request.args.get('q', '').strip()
    category = request.args.get('category', '')
    item_type = request.args.get('type', 'all')
    
    conn = get_db()
    
    lost_items = []
    found_items = []
    
    if item_type in ['all', 'lost']:
        lost_items = conn.execute('''SELECT *, 'lost' as type FROM lost_items 
                                      WHERE (item_name LIKE ? OR description LIKE ?) 
                                      AND category LIKE ?
                                      ORDER BY created_at DESC''',
                                  (f'%{query}%', f'%{query}%', f'%{category}%')).fetchall()
    
    if item_type in ['all', 'found']:
        found_items = conn.execute('''SELECT *, 'found' as type FROM found_items 
                                       WHERE status = 'available'
                                       AND (item_name LIKE ? OR description LIKE ?)
                                       AND category LIKE ?
                                       ORDER BY created_at DESC''',
                                   (f'%{query}%', f'%{query}%', f'%{category}%')).fetchall()
    
    conn.close()
    
    return render_template('search_results.html',
                         user=session['user'],
                         query=query,
                         category=category,
                         item_type=item_type,
                         lost_items=[dict(li) for li in lost_items],
                         found_items=[dict(fi) for fi in found_items])

@app.route('/logout')
def logout():
    session.pop('user', None)
    flash("You have been logged out.", "info")
    return redirect(url_for('home'))

if __name__ == "__main__":
    app.run(debug=True)