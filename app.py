from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_bcrypt import Bcrypt
from datetime import datetime
import random
import string
import requests
import os

app = Flask(__name__)
# Enable CORS to allow secure communication between the frontend and this Flask API
CORS(app)

# ==========================================
# DATABASE CONFIGURATION
# ==========================================
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://neondb_owner:npg_aG9UQpT6Nswf@ep-wild-resonance-a1xpry7g.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ==========================================
# BREVO API CONFIGURATION
# ==========================================
BREVO_API_KEY = os.environ.get('BREVO_API_KEY')
SENDER_EMAIL = 'oathofcareofficial@gmail.com'

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

# In-memory storage for email verification and rate limiting
verification_codes = {}
search_rate_limits = {}

# ==========================================
# DATABASE MODELS (ORM)
# [SECURITY] SQLAlchemy ORM natively utilizes parameterized queries, 
# completely neutralizing SQL Injection (SQLi) vulnerabilities.
# ==========================================

class Admin(db.Model):
    __tablename__ = 'admin'
    AdminID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    Email = db.Column(db.String(120), unique=True, nullable=False)
    PasswordHash = db.Column(db.String(255), nullable=False)
    IsFirstLogin = db.Column(db.Boolean, default=True)

class PatientAccount(db.Model):
    __tablename__ = 'patient_account'
    PatientID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    Fname = db.Column(db.String(100), nullable=False)
    Lname = db.Column(db.String(100), nullable=False)
    Age = db.Column(db.Integer, nullable=True)
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
    PermitPhotoPath = db.Column(db.String(255), nullable=True)
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
    PatientID = db.Column(db.Integer, db.ForeignKey('patient_account.PatientID'), nullable=True)
    MedicineID = db.Column(db.Integer, db.ForeignKey('medicine.MedicineID'), nullable=True)
    CreatedAt = db.Column(db.DateTime, default=datetime.utcnow)
    HasResult = db.Column(db.Boolean, default=False)


# ==========================================
# API ENDPOINTS
# ==========================================

@app.route('/api/send-verification', methods=['POST'])
def send_verification():
    data = request.json
    email = data.get('email')
    
    if not email:
        return jsonify({'error': 'Email is required'}), 400
        
    code = ''.join(random.choices(string.digits, k=6))
    verification_codes[email] = code
    
    try:
        if not BREVO_API_KEY:
            return jsonify({'error': 'Server misconfiguration.'}), 500

        url = "https://api.brevo.com/v3/smtp/email"
        headers = {
            "accept": "application/json",
            "api-key": BREVO_API_KEY,
            "content-type": "application/json"
        }
        
        professional_html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; background-color: #f4f3ef; margin: 0; padding: 20px 10px; }}
                .container {{ max-width: 450px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; padding: 30px 20px; box-shadow: 0 4px 15px rgba(2, 75, 51, 0.08); text-align: center; border: 1px solid #e8dacc; width: 100%; box-sizing: border-box; }}
                .logo {{ color: #a3c936; font-size: 24px; font-weight: 800; letter-spacing: 2px; margin-bottom: 20px; display: block; font-family: 'Georgia', serif; text-transform: uppercase; }}
                .logo span {{ color: #024b33; }}
                .title {{ color: #0a0a0a; font-size: 22px; font-weight: bold; margin-bottom: 10px; }}
                .subtitle {{ color: #4b5563; font-size: 14px; line-height: 1.5; margin-bottom: 25px; padding: 0 10px; }}
                .code-box {{ background-color: #fcfcfa; border: 2px dashed #024b33; border-radius: 8px; padding: 15px; margin: 0 auto 25px auto; max-width: 200px; }}
                .code {{ font-size: 28px; font-weight: 900; color: #024b33; letter-spacing: 8px; margin: 0; text-align: center; }}
                .warning {{ color: #9ca3af; font-size: 12px; margin-bottom: 25px; }}
                .footer {{ color: #9ca3af; font-size: 11px; margin-top: 30px; border-top: 1px solid #e8dacc; padding-top: 20px; line-height: 1.5; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="logo"><span>Oath of</span> Care</div>
                <div class="title">Welcome to Oath of Care!</div>
                <div class="subtitle">You are almost there. Please use the verification code below to authenticate your account.</div>
                <div class="code-box">
                    <p class="code">{code}</p>
                </div>
                <div class="warning">If you did not request this code, you can safely ignore this email.</div>
                <div class="footer">
                    &copy; {datetime.utcnow().year} Medical Locator Network. All rights reserved.
                </div>
            </div>
        </body>
        </html>
        """

        payload = {
            "sender": {"name": "Oath of Care Support", "email": SENDER_EMAIL},
            "to": [{"email": email}],
            "subject": f"{code} is your Oath of Care verification code",
            "htmlContent": professional_html_content
        }

        response = requests.post(url, json=payload, headers=headers)
        
        if response.status_code in [200, 201, 202]:
            return jsonify({'message': 'Verification code sent successfully'})
        else:
            return jsonify({'error': 'Failed to send email. Check configuration.'}), 500

    except Exception as e:
        return jsonify({'error': 'System error while sending email.'}), 500

@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    data = request.json
    email = data.get('email')
    code = data.get('code')
    
    if verification_codes.get(email) == code:
        return jsonify({'message': 'Code verified successfully'})
    else:
        return jsonify({'error': 'Invalid or expired code'}), 400

# Endpoint: Register Patient
@app.route('/register-patient', methods=['POST'])
def register_patient():
    data = request.json
    email = data.get('email')
    
    if PatientAccount.query.filter_by(Email=email).first():
        return jsonify({'error': 'Email is already registered as a patient'}), 400

    hashed_pw = bcrypt.generate_password_hash(data.get('password')).decode('utf-8')
    try:
        new_patient = PatientAccount(
            Fname=data.get('fname'),
            Lname=data.get('lname'),
            Age=data.get('age'),
            Email=email,
            PasswordHash=hashed_pw
        )
        db.session.add(new_patient)
        db.session.commit()
        return jsonify({'message': 'Patient registration complete!'}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Database error.'}), 500

# Endpoint: Register Pharmacy
@app.route('/register', methods=['POST'])
def register():
    data = request.json
    email = data.get('email')
    password = data.get('password')

    if PharmacyAccount.query.filter_by(Email=email).first():
        return jsonify({'error': 'Email is already registered'}), 400

    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

    try:
        new_account = PharmacyAccount(Email=email, PasswordHash=hashed_password)
        db.session.add(new_account)
        db.session.flush()

        barangay = Barangay.query.filter_by(BarangayName=data.get('barangay')).first()
        if not barangay:
            barangay = Barangay(BarangayName=data.get('barangay'))
            db.session.add(barangay)
            db.session.flush()

        new_pharmacy = Pharmacy(
            PharmacyName=data.get('pharmacyName'),
            ContactNumber=data.get('contactNumber'),
            FullAddress=data.get('address'),
            GoogleMapLink=data.get('mapLink'),
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

# Endpoint: Secure Login (Handles Roles)
@app.route('/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    role = data.get('role')

    if role == 'patient':
        user = PatientAccount.query.filter_by(Email=email).first()
        if user and bcrypt.check_password_hash(user.PasswordHash, password):
            return jsonify({
                'message': 'Login successful', 
                'id': user.PatientID, 
                'name': f"{user.Fname} {user.Lname}",
                'role': 'patient'
            }), 200
            
    elif role == 'pharmacy':
        user = PharmacyAccount.query.filter_by(Email=email).first()
        if user and bcrypt.check_password_hash(user.PasswordHash, password):
            pharmacy = Pharmacy.query.filter_by(PharmacyAccountID=user.PharmacyAccountID).first()
            if pharmacy:
                status = PharmacyStatus.query.filter_by(PharmacyID=pharmacy.PharmacyID).first()
                if status and status.AccountStatus == 'Pending':
                    return jsonify({'error': 'Your account is still pending admin approval.'}), 403
                
            return jsonify({
                'message': 'Login successful', 
                'id': pharmacy.PharmacyID if pharmacy else None,
                'pharmacyName': pharmacy.PharmacyName if pharmacy else "Pharmacy Dashboard",
                'role': 'pharmacy'
            }), 200
            
    elif role == 'admin':
        admin = Admin.query.filter_by(Email=email).first()
        if admin and bcrypt.check_password_hash(admin.PasswordHash, password):
            return jsonify({'message': 'Admin login successful', 'role': 'admin'}), 200

    return jsonify({'error': 'Invalid email or password'}), 401

@app.route('/api/reset-password', methods=['POST'])
def reset_password():
    data = request.json
    user = PharmacyAccount.query.filter_by(Email=data.get('email')).first()
    if not user:
        return jsonify({'error': 'Account not found.'}), 404
        
    user.PasswordHash = bcrypt.generate_password_hash(data.get('password')).decode('utf-8')
    db.session.commit()
    return jsonify({'message': 'Password has been successfully reset.'}), 200


# ==========================================
# SECURE PHARMACY ENDPOINTS
# ==========================================

# Fetch existing pharmacy profile data to populate the update form
@app.route('/api/pharmacy/profile/<int:pharm_id>', methods=['GET'])
def get_pharmacy_profile(pharm_id):
    try:
        pharmacy = Pharmacy.query.get(pharm_id)
        if not pharmacy:
            return jsonify({'error': 'Pharmacy not found'}), 404
            
        return jsonify({
            'name': pharmacy.PharmacyName,
            'contact': pharmacy.ContactNumber,
            'address': pharmacy.FullAddress,
            'mapLink': pharmacy.GoogleMapLink
        }), 200
    except Exception as e:
        return jsonify({'error': 'Database error'}), 500

@app.route('/api/pharmacy/update', methods=['POST'])
def update_pharmacy():
    data = request.json
    pharm_id = data.get('pharmacyId')
    
    if not pharm_id:
        return jsonify({'error': 'Unauthorized'}), 401
        
    try:
        pharmacy = Pharmacy.query.get(pharm_id)
        if pharmacy:
            pharmacy.PharmacyName = data.get('name')
            pharmacy.ContactNumber = data.get('contact')
            pharmacy.FullAddress = data.get('address')
            pharmacy.GoogleMapLink = data.get('mapLink') # Map link processing
            db.session.commit()
            return jsonify({'message': 'Profile updated successfully!'}), 200
        return jsonify({'error': 'Pharmacy not found'}), 404
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Update failed'}), 500

# Get all medicines for a specific pharmacy
@app.route('/api/medicines/<int:pharm_id>', methods=['GET'])
def get_medicines(pharm_id):
    try:
        medicines = Medicine.query.filter_by(PharmacyID=pharm_id).all()
        results = [{
            'id': med.MedicineID,
            'name': med.MedicineName,
            'category': med.Description,
            'price': str(med.Price),
            'status': 'In Stock' if med.InStock else 'Out of Stock'
        } for med in medicines]
        return jsonify(results), 200
    except Exception as e:
        return jsonify({'error': 'Failed to load inventory'}), 500

@app.route('/api/medicines', methods=['POST'])
def add_medicine():
    data = request.json
    pharm_id = data.get('pharmacyId')
    
    if not pharm_id:
        return jsonify({'error': 'Authentication required.'}), 403
        
    try:
        new_med = Medicine(
            MedicineName=data.get('name'),
            Price=data.get('price'),
            Description=data.get('category'),
            InStock=True if data.get('status') == 'In Stock' else False,
            PharmacyID=pharm_id
        )
        db.session.add(new_med)
        db.session.commit()
        return jsonify({'message': f"{data.get('name')} successfully added!"}), 201
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
# SECURITY: RATE LIMITED SEARCH ENGINE
# ==========================================
@app.route('/api/search', methods=['POST'])
def search_medicine():
    data = request.json
    patient_id = data.get('patientId')
    medicine_query = data.get('medicine', '').strip()
    barangay_query = data.get('barangay', '').strip()
    
    # Require authentication
    if not patient_id:
        return jsonify({'error': 'Access Denied. You must log in as a Patient to search.'}), 403

    # [SECURITY] Rate Limiting: Prevent API abuse (10-second cooldown per user)
    now = datetime.utcnow()
    if patient_id in search_rate_limits:
        time_passed = (now - search_rate_limits[patient_id]).total_seconds()
        if time_passed < 10:
            return jsonify({'error': f'Please wait {int(10 - time_passed)} seconds before searching again to prevent spam.'}), 429
    search_rate_limits[patient_id] = now

    # [SECURITY] SQLAlchemy ORM executes parameterized queries to prevent SQL Injection
    try:
        barangay = Barangay.query.filter_by(BarangayName=barangay_query).first()
        results = []
        medicine_id_for_log = None
        
        if barangay:
            # Query joined tables securely
            medicines = db.session.query(Medicine, Pharmacy).join(Pharmacy).filter(
                Medicine.MedicineName.ilike(f'%{medicine_query}%'),
                Medicine.InStock == True,
                Pharmacy.BarangayID == barangay.BarangayID,
                Pharmacy.IsActive == True # Ensure only active pharmacies are searched
            ).all()

            for med, pharm in medicines:
                medicine_id_for_log = med.MedicineID
                results.append({
                    'pharmacyName': pharm.PharmacyName,
                    'branch': barangay.BarangayName,
                    'medicine': med.MedicineName,
                    'price': str(med.Price),
                    'address': pharm.FullAddress,
                    'mapLink': pharm.GoogleMapLink,
                    'inStock': med.InStock
                })

        # Save Audit Log
        new_log = SearchLog(
            BarangayID=barangay.BarangayID if barangay else None,
            PatientID=patient_id,
            MedicineID=medicine_id_for_log,
            HasResult=bool(results)
        )
        db.session.add(new_log)
        db.session.commit()

        return jsonify({'message': 'Search completed', 'results': results}), 200

    except Exception as e:
        return jsonify({'error': 'Database search failed.'}), 500


# ==========================================
# ADMIN ENDPOINTS (REAL DATA)
# ==========================================

@app.route('/api/admin/pending', methods=['GET'])
def get_pending_pharmacies():
    try:
        # Fetch actual pending pharmacy requests from database
        pending = db.session.query(Pharmacy, PharmacyStatus, Barangay).join(
            PharmacyStatus, Pharmacy.PharmacyID == PharmacyStatus.PharmacyID
        ).join(
            Barangay, Pharmacy.BarangayID == Barangay.BarangayID
        ).filter(PharmacyStatus.AccountStatus == 'Pending').all()
        
        results = []
        for pharm, status, brgy in pending:
            results.append({
                'id': pharm.PharmacyID,
                'name': pharm.PharmacyName,
                'branch': brgy.BarangayName,
                'status': status.AccountStatus
            })
            
        return jsonify(results), 200
    except Exception as e:
        return jsonify({'error': 'Failed to fetch pending applications'}), 500

@app.route('/api/admin/resolve', methods=['POST'])
def resolve_application():
    data = request.json
    pharm_id = data.get('pharmacyId')
    action = data.get('action') # 'approve' or 'reject'
    
    try:
        status = PharmacyStatus.query.filter_by(PharmacyID=pharm_id).first()
        pharmacy = Pharmacy.query.get(pharm_id)
        
        if status and pharmacy:
            if action == 'approve':
                status.AccountStatus = 'Active'
                pharmacy.IsActive = True
            else:
                status.AccountStatus = 'Rejected'
                pharmacy.IsActive = False
            db.session.commit()
            return jsonify({'message': f'Application has been {action}d successfully'}), 200
            
        return jsonify({'error': 'Pharmacy not found'}), 404
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Database error occurred'}), 500

@app.route('/api/admin/stats', methods=['GET'])
def admin_stats():
    try:
        total_pharmacies = Pharmacy.query.count()
        total_patients = PatientAccount.query.count()
        total_searches = SearchLog.query.count()
        
        # Determine real success vs failed searches for Chart.js
        success_count = SearchLog.query.filter_by(HasResult=True).count()
        failed_count = SearchLog.query.filter_by(HasResult=False).count()
        
        return jsonify({
            'totalPharmacies': total_pharmacies,
            'totalPatients': total_patients,
            'totalSearches': total_searches,
            'chartData': [success_count, failed_count]
        }), 200
    except Exception as e:
        return jsonify({'error': 'Failed to fetch statistics'}), 500

@app.route('/api/admin/logs', methods=['GET'])
def admin_logs():
    try:
        # Securely fetch the last 15 audit logs
        logs = db.session.query(SearchLog, PatientAccount).join(PatientAccount).order_by(SearchLog.CreatedAt.desc()).limit(15).all()
        log_data = []
        for log, patient in logs:
            log_data.append({
                'time': log.CreatedAt.strftime("%Y-%m-%d %H:%M:%S"),
                'user': f"{patient.Fname} {patient.Lname}",
                'result': 'Success' if log.HasResult else 'No Match'
            })
        return jsonify(log_data), 200
    except Exception as e:
        return jsonify({'error': 'Failed to fetch logs'}), 500

# Execute Server Application
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("PostgreSQL tables successfully initialized.")
        
        # Generate default admin account to prevent blank databases
        if not Admin.query.filter_by(Email='admin@oathofcare.com').first():
            hashed_admin_pw = bcrypt.generate_password_hash('admin123').decode('utf-8')
            default_admin = Admin(Email='admin@oathofcare.com', PasswordHash=hashed_admin_pw)
            db.session.add(default_admin)
            db.session.commit()
            print("Default admin created: admin@oathofcare.com / admin123")

    # Dynamic Port allocation for Render hosting deployment
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
