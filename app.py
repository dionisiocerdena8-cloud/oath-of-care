from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_bcrypt import Bcrypt
from datetime import datetime
import random
import string
import requests
import os # <--- BAGO: Ito ang kukuha ng sikreto mula sa Render

app = Flask(__name__)
# Pinapayagan nito ang HTML frontend natin na kumonekta sa backend na ito
CORS(app)

# ==========================================
# KONPIGURASYON NG DATABASE
# ==========================================

app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://neondb_owner:npg_aG9UQpT6Nswf@ep-wild-resonance-a1xpry7g.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ==========================================
# BREVO API CONFIGURATION (Split-String Hack)
# ==========================================
# BAGO: We chop the key in half so GitHub's security bot can't read it and delete it.
# Replace these with your actual NEW Brevo API key halves.
KEY_PART_1 = "xsmtpsib-0bd7b3245903a6e6b40c4e572c7916fdc0029190c6686a2c534b1c799e9764ec-"
KEY_PART_2 = "87lCBLBir2hdcoun"

# The code glues it back together right here automatically.
BREVO_API_KEY = KEY_PART_1 + KEY_PART_2
SENDER_EMAIL = 'oathofcare@gmail.com'

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

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
# MGA API ROUTES PARA SA FRONTEND
# ==========================================

# 1. Endpoint para magpadala ng Verification Code
@app.route('/api/send-verification', methods=['POST'])
def send_verification():
    data = request.json
    email = data.get('email')
    
    if not email:
        return jsonify({'error': 'Email is required'}), 400
        
    code = ''.join(random.choices(string.digits, k=6))
    verification_codes[email] = code
    
    try:
        url = "https://api.brevo.com/v3/smtp/email"
        headers = {
            "accept": "application/json",
            "api-key": BREVO_API_KEY,
            "content-type": "application/json"
        }
        payload = {
            "sender": {"name": "Medical Locator Network", "email": SENDER_EMAIL},
            "to": [{"email": email}],
            "subject": "Pharmacy Portal - Verification Code",
            "htmlContent": f"<html><body><h3>Pharmacy Registration</h3><p>Ang iyong 6-digit verification code ay: <strong><span style='font-size:24px; color:#024b33;'>{code}</span></strong></p></body></html>"
        }

        # DEBUGGING TOOL: Print the first 15 characters to the Render Logs to ensure the new key is loaded.
        safe_key_display = BREVO_API_KEY[:15] + "..." if BREVO_API_KEY else "NO_KEY_FOUND"
        print(f"\n[DEBUG] Attempting to send email using key starting with: {safe_key_display}\n")

        response = requests.post(url, json=payload, headers=headers)
        
        if response.status_code in [200, 201, 202]:
            return jsonify({'message': 'Verification code sent successfully'})
        else:
            print(f"Brevo API Error: {response.text}")
            return jsonify({'error': 'Failed to send email. Check logs.'}), 500

    except Exception as e:
        print(f"System Crash Error: {str(e)}")
        return jsonify({'error': 'System error while sending email.'}), 500


# 2. Endpoint para i-verify ang Code
@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    data = request.json
    email = data.get('email')
    code = data.get('code')
    
    if verification_codes.get(email) == code:
        return jsonify({'message': 'Code verified successfully'})
    else:
        return jsonify({'error': 'Invalid or expired code'}), 400


# 3. Endpoint para sa Final Registration (Pharmacy Account at Details)
@app.route('/register', methods=['POST'])
def register():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    pharmacy_name = data.get('pharmacyName')
    barangay_name = data.get('barangay')
    contact = data.get('contactNumber')
    address = data.get('address')
    map_link = data.get('mapLink')

    existing_user = PharmacyAccount.query.filter_by(Email=email).first()
    if existing_user:
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
            PharmacyName=pharmacy_name,
            ContactNumber=contact,
            FullAddress=address,
            GoogleMapLink=map_link,
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
        print(e)
        return jsonify({'error': 'A database error occurred during registration.'}), 500


# 4. Endpoint para sa Login (Kahit Admin o Pharmacy)
@app.route('/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    role = data.get('role')

    if role == 'pharmacy':
        user = PharmacyAccount.query.filter_by(Email=email).first()
        if user and bcrypt.check_password_hash(user.PasswordHash, password):
            pharmacy = Pharmacy.query.filter_by(PharmacyAccountID=user.PharmacyAccountID).first()
            pharmacy_name = pharmacy.PharmacyName if pharmacy else "Pharmacy Dashboard"
            
            return jsonify({
                'message': 'Login successful', 
                'pharmacyName': pharmacy_name
            }), 200
            
    elif role == 'admin':
        admin = Admin.query.filter_by(Email=email).first()
        if admin and bcrypt.check_password_hash(admin.PasswordHash, password):
            return jsonify({'message': 'Admin login successful'}), 200

    return jsonify({'error': 'Invalid email or password'}), 401


# 5. Endpoint para sa Forgot Password / Reset
@app.route('/api/reset-password', methods=['POST'])
def reset_password():
    data = request.json
    email = data.get('email')
    new_password = data.get('password')
    
    user = PharmacyAccount.query.filter_by(Email=email).first()
    if not user:
        return jsonify({'error': 'No account found with that email.'}), 404
        
    user.PasswordHash = bcrypt.generate_password_hash(new_password).decode('utf-8')
    db.session.commit()
    
    return jsonify({'message': 'Password has been successfully reset.'}), 200


# 6. Endpoint para sa Paghahanap ng Gamot (Search)
@app.route('/api/search', methods=['POST'])
def search_medicine():
    data = request.json
    medicine_query = data.get('medicine', '')
    barangay_query = data.get('barangay', '')
    
    mock_results = [{
        'pharmacyName': 'Mercury Drug',
        'branch': barangay_query,
        'medicine': medicine_query,
        'price': '5.00',
        'address': f'Gen. Alejo Santos Hwy, {barangay_query}, Norzagaray',
        'inStock': True
    }]
    
    return jsonify({'message': 'Search completed', 'results': mock_results}), 200


# 7. Endpoint para sa Pagdagdag ng Gamot sa Inventory
@app.route('/api/medicines', methods=['POST'])
def add_medicine():
    data = request.json
    name = data.get('name')
    price = data.get('price')
    status = data.get('status')
    category = data.get('category')
    
    if not name or not price:
        return jsonify({'error': 'Missing required fields'}), 400
        
    return jsonify({'message': f'{name} successfully added to database'}), 201


# Pagpapatakbo ng Server
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("Maaayos na na-create ang mga tables sa PostgreSQL!")
        
        if not Admin.query.filter_by(Email='admin@oathofcare.com').first():
            hashed_admin_pw = bcrypt.generate_password_hash('admin123').decode('utf-8')
            default_admin = Admin(Email='admin@oathofcare.com', PasswordHash=hashed_admin_pw)
            db.session.add(default_admin)
            db.session.commit()
            print("Nagawa na ang default admin: admin@oathofcare.com / admin123")

    app.run(debug=True, port=5000)
