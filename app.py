import os
import random
import string
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_bcrypt import Bcrypt
from flask_mail import Mail, Message
from sqlalchemy import text

# Setup Flask to look for HTML files in the 'templates' folder
app = Flask(__name__, template_folder='templates', static_folder='static')

# ==========================================
# CORS CONFIGURATION
# ==========================================
CORS(app, resources={r"/*": {"origins": "*"}})

# ==========================================
# KONPIGURASYON NG DATABASE AT EMAIL
# ==========================================
db_url = os.environ.get('DATABASE_URL', 'postgresql://neondb_owner:npg_aG9UQpT6Nswf@ep-wild-resonance-a1xpry7g-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# FIX: IDINAGDAG ITO PARA HINDI MAMATAY ANG CONNECTION SA NEON DB (SERVERLESS POOLING FIX)
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,       # I-che-check muna kung buhay ang connection bago mag-query
    'pool_recycle': 300,         # I-re-refresh ang connection every 5 mins
    'pool_timeout': 20,          # Bibigyan ng 20 secs para makakuha ng connection
}

# Konpigurasyon para sa Gmail
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'oathofcare@gmail.com'
app.config['MAIL_PASSWORD'] = 'ixrk xezt gmtr fefm' 
app.config['MAIL_DEFAULT_SENDER'] = 'oathofcare@gmail.com'

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
mail = Mail(app)

verification_codes = {}

# ==========================================
# MGA DATABASE MODELS
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
    StrikeCount = db.Column(db.Integer, default=0)
    LastStockUpdate = db.Column(db.DateTime, default=datetime.utcnow)

class Medicine(db.Model):
    __tablename__ = 'medicine'
    MedicineID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    MedicineName = db.Column(db.String(150), nullable=False)
    Description = db.Column(db.Text, nullable=True)
    Price = db.Column(db.Numeric(10, 2), nullable=False)
    IsPrescriptionRequired = db.Column(db.Boolean, default=False)
    InStock = db.Column(db.Boolean, default=True)
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

# ==========================================
# WEB PORTAL ROUTES (PARA SA RAILWAY)
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
        msg = Message('Oath of Care - Verification Code', recipients=[email])
        msg.body = f'Your 6-digit verification code for Oath of Care is: {code}'
        mail.send(msg)
        return jsonify({'message': 'Verification code sent successfully'})
    except Exception as e:
        print("Mail Error:", e)
        return jsonify({'error': 'Failed to send email. Check credentials.'}), 500

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
        return jsonify({'error': 'Email is already registered as a client'}), 400

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
            BarangayID=barangay.BarangayID,
            PharmacyAccountID=new_account.PharmacyAccountID
        )
        db.session.add(new_pharmacy)
        db.session.flush()

        new_status = PharmacyStatus(
            PharmacyID=new_pharmacy.PharmacyID,
            AccountStatus='Pending'
        )
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
# PHARMACY INVENTORY ENDPOINTS
# ==========================================
@app.route('/api/pharmacy/profile/<int:pharm_id>', methods=['GET'])
def get_pharmacy_profile(pharm_id):
    try:
        pharmacy = Pharmacy.query.get(pharm_id)
        if not pharmacy: return jsonify({'error': 'Pharmacy not found'}), 404
        return jsonify({'name': pharmacy.PharmacyName, 'contact': pharmacy.ContactNumber, 'address': pharmacy.FullAddress, 'mapLink': pharmacy.GoogleMapLink}), 200
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
        
        # Penalty reversal logic
        status = PharmacyStatus.query.filter_by(PharmacyID=pharm_id).first()
        if status:
            status.StrikeCount = 0
            status.IsDeactivated = False
            status.LastStockUpdate = datetime.utcnow()

        db.session.commit()
        return jsonify({'message': f"{data.get('name')} successfully added and Account standing updated!"}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to add medicine.'}), 500

@app.route('/api/medicines/<int:med_id>', methods=['DELETE'])
def delete_medicine(med_id):
    try:
        med = Medicine.query.get(med_id)
        if med:
            db.session.delete(med)
            db.session.commit()
            return jsonify({'message': 'Item deleted successfully'}), 200
        return jsonify({'error': 'Item not found'}), 404
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
                'strikes': status.StrikeCount,
                'storeImage': pharm.LogoPhotoPath
            })

        return jsonify({'message': 'Search completed', 'results': results}), 200
    except Exception as e:
        # FIX: IBABATO NA NATIN YUNG ACTUAL ERROR PAPUNTA SA FRONTEND PARA MAKITA NATIN KUNG MAY MALI SA TABLE OR COLUMN
        error_msg = str(e)
        print("Search Engine Error:", error_msg)
        return jsonify({'error': f"{error_msg}"}), 500


# ==========================================
# PENALTY SYSTEM & REPORTING ENDPOINT
# ==========================================
@app.route('/api/report-stock', methods=['POST'])
def report_pharmacy_stock():
    data = request.json
    pharm_id = data.get('pharmacyId')
    client_id = data.get('clientId')
    
    try:
        new_report = PharmacyReport(PharmacyID=pharm_id, ClientID=client_id, IsOutOfStock=True)
        db.session.add(new_report)
        
        status = PharmacyStatus.query.filter_by(PharmacyID=pharm_id).first()
        pharmacy = Pharmacy.query.get(pharm_id)
        
        if status and pharmacy:
            account = PharmacyAccount.query.get(pharmacy.PharmacyAccountID)
            status.StrikeCount += 1
            
            if status.StrikeCount == 5:
                msg = Message('Oath of Care - Inventory Warning', recipients=[account.Email])
                msg.body = 'Warning: Multiple patients reported that your medicines are out of stock despite showing as available on the platform. Please update your inventory immediately to avoid deactivation.'
                mail.send(msg)
                
            elif status.StrikeCount >= 10:
                status.IsDeactivated = True
                msg = Message('Oath of Care - Account Deactivated', recipients=[account.Email])
                msg.body = 'Your pharmacy has been hidden from search results due to excessive out-of-stock reports (10 strikes). You MUST log in and update your medicine inventory to restore access.'
                mail.send(msg)

        db.session.commit()
        return jsonify({'message': 'Report submitted successfully'}), 200
    except Exception as e:
        db.session.rollback()
        print("Reporting Error:", e)
        return jsonify({'error': 'Failed to process report'}), 500


# ==========================================
# ADMIN ENDPOINTS & AUTO-DELETION
# ==========================================
def run_auto_deletion_check():
    try:
        two_months_ago = datetime.utcnow() - timedelta(days=60)
        abandoned_pharmacies = PharmacyStatus.query.filter(
            PharmacyStatus.IsDeactivated == True,
            PharmacyStatus.LastStockUpdate < two_months_ago
        ).all()
        
        for status in abandoned_pharmacies:
            pharm_id = status.PharmacyID
            Medicine.query.filter_by(PharmacyID=pharm_id).delete()
            PharmacyReport.query.filter_by(PharmacyID=pharm_id).delete()
            db.session.delete(status)
            Pharmacy.query.filter_by(PharmacyID=pharm_id).delete()
            
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print("Auto-Deletion Error:", e)

@app.route('/api/admin/pending', methods=['GET'])
def get_pending_pharmacies():
    try:
        pending_statuses = PharmacyStatus.query.filter_by(AccountStatus='Pending').all()
        results = []
        for status in pending_statuses:
            pharm = Pharmacy.query.get(status.PharmacyID)
            acc = PharmacyAccount.query.get(pharm.PharmacyAccountID)
            brgy = Barangay.query.get(pharm.BarangayID)
            if pharm and acc:
                results.append({
                    'id': pharm.PharmacyID,
                    'name': pharm.PharmacyName,
                    'email': acc.Email,
                    'contact': pharm.ContactNumber,
                    'branch': brgy.BarangayName if brgy else 'Unknown',
                    'address': pharm.FullAddress,
                    'mapLink': pharm.GoogleMapLink,
                    'storePhoto': pharm.LogoPhotoPath,
                    'permitPhoto': pharm.PermitPhotoPath
                })
        return jsonify(results), 200
    except Exception as e:
        print("Error fetching pending:", e)
        return jsonify({'error': 'Database error'}), 500

@app.route('/api/admin/resolve', methods=['POST'])
def resolve_application():
    data = request.json
    pharm_id = data.get('pharmacyId')
    action = data.get('action')
    
    try:
        status = PharmacyStatus.query.filter_by(PharmacyID=pharm_id).first()
        pharmacy = Pharmacy.query.get(pharm_id)
        
        if status and pharmacy:
            if action == 'approve':
                status.AccountStatus = 'Active'
                pharmacy.IsActive = True
            elif action == 'reject':
                status.AccountStatus = 'Rejected'
            
            db.session.commit()
            return jsonify({'message': f'Application {action}d successfully'}), 200
        return jsonify({'error': 'Pharmacy not found'}), 404
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to process'}), 500

@app.route('/api/admin/stats', methods=['GET'])
def get_admin_stats():
    run_auto_deletion_check()
    return jsonify({
        'totalPharmacies': Pharmacy.query.count() if Pharmacy.query.count() else 0,
        'totalPatients': ClientAccount.query.count() if ClientAccount.query.count() else 0,
        'totalSearches': 0,
        'chartData': [75, 25] 
    }), 200

@app.route('/api/admin/logs', methods=['GET'])
def get_admin_logs():
    return jsonify([
        {'time': '2026-03-27 10:00 AM', 'user': 'System', 'result': 'Success'},
        {'time': '2026-03-27 09:30 AM', 'user': 'John Doe', 'result': 'Failed'}
    ]), 200

# ==========================================
# RUN SERVER
# ==========================================
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("PostgreSQL tables successfully initialized.")
        
        if not Admin.query.filter_by(Email='oathofcare@gmail.com').first():
            hashed_admin_pw = bcrypt.generate_password_hash('admin123').decode('utf-8')
            default_admin = Admin(Email='oathofcare@gmail.com', PasswordHash=hashed_admin_pw)
            db.session.add(default_admin)
            db.session.commit()
            print("Default admin created: oathofcare@gmail.com / admin123")

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
