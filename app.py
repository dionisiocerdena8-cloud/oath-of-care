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
# Pinapayagan nito ang HTML frontend natin na kumonekta sa backend na ito
CORS(app)

# ==========================================
# KONPIGURASYON NG DATABASE
# ==========================================
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://neondb_owner:npg_aG9UQpT6Nswf@ep-wild-resonance-a1xpry7g.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ==========================================
# BREVO API CONFIGURATION (FINAL!)
# ==========================================
# Kukunin na niya yung API Key sa loob ng Render Environment Vault
BREVO_API_KEY = os.environ.get('BREVO_API_KEY')

# Ito yung VERIFIED sender mo sa Brevo Dashboard
SENDER_EMAIL = 'oathofcareofficial@gmail.com'

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

# 1. Endpoint para magpadala ng Verification Code (BREVO API VERSION)
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
            print("[CRITICAL ERROR] BREVO_API_KEY is missing in Render Environment!")
            return jsonify({'error': 'Server misconfiguration.'}), 500

        # Ibinalik natin kay Brevo ang URL
        url = "https://api.brevo.com/v3/smtp/email"
        
        headers = {
            "accept": "application/json",
            "api-key": BREVO_API_KEY,
            "content-type": "application/json"
        }
        
        # Professional Canva-Style Email Template
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
                <div class="subtitle">You are almost there. Please use the verification code below to authenticate your account and access the Pharmacy Portal.</div>
                
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

        # Brevo JSON payload format
        payload = {
            "sender": {"name": "Oath of Care Support", "email": SENDER_EMAIL},
            "to": [{"email": email}],
            "subject": f"{code} is your Oath of Care verification code",
            "htmlContent": professional_html_content
        }

        print(f"\n[DEBUG] Sending professional email to {email} via Brevo API...")
        response = requests.post(url, json=payload, headers=headers)
        
        if response.status_code in [200, 201, 202]:
            print(f"[SUCCESS] Email sent successfully via Brevo!\n")
            return jsonify({'message': 'Verification code sent successfully'})
        else:
            print(f"[ERROR] Brevo API failed: {response.text}")
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
        
        if not Admin.query.filter_by(Email='oathofcare@gmail.com').first():
            hashed_admin_pw = bcrypt.generate_password_hash('admin123').decode('utf-8')
            default_admin = Admin(Email='admin@oathofcare.com', PasswordHash=hashed_admin_pw)
            db.session.add(default_admin)
            db.session.commit()
            print("Nagawa na ang default admin: oathofcare@gmail.com / admin123")

    # Inayos natin ang host="0.0.0.0" para makita ni Render at hindi siya mag-"No open HTTP ports"
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
