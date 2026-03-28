from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_bcrypt import Bcrypt
from datetime import datetime
from sqlalchemy import text
import random
import string
import requests
import os

app = Flask(__name__)
# Enable CORS nang mas malawak para hindi ma-block at hindi mag "Server connection failed"
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

# ==========================================
# DATABASE CONFIGURATION
# ==========================================
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://neondb_owner:npg_aG9UQpT6Nswf@ep-wild-resonance-a1xpry7g.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ==========================================
# BREVO API CONFIGURATION (SECURED)
# ==========================================
# Kukunin na lang niya ito nang patago sa Render Environment Variables!
# Wala nang hardcoded key kaya hindi ka na iba-block ni GitHub.
BREVO_API_KEY = os.environ.get('BREVO_API_KEY')

SENDER_EMAIL = 'oathofcareofficial@gmail.com'
SENDER_NAME = 'Oath of Care'

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

# In-memory storage for email verification and rate limiting
verification_codes = {}
search_rate_limits = {}

# ==========================================
# DATABASE MODELS (ORM)
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


# ==========================================
# EMAIL HELPER FUNCTIONS (BREVO)
# ==========================================
def send_email_api(to_email, subject, html_content):
    if not BREVO_API_KEY:
        return False, "BREVO API KEY is missing from Render Environment Variables! Paki-set sa Render."
        
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
        "htmlContent": html_content
    }
    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code in [200, 201, 202]:
            return True, "Email sent successfully"
            
        # Para makita mo agad kung anong problema base mismo sa sagot ni Brevo!
        return False, f"BREVO ERROR: {response.text}"
    except Exception as e:
        return False, f"System error while sending email: {str(e)}"

def get_base_email_template(title, subtitle, content_html):
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; background-color: #f4f3ef; margin: 0; padding: 30px 10px; }}
            .container {{ max-width: 500px; margin: 0 auto; background-color: #ffffff; border-radius: 16px; padding: 40px 30px; box-shadow: 0 10px 30px rgba(2, 75, 51, 0.08); text-align: center; border: 1px solid #e8dacc; width: 100%; box-sizing: border-box; }}
            .logo {{ color: #a3c936; font-size: 28px; font-weight: 800; letter-spacing: 2px; margin-bottom: 25px; display: block; font-family: 'Georgia', serif; text-transform: uppercase; }}
            .logo span {{ color: #024b33; }}
            .title {{ color: #0a0a0a; font-size: 26px; font-weight: bold; margin-bottom: 12px; }}
            .subtitle {{ color: #4b5563; font-size: 15px; line-height: 1.6; margin-bottom: 30px; padding: 0 10px; }}
            .footer {{ color: #9ca3af; font-size: 12px; margin-top: 35px; border-top: 1px solid #e8dacc; padding-top: 25px; line-height: 1.6; }}
            .btn {{ display: inline-block; padding: 14px 28px; background-color: #024b33; color: #ffffff; text-decoration: none; border-radius: 8px; font-weight: bold; letter-spacing: 1px; text-transform: uppercase; font-size: 13px; margin-top: 10px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="logo"><span>Oath of</span> Care</div>
            <div class="title">{title}</div>
            <div class="subtitle">{subtitle}</div>
            {content_html}
            <div class="footer">
                &copy; {datetime.utcnow().year} Oath of Care Medical Locator Network.<br>All rights reserved.
            </div>
        </div>
    </body>
    </html>
    """

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
    
    content = f"""
    <div style="background-color: #fcfcfa; border: 2px dashed #024b33; border-radius: 12px; padding: 20px; margin: 0 auto 30px auto; max-width: 220px;">
        <p style="font-size: 32px; font-weight: 900; color: #024b33; letter-spacing: 10px; margin: 0; text-align: center;">{code}</p>
    </div>
    <div style="color: #9ca3af; font-size: 13px; margin-bottom: 25px;">If you did not request this code, you can safely ignore this email.</div>
    """
    html_content = get_base_email_template("Verify Your Account", "You are almost there. Please use the verification code below to authenticate.", content)
    
    success, msg = send_email_api(email, f"{code} is your verification code", html_content)
    if success:
        return jsonify({'message': 'Verification code sent successfully'})
    
    # Ibabato ang totoong error mula kay Brevo pabalik sa website mo
    return jsonify({'error': msg}), 400

@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    data = request.json
    email = data.get('email')
    code = data.get('code')
    
    if verification_codes.get(email) == code:
        return jsonify({'message': 'Code verified successfully'})
    else:
        return jsonify({'error': 'Invalid or expired code'}), 400

@app.route('/register-client', methods=['POST'])
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
        
        # Send a Beautiful Welcome Email after successful registration
        welcome_content = f"""
        <p style="color: #4b5563; font-size: 15px; line-height: 1.6; margin-bottom: 25px;">Thank you for joining our network. You now have full access to our database to quickly locate the essential medicines you need across our verified pharmacy partners.</p>
        <a href="https://oath-of-care.com" class="btn">Explore Now</a>
        """
        html_mail = get_base_email_template("Welcome to Oath of Care!", f"Hello {data.get('fname')}, your account has been successfully created.", welcome_content)
        send_email_api(email, "Welcome to Oath of Care!", html_mail)

        return jsonify({'message': 'Client registration complete!'}), 201
    except Exception as e:
        print(f"Error during client registration: {e}")
        db.session.rollback()
        return jsonify({'error': f'Database error: {str(e)}'}), 500

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

        # FIXED: mapped to storePhoto and permitPhoto to avoid 500 error!
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
        print(f"Error during pharmacy registration: {e}")
        db.session.rollback()
        # Mas malinaw na error message para makita sa frontend
        return jsonify({'error': f'Database error: {str(e)}'}), 500

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    role = data.get('role')

    if role == 'client' or role == 'patient':
        user = ClientAccount.query.filter_by(Email=email).first()
        if user and bcrypt.check_password_hash(user.PasswordHash, password):
            return jsonify({
                'message': 'Login successful', 
                'id': user.ClientID, 
                'name': f"{user.Fname} {user.Lname}",
                'role': 'client'
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
        user = ClientAccount.query.filter_by(Email=data.get('email')).first()
        
    if not user:
        return jsonify({'error': 'Account not found.'}), 404
        
    user.PasswordHash = bcrypt.generate_password_hash(data.get('password')).decode('utf-8')
    db.session.commit()
    return jsonify({'message': 'Password has been successfully reset.'}), 200

# ==========================================
# SECURE PHARMACY ENDPOINTS
# ==========================================

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
    client_id = data.get('clientId') or data.get('patientId')
    medicine_query = data.get('medicine', '').strip()
    barangay_query = data.get('barangay', '').strip()
    
    if not client_id:
        return jsonify({'error': 'Access Denied. You must log in as a Client to search.'}), 403

    now = datetime.utcnow()
    if client_id in search_rate_limits:
        time_passed = (now - search_rate_limits[client_id]).total_seconds()
        if time_passed < 10:
            return jsonify({'error': f'Please wait {int(10 - time_passed)} seconds before searching again.'}), 429
    search_rate_limits[client_id] = now

    try:
        barangay = Barangay.query.filter_by(BarangayName=barangay_query).first()
        results = []
        medicine_id_for_log = None
        
        if barangay:
            medicines = db.session.query(Medicine, Pharmacy).join(Pharmacy).filter(
                Medicine.MedicineName.ilike(f'%{medicine_query}%'),
                Medicine.InStock == True,
                Pharmacy.BarangayID == barangay.BarangayID,
                Pharmacy.IsActive == True 
            ).all()

            for med, pharm in medicines:
                medicine_id_for_log = med.MedicineID
                results.append({
                    'pharmacyName': pharm.PharmacyName,
                    'branch': barangay.BarangayName,
                    'medicine': med.MedicineName,
                    'price': str(med.Price),
                    'contact': pharm.ContactNumber,
                    'address': pharm.FullAddress,
                    'mapLink': pharm.GoogleMapLink,
                    'logo': pharm.LogoPhotoPath, 
                    'inStock': med.InStock
                })

        new_log = SearchLog(
            BarangayID=barangay.BarangayID if barangay else None,
            ClientID=client_id,
            MedicineID=medicine_id_for_log,
            HasResult=bool(results)
        )
        db.session.add(new_log)
        db.session.commit()

        return jsonify({'message': 'Search completed', 'results': results}), 200

    except Exception as e:
        return jsonify({'error': 'Database search failed.'}), 500

# ==========================================
# ADMIN ENDPOINTS
# ==========================================

@app.route('/api/admin/pending', methods=['GET'])
def get_pending_pharmacies():
    try:
        pending = db.session.query(Pharmacy, PharmacyStatus, Barangay, PharmacyAccount).join(
            PharmacyStatus, Pharmacy.PharmacyID == PharmacyStatus.PharmacyID
        ).join(
            Barangay, Pharmacy.BarangayID == Barangay.BarangayID
        ).join(
            PharmacyAccount, Pharmacy.PharmacyAccountID == PharmacyAccount.PharmacyAccountID
        ).filter(PharmacyStatus.AccountStatus == 'Pending').all()
        
        results = []
        for pharm, status, brgy, account in pending:
            results.append({
                'id': pharm.PharmacyID,
                'name': pharm.PharmacyName,
                'branch': brgy.BarangayName,
                'status': status.AccountStatus,
                'email': account.Email,
                'contact': pharm.ContactNumber,
                'address': pharm.FullAddress,
                'mapLink': pharm.GoogleMapLink,
                'storePhoto': pharm.LogoPhotoPath,
                'permitPhoto': pharm.PermitPhotoPath
            })
            
        return jsonify(results), 200
    except Exception as e:
        return jsonify({'error': 'Failed to fetch pending applications'}), 500

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
        total_clients = ClientAccount.query.count()
        total_searches = SearchLog.query.count()
        
        success_count = SearchLog.query.filter_by(HasResult=True).count()
        failed_count = SearchLog.query.filter_by(HasResult=False).count()
        
        return jsonify({
            'totalPharmacies': total_pharmacies,
            'totalClients': total_clients,
            'totalSearches': total_searches,
            'chartData': [success_count, failed_count]
        }), 200
    except Exception as e:
        return jsonify({'error': 'Failed to fetch statistics'}), 500

@app.route('/api/admin/logs', methods=['GET'])
def admin_logs():
    try:
        logs = db.session.query(SearchLog, ClientAccount).join(ClientAccount).order_by(SearchLog.CreatedAt.desc()).limit(15).all()
        log_data = []
        for log, client in logs:
            log_data.append({
                'time': log.CreatedAt.strftime("%Y-%m-%d %H:%M:%S"),
                'user': f"{client.Fname} {client.Lname}",
                'result': 'Success' if log.HasResult else 'No Match'
            })
        return jsonify(log_data), 200
    except Exception as e:
        return jsonify({'error': 'Failed to fetch logs'}), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("PostgreSQL tables successfully initialized.")
        
        # AUTO-PATCH: Sisiguraduhin natin na TEXT (unlimited length) ang data type ng Base64 Photos 
        # para maiwasan ang "DataError: value too long for type character varying(255)"
        try:
            db.session.execute(text('ALTER TABLE pharmacy ADD COLUMN "LogoPhotoPath" TEXT;'))
            db.session.commit()
            print("Database Patched: Added LogoPhotoPath column successfully.")
        except Exception:
            db.session.rollback() 
            
        try:
            db.session.execute(text('ALTER TABLE pharmacy ALTER COLUMN "LogoPhotoPath" TYPE TEXT;'))
            db.session.commit()
        except Exception:
            db.session.rollback()
            
        try:
            db.session.execute(text('ALTER TABLE pharmacy ALTER COLUMN "PermitPhotoPath" TYPE TEXT;'))
            db.session.commit()
        except Exception:
            db.session.rollback()
        
        if not Admin.query.filter_by(Email='oathofcare@gmail.com').first():
            hashed_admin_pw = bcrypt.generate_password_hash('admin123').decode('utf-8')
            default_admin = Admin(Email='oathofcare@gmail.com', PasswordHash=hashed_admin_pw)
            db.session.add(default_admin)
            db.session.commit()
            print("Default admin created: oathofcare@gmail.com / admin123")

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
