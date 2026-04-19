import os
import random
import string
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_bcrypt import Bcrypt
from sqlalchemy import text, func
from collections import defaultdict
import threading
import requests # Used for Brevo API

# Setup Flask to look for HTML files in the 'templates' folder
app = Flask(__name__, template_folder='templates', static_folder='static')

# ==========================================
# CORS CONFIGURATION
# ==========================================
CORS(app, resources={r"/*": {"origins": "*"}})

# ==========================================
# DATABASE CONFIGURATION
# ==========================================
db_url = os.environ.get('DATABASE_URL', 'postgresql://neondb_owner:npg_aG9UQpT6Nswf@ep-wild-resonance-a1xpry7g-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# SERVERLESS POOLING FIX
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 300,
    'pool_timeout': 20,
}

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

verification_codes = {}

# ==========================================
# BREVO API EMAIL SETUP
# ==========================================
# SAFE METHOD: Retrieving the key from Railway Variables (Environment)
BREVO_API_KEY = os.environ.get('BREVO_API_KEY')
SENDER_EMAIL = 'oathofcare@gmail.com'
SENDER_NAME = 'Oath of Care System'

def send_brevo_email_task(to_email, subject, body_text):
    if not BREVO_API_KEY:
        print("❌ [BREVO ERROR] No API Key set in Environment Variables!")
        return

    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json"
    }
    payload = {
        "sender": {"name": SENDER_NAME, "email": SENDER_EMAIL},
        "to": [{"email": to_email}],
        "subject": subject,
        "textContent": body_text
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        if response.status_code in [200, 201, 202]:
            print(f"✅ [BREVO] Successfully sent email to: {to_email}")
        else:
            print(f"❌ [BREVO ERROR] Code: {response.status_code}, Response: {response.text}")
    except Exception as e:
        print(f"❌ [BREVO EXCEPTION] Network Error: {e}")

def send_async_email(to_email, subject, body_text):
    # Using Threading to prevent frontend timeout while sending to the API
    threading.Thread(target=send_brevo_email_task, args=(to_email, subject, body_text)).start()

# ==========================================
# DATABASE MODELS
# ==========================================
class Admin(db.Model):
    __tablename__ = 'admin'
    AdminID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    Email = db.Column(db.String(120), unique=True, nullable=False)
    PasswordHash = db.Column(db.String(255), nullable=False)
    IsFirstLogin = db.Column(db.Boolean, default=True)

class ClientAccount(db.Model):
    __tablename__ = 'patient_account'
    ClientID = db.Column('PatientID', db.Integer, primary_key=True, autoincrement=True)
    Fname = db.Column(db.String(100), nullable=False)
    Lname = db.Column(db.String(100), nullable=False)
    Email = db.Column(db.String(120), unique=True, nullable=False)
    PasswordHash = db.Column(db.String(255), nullable=False)

class PharmacyAccount(db.Model):
    __tablename__ = 'pharmacy_account'
    PharmacyAccountID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    Email = db.Column(db.String(120), unique=True, nullable=False)
    PasswordHash = db.Column(db.String(255), nullable=False)
    LastName = db.Column(db.String(100), nullable=True)
    FirstName = db.Column(db.String(100), nullable=True)
    pharmacies = db.relationship('Pharmacy', backref='account', lazy=True)

class Barangay(db.Model):
    __tablename__ = 'barangay'
    BarangayID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    BarangayName = db.Column(db.String(100), unique=True, nullable=False)

class Pharmacy(db.Model):
    __tablename__ = 'pharmacy'
    PharmacyID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    PharmacyName = db.Column(db.String(150), nullable=False)
    ContactNumber = db.Column(db.String(20), nullable=False)
    FullAddress = db.Column(db.Text, nullable=False)
    GoogleMapLink = db.Column(db.Text, nullable=True)
    LogoPhotoPath = db.Column(db.Text, nullable=True)
    PermitPhotoPath = db.Column(db.Text, nullable=True)
    IsActive = db.Column(db.Boolean, default=False)
    OpenTime = db.Column(db.String(50), nullable=True)
    CloseTime = db.Column(db.String(50), nullable=True)
    BarangayID = db.Column(db.Integer, db.ForeignKey('barangay.BarangayID'), nullable=False)
    PharmacyAccountID = db.Column(db.Integer, db.ForeignKey('pharmacy_account.PharmacyAccountID'), nullable=False)
    medicines = db.relationship('Medicine', backref='pharmacy', lazy=True)
    statuses = db.relationship('PharmacyStatus', backref='pharmacy', lazy=True)

class PharmacyStatus(db.Model):
    __tablename__ = 'pharmacy_status'
    StatusID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    PharmacyID = db.Column(db.Integer, db.ForeignKey('pharmacy.PharmacyID'), nullable=False)
    AdminID = db.Column(db.Integer, db.ForeignKey('admin.AdminID'), nullable=True)
    AccountStatus = db.Column(db.String(50), default='Pending')
    LastLogin = db.Column(db.DateTime, nullable=True)
    IsDeactivated = db.Column(db.Boolean, default=False)
    IsArchived = db.Column(db.Boolean, default=False)
    StrikeCount = db.Column(db.Integer, default=0) # Active penalty (resets upon update)
    TotalLifetimeStrikes = db.Column(db.Integer, default=0) # Non-resetting total 'No' for admin reports
    LastStockUpdate = db.Column(db.DateTime, default=datetime.utcnow)

class Medicine(db.Model):
    __tablename__ = 'medicine'
    MedicineID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    MedicineName = db.Column(db.String(150), nullable=False)
    Description = db.Column(db.Text, nullable=True) # Used as Category
    Price = db.Column(db.Numeric(10, 2), nullable=False)
    IsPrescriptionRequired = db.Column(db.Boolean, default=False)
    InStock = db.Column(db.Boolean, default=True)
    StrikeCount = db.Column(db.Integer, default=0) # Strike for a specific medicine
    PharmacyID = db.Column(db.Integer, db.ForeignKey('pharmacy.PharmacyID'), nullable=False)

class SearchLog(db.Model):
    __tablename__ = 'search_log'
    SearchLogID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    BarangayID = db.Column(db.Integer, db.ForeignKey('barangay.BarangayID'), nullable=True)
    ClientID = db.Column('PatientID', db.Integer, db.ForeignKey('patient_account.PatientID'), nullable=True)
    MedicineID = db.Column(db.Integer, db.ForeignKey('medicine.MedicineID'), nullable=True)
    CreatedAt = db.Column(db.DateTime, default=datetime.utcnow)
    HasResult = db.Column(db.Boolean, default=False)

class PharmacyReport(db.Model):
    __tablename__ = 'pharmacy_report'
    ReportID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    PharmacyID = db.Column(db.Integer, db.ForeignKey('pharmacy.PharmacyID'), nullable=False)
    ClientID = db.Column(db.Integer, db.ForeignKey('patient_account.PatientID'), nullable=False)
    ReportDate = db.Column(db.DateTime, default=datetime.utcnow)
    IsOutOfStock = db.Column(db.Boolean, default=True)

class PharmacyVisibilityLog(db.Model):
    __tablename__ = 'pharmacy_visibility_log'
    LogID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    PharmacyID = db.Column(db.Integer, db.ForeignKey('pharmacy.PharmacyID'), nullable=False)
    Action = db.Column(db.String(50)) # 'Appeared', 'Clicked'
    MedicineName = db.Column(db.String(150), nullable=True)
    CreatedAt = db.Column(db.DateTime, default=datetime.utcnow)

# ==========================================
# WEB PORTAL ROUTES
# ==========================================
@app.route('/')
def serve_client_portal():
    return render_template('client.html')

@app.route('/pharmacy')
def serve_pharmacy_portal():
    return render_template('pharmacy.html')

@app.route('/admin')
def serve_admin_portal():
    return render_template('admin.html')

# ==========================================
# AUTHENTICATION & REGISTRATION ENDPOINTS
# ==========================================
@app.route('/api/send-verification', methods=['POST'])
def send_verification():
    data = request.json
    email = data.get('email')
    if not email: return jsonify({'error': 'Email is required'}), 400
        
    code = ''.join(random.choices(string.digits, k=6))
    verification_codes[email] = code
    
    try:
        subject = 'Oath of Care - Verification Code'
        body = f"""Your 6-digit verification code for Oath of Care is: {code}

NOTE: Please check your SPAM or JUNK folder if you do not see this in your inbox.
Do not share this code with anyone."""
        
        # Using Brevo API from Environment Variables
        send_async_email(email, subject, body)
        
        return jsonify({'message': 'Verification code sent successfully. Please check your Inbox and Spam folders.'})
    except Exception as e:
        print("Mail Error:", e)
        return jsonify({'error': 'Failed to send email. Check credentials or server status.'}), 500

@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    data = request.json
    email = data.get('email')
    code = data.get('code')
    if verification_codes.get(email) == code:
        return jsonify({'message': 'Code verified successfully'})
    return jsonify({'error': 'Invalid or expired code'}), 400

@app.route('/register-patient', methods=['POST'])
def register_client():
    data = request.json
    email = data.get('email')
    
    if ClientAccount.query.filter_by(Email=email).first():
        return jsonify({'error': 'This email is already registered as a client'}), 400

    hashed_pw = bcrypt.generate_password_hash(data.get('password')).decode('utf-8')
    try:
        new_client = ClientAccount(
            Fname=data.get('fname'),
            Lname=data.get('lname'),
            Email=email,
            PasswordHash=hashed_pw
        )
        db.session.add(new_client)
        db.session.commit()
        return jsonify({'message': 'Account created successfully!'}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Database error.'}), 500

@app.route('/register', methods=['POST'])
def register_pharmacy():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    barangay_name = data.get('barangay')

    if PharmacyAccount.query.filter_by(Email=email).first():
        return jsonify({'error': 'Email is already registered'}), 400

    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

    try:
        new_account = PharmacyAccount(Email=email, PasswordHash=hashed_password)
        db.session.add(new_account)
        db.session.flush()

        barangay = Barangay.query.filter_by(BarangayName=barangay_name).first()
        if not barangay:
            barangay = Barangay(BarangayName=barangay_name)
            db.session.add(barangay)
            db.session.flush()

        new_pharmacy = Pharmacy(
            PharmacyName=data.get('pharmacyName'),
            ContactNumber=data.get('contactNumber'),
            FullAddress=data.get('address'),
            GoogleMapLink=data.get('mapLink'),
            LogoPhotoPath=data.get('storePhoto'), 
            PermitPhotoPath=data.get('permitPhoto'), 
            OpenTime=data.get('openTime'),
            CloseTime=data.get('closeTime'),
            BarangayID=barangay.BarangayID,
            PharmacyAccountID=new_account.PharmacyAccountID
        )
        db.session.add(new_pharmacy)
        db.session.flush()

        new_status = PharmacyStatus(PharmacyID=new_pharmacy.PharmacyID, AccountStatus='Pending')
        db.session.add(new_status)
        db.session.commit()
        return jsonify({'message': 'Registration complete! Pending admin approval.'}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'A database error occurred.'}), 500

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    role = data.get('role')

    if role == 'patient':
        user = ClientAccount.query.filter_by(Email=email).first()
        if user and bcrypt.check_password_hash(user.PasswordHash, password):
            return jsonify({'message': 'Login successful', 'id': user.ClientID, 'name': f"{user.Fname} {user.Lname}", 'role': 'patient'}), 200
            
    elif role == 'pharmacy':
        user = PharmacyAccount.query.filter_by(Email=email).first()
        if user and bcrypt.check_password_hash(user.PasswordHash, password):
            pharmacy = Pharmacy.query.filter_by(PharmacyAccountID=user.PharmacyAccountID).first()
            if pharmacy:
                status = PharmacyStatus.query.filter_by(PharmacyID=pharmacy.PharmacyID).first()
                if status and status.AccountStatus == 'Pending':
                    return jsonify({'error': 'Your account is still pending admin approval.'}), 403
            return jsonify({'message': 'Login successful', 'id': pharmacy.PharmacyID if pharmacy else None, 'pharmacyName': pharmacy.PharmacyName if pharmacy else "Store", 'role': 'pharmacy'}), 200
            
    elif role == 'admin':
        admin = Admin.query.filter_by(Email=email).first()
        if admin and bcrypt.check_password_hash(admin.PasswordHash, password):
            return jsonify({'message': 'Admin login successful', 'id': admin.AdminID, 'role': 'admin'}), 200

    return jsonify({'error': 'Invalid email or password'}), 401

@app.route('/api/reset-password', methods=['POST'])
def reset_password():
    data = request.json
    email = data.get('email')
    user = ClientAccount.query.filter_by(Email=email).first()
    if not user:
        user = PharmacyAccount.query.filter_by(Email=email).first()
    if not user:
        return jsonify({'error': 'Account not found.'}), 404
        
    user.PasswordHash = bcrypt.generate_password_hash(data.get('password')).decode('utf-8')
    db.session.commit()
    return jsonify({'message': 'Password has been successfully reset.'}), 200

# ==========================================
# PHARMACY INVENTORY & EDIT ENDPOINTS
# ==========================================
@app.route('/api/pharmacy/profile/<int:pharm_id>', methods=['GET'])
def get_pharmacy_profile(pharm_id):
    try:
        pharmacy = Pharmacy.query.get(pharm_id)
        if not pharmacy: return jsonify({'error': 'Pharmacy not found'}), 404
        return jsonify({'name': pharmacy.PharmacyName, 'contact': pharmacy.ContactNumber, 'address': pharmacy.FullAddress, 'mapLink': pharmacy.GoogleMapLink, 'openTime': pharmacy.OpenTime, 'closeTime': pharmacy.CloseTime}), 200
    except Exception as e:
        return jsonify({'error': 'Database error'}), 500

@app.route('/api/pharmacy/update', methods=['POST'])
def update_pharmacy():
    data = request.json
    pharm_id = data.get('pharmacyId')
    try:
        pharmacy = Pharmacy.query.get(pharm_id)
        if pharmacy:
            pharmacy.PharmacyName = data.get('name')
            pharmacy.ContactNumber = data.get('contact')
            pharmacy.FullAddress = data.get('address')
            pharmacy.GoogleMapLink = data.get('mapLink')
            pharmacy.OpenTime = data.get('openTime')
            pharmacy.CloseTime = data.get('closeTime')
            db.session.commit()
            return jsonify({'message': 'Profile updated successfully!'}), 200
        return jsonify({'error': 'Pharmacy not found'}), 404
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Update failed'}), 500

@app.route('/api/medicines/<int:pharm_id>', methods=['GET'])
def get_medicines(pharm_id):
    try:
        medicines = Medicine.query.filter_by(PharmacyID=pharm_id).all()
        results = [{'id': med.MedicineID, 'name': med.MedicineName, 'category': med.Description, 'price': str(med.Price), 'status': 'In Stock' if med.InStock else 'Out of Stock'} for med in medicines]
        return jsonify(results), 200
    except Exception as e:
        return jsonify({'error': 'Failed to load inventory'}), 500

@app.route('/api/medicines', methods=['POST'])
def add_medicine():
    data = request.json
    pharm_id = data.get('pharmacyId')
    try:
        new_med = Medicine(
            MedicineName=data.get('name'),
            Price=data.get('price'),
            Description=data.get('category'),
            InStock=True if data.get('status') == 'In Stock' else False,
            PharmacyID=pharm_id
        )
        db.session.add(new_med)
        
        status = PharmacyStatus.query.filter_by(PharmacyID=pharm_id).first()
        if status:
            if status.IsDeactivated:
                status.IsDeactivated = False
                status.StrikeCount = 0 # Resets penalty upon update (Reactivation)
            status.LastStockUpdate = datetime.utcnow()

        db.session.commit()
        return jsonify({'message': f"{data.get('name')} added successfully and Account standing updated!"}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to add medicine.'}), 500

@app.route('/api/medicines/<int:med_id>/status', methods=['PUT'])
def update_med_status(med_id):
    data = request.json
    try:
        med = Medicine.query.get(med_id)
        if med:
            med.InStock = (data.get('status') == 'In Stock')
            med.StrikeCount = 0 # Resets the specific medicine strike if updated manually
            status = PharmacyStatus.query.filter_by(PharmacyID=med.PharmacyID).first()
            if status:
                if status.IsDeactivated:
                    status.IsDeactivated = False
                    status.StrikeCount = 0 # Resets penalty upon update
                status.LastStockUpdate = datetime.utcnow()
            db.session.commit()
            return jsonify({'success': True}), 200
        return jsonify({'error': 'Not found'}), 404
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Update failed'}), 500

@app.route('/api/medicines/<int:med_id>', methods=['PUT', 'DELETE'])
def handle_medicine(med_id):
    try:
        med = Medicine.query.get(med_id)
        if not med:
            return jsonify({'error': 'Not found'}), 404
            
        if request.method == 'DELETE':
            db.session.delete(med)
            db.session.commit()
            return jsonify({'message': 'Deleted successfully'}), 200
            
        if request.method == 'PUT':
            data = request.json
            if 'price' in data: med.Price = data['price']
            if 'category' in data: med.Description = data['category']
            
            status = PharmacyStatus.query.filter_by(PharmacyID=med.PharmacyID).first()
            if status:
                if status.IsDeactivated:
                    status.IsDeactivated = False
                    status.StrikeCount = 0
                status.LastStockUpdate = datetime.utcnow()
                
            db.session.commit()
            return jsonify({'success': True}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Database error'}), 500

# ==========================================
# ADVANCED SEARCH ENGINE ALGORITHM
# ==========================================
@app.route('/api/search', methods=['POST'])
def search_medicine():
    data = request.json
    medicine_query = data.get('medicine', '')
    barangay_query = data.get('barangay', '')
    
    try:
        query = db.session.query(Medicine, Pharmacy, Barangay, PharmacyStatus)\
            .join(Pharmacy, Medicine.PharmacyID == Pharmacy.PharmacyID)\
            .join(Barangay, Pharmacy.BarangayID == Barangay.BarangayID)\
            .join(PharmacyStatus, Pharmacy.PharmacyID == PharmacyStatus.PharmacyID)\
            .filter(Medicine.MedicineName.ilike(f"%{medicine_query}%"))\
            .filter(Medicine.InStock == True)

        query = query.filter(PharmacyStatus.IsDeactivated == False)
        
        if barangay_query:
            query = query.filter(Barangay.BarangayName.ilike(f"%{barangay_query}%"))
            
        query = query.order_by(PharmacyStatus.StrikeCount.asc()).all()

        results = []
        for med, pharm, brgy, status in query:
            results.append({
                'pharmacyId': pharm.PharmacyID,
                'pharmacyName': pharm.PharmacyName,
                'branch': brgy.BarangayName,
                'medicine': med.MedicineName,
                'price': str(med.Price),
                'address': pharm.FullAddress,
                'inStock': med.InStock,
                'strikes': getattr(status, 'StrikeCount', 0),
                'storeImage': pharm.LogoPhotoPath,
                'openTime': pharm.OpenTime,
                'closeTime': pharm.CloseTime,
                'contactNumber': pharm.ContactNumber
            })
            
            # LOG VISIBILITY FOR ANALYTICS (Appeared in Search)
            try:
                vis_log = PharmacyVisibilityLog(PharmacyID=pharm.PharmacyID, Action='Appeared', MedicineName=med.MedicineName)
                db.session.add(vis_log)
            except Exception: pass

        db.session.commit()
        return jsonify({'message': 'Search completed', 'results': results}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/log-click', methods=['POST'])
def log_click():
    data = request.json
    pharm_id = data.get('pharmacyId')
    medicine = data.get('medicine')
    if pharm_id:
        try:
            log = PharmacyVisibilityLog(PharmacyID=pharm_id, Action='Clicked', MedicineName=medicine)
            db.session.add(log)
            db.session.commit()
        except: db.session.rollback()
    return jsonify({'success': True})

# ==========================================
# PENALTY SYSTEM & REPORTING ENDPOINT
# ==========================================
@app.route('/api/report-stock', methods=['POST'])
def report_pharmacy_stock():
    data = request.json
    pharm_id = data.get('pharmacyId')
    client_id = data.get('clientId')
    is_out_of_stock = data.get('isOutOfStock', True)
    medicine_name = data.get('medicineName')
    
    try:
        new_report = PharmacyReport(PharmacyID=pharm_id, ClientID=client_id, IsOutOfStock=is_out_of_stock)
        db.session.add(new_report)
        
        status = PharmacyStatus.query.filter_by(PharmacyID=pharm_id).first()
        pharmacy = Pharmacy.query.get(pharm_id)
        
        if status and pharmacy and is_out_of_stock:
            account = PharmacyAccount.query.get(pharmacy.PharmacyAccountID)
            
            # 1. SPECIFIC MEDICINE PENALTY (5 Warning / 10 Auto-OOS)
            if medicine_name:
                medicine = Medicine.query.filter(Medicine.PharmacyID == pharm_id, Medicine.MedicineName == medicine_name).first()
                if medicine:
                    medicine.StrikeCount = getattr(medicine, 'StrikeCount', 0) + 1
                    if medicine.StrikeCount == 5:
                        subject = 'Oath of Care - Inventory Warning'
                        body = f'Warning: Your medicine "{medicine.MedicineName}" has received 5 out-of-stock reports from patients. Please update your inventory.'
                        send_async_email(account.Email, subject, body)
                    elif medicine.StrikeCount >= 10:
                        medicine.InStock = False
                        medicine.StrikeCount = 0 # Reset specific medicine strike
                        subject = 'Oath of Care - Medicine Auto-Disabled'
                        body = f'Notice: "{medicine.MedicineName}" has received 10 out-of-stock reports and was automatically marked as OUT OF STOCK to protect the reliability of the network.'
                        send_async_email(account.Email, subject, body)

            # 2. OVERALL PHARMACY PENALTY (20 Warning / 30 Deactivation)
            status.StrikeCount += 1
            status.TotalLifetimeStrikes = getattr(status, 'TotalLifetimeStrikes', 0) + 1
            
            if status.StrikeCount == 20:
                subject = 'Oath of Care - Critical Account Warning'
                body = 'CRITICAL WARNING: Your pharmacy has accumulated 20 out-of-stock reports. 10 more reports will result in temporary account deactivation.'
                send_async_email(account.Email, subject, body)
                
            elif status.StrikeCount >= 30:
                status.IsDeactivated = True
                status.StrikeCount = 0 # Will reset actively upon deactivation, so when they reactivate it's clean.
                subject = 'Oath of Care - Account Deactivated'
                body = 'Your pharmacy has been deactivated due to 30 out-of-stock reports. You must log in and manually update your inventory to restore your visibility in searches.'
                send_async_email(account.Email, subject, body)

        db.session.commit()
        return jsonify({'message': 'Report processed successfully'}), 200
    except Exception as e:
        db.session.rollback()
        print("Reporting Error:", e)
        return jsonify({'error': 'Failed to process report'}), 500


# ==========================================
# PHARMACY ANALYTICS ENDPOINT (REAL DATABASE)
# ==========================================
@app.route('/api/pharmacy/analytics/<int:pharm_id>', methods=['GET'])
def get_pharmacy_analytics(pharm_id):
    filter_date = request.args.get('filter', '30days')
    now = datetime.utcnow()
    
    if filter_date == 'today':
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif filter_date == '7days':
        start_date = now - timedelta(days=7)
    elif filter_date == '30days':
        start_date = now - timedelta(days=30)
    else:
        start_date = datetime.min

    try:
        # 1. PIE CHART: Feedback Data
        reports = PharmacyReport.query.filter(PharmacyReport.PharmacyID == pharm_id, PharmacyReport.ReportDate >= start_date).all()
        yes_count = sum(1 for r in reports if not r.IsOutOfStock)
        no_count = sum(1 for r in reports if r.IsOutOfStock)

        # 2. VISIBILITY LOGS: Most Searched & Most Clicked
        vis_logs = PharmacyVisibilityLog.query.filter(PharmacyVisibilityLog.PharmacyID == pharm_id, PharmacyVisibilityLog.CreatedAt >= start_date).all()
        
        appeared_meds = [log.MedicineName for log in vis_logs if log.Action == 'Appeared' and log.MedicineName]
        clicked_meds = [log.MedicineName for log in vis_logs if log.Action == 'Clicked' and log.MedicineName]
        
        most_searched = max(set(appeared_meds), key=appeared_meds.count) if appeared_meds else "N/A"
        most_clicked = max(set(clicked_meds), key=clicked_meds.count) if clicked_meds else "N/A"

        # 3. BAR CHART: Visibility vs Clicks over time
        appear_counts = defaultdict(int)
        click_counts = defaultdict(int)
        
        for log in vis_logs:
            date_str = log.CreatedAt.strftime('%b %d')
            if log.Action == 'Appeared': appear_counts[date_str] += 1
            elif log.Action == 'Clicked': click_counts[date_str] += 1
                
        sorted_dates = sorted(list(set(list(appear_counts.keys()) + list(click_counts.keys()))))
        sorted_dates = sorted_dates[-7:] if len(sorted_dates) > 7 else sorted_dates
        if not sorted_dates: sorted_dates = [now.strftime('%b %d')]
            
        visibility_data = [appear_counts[d] for d in sorted_dates]
        clicked_data = [click_counts[d] for d in sorted_dates]

        return jsonify({
            'mostSearched': most_searched,
            'mostClicked': most_clicked,
            'feedback': {'yes': yes_count, 'no': no_count},
            'chartLabels': sorted_dates,
            'visibilityData': visibility_data,
            'clickedData': clicked_data
        }), 200
    except Exception as e:
        print("Analytics Error:", e)
        return jsonify({'error': 'Failed to load analytics'}), 500


# ==========================================
# ADMIN ENDPOINTS & AUTO-DELETION
# ==========================================
def run_auto_deletion_check():
    try:
        # DELETE FOR 3 MONTHS (90 days) OF DEACTIVATION
        three_months_ago = datetime.utcnow() - timedelta(days=90)
        abandoned_pharmacies = PharmacyStatus.query.filter(
            PharmacyStatus.IsDeactivated == True,
            PharmacyStatus.LastStockUpdate < three_months_ago
        ).all()
        
        for status in abandoned_pharmacies:
            pharm_id = status.PharmacyID
            Medicine.query.filter_by(PharmacyID=pharm_id).delete()
            PharmacyReport.query.filter_by(PharmacyID=pharm_id).delete()
            PharmacyVisibilityLog.query.filter_by(PharmacyID=pharm_id).delete()
            db.session.delete(status)
            Pharmacy.query.filter_by(PharmacyID=pharm_id).delete()
            
        db.session.commit()
    except Exception as e:
        db.session.rollback()

# ... other admin endpoints (get_pending_pharmacies, resolve_application) remain unchanged ...

# ==========================================
# RUN SERVER & INITIALIZE DATABASE
# ==========================================
with app.app_context():
    db.create_all()
    
    # === DATABASE AUTO-PATCHER ===
    # Safely adds new columns and tables if they don't exist yet
    try:
        db.session.execute(text('ALTER TABLE pharmacy_status ADD COLUMN "StrikeCount" INTEGER DEFAULT 0;'))
        db.session.commit()
    except Exception: db.session.rollback()
        
    try:
        db.session.execute(text('ALTER TABLE pharmacy_status ADD COLUMN "TotalLifetimeStrikes" INTEGER DEFAULT 0;'))
        db.session.commit()
    except Exception: db.session.rollback()

    try:
        db.session.execute(text('ALTER TABLE medicine ADD COLUMN "StrikeCount" INTEGER DEFAULT 0;'))
        db.session.commit()
    except Exception: db.session.rollback()

    try:
        db.session.execute(text('ALTER TABLE pharmacy_status ADD COLUMN "LastStockUpdate" TIMESTAMP;'))
        db.session.commit()
    except Exception: db.session.rollback()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
