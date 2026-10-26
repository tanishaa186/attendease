from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import Optional
import datetime
from email.message import EmailMessage
import hashlib
import hmac
import math
import models, schemas, database, face_service
import json
import numpy as np
import os
import secrets
import smtplib
from database import engine, get_db, SessionLocal
import uvicorn
from dotenv import load_dotenv
from sqlalchemy import func
try:
    from twilio.rest import Client
    from twilio.base.exceptions import TwilioException
except ImportError:
    Client = None
    TwilioException = None

load_dotenv()

# Twilio Configuration
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")

models.Base.metadata.create_all(bind=engine)

# Seed initial data
db_session = SessionLocal()
if db_session.query(models.Department).count() == 0:
    rollwala = models.Department(
        name="Rollwala Computer Center",
        lat=23.03594131796963,
        lng=72.54588142528459,
        radius=100.0
    )
    db_session.add(rollwala)
    db_session.commit()
db_session.close()

app = FastAPI(title="Smart Faculty Attendance API")

cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "*").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

def haversine(lat1, lon1, lat2, lon2):
    # Radius of the Earth in km
    R = 6371.0

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    distance = R * c * 1000 # Convert to meters
    return distance

@app.get("/")
def read_root():
    return {"message": "Welcome to Faculty Attendance API"}

# Auth & User Endpoints
@app.get("/check-user/{phone}")
def check_user(phone: str, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.phone == phone).first()
    if db_user:
        return {"exists": True, "user_id": db_user.id}
    return {"exists": False}

# Legacy SMS OTP storage; email challenges are persisted in the SQL database.
otp_storage = {}

EMAIL_OTP_TTL_SECONDS = 5 * 60
EMAIL_OTP_RESEND_SECONDS = 60
EMAIL_OTP_MAX_ATTEMPTS = 5

def _send_email_otp(email: str, otp: str) -> None:
    smtp_host = os.getenv("SMTP_HOST")
    smtp_from_email = os.getenv("SMTP_FROM_EMAIL")
    if not smtp_host or not smtp_from_email:
        raise HTTPException(
            status_code=503,
            detail="Email delivery is not configured. Set SMTP_HOST and SMTP_FROM_EMAIL.",
        )

    use_ssl = os.getenv("SMTP_USE_SSL", "false").lower() in ("1", "true", "yes")
    default_port = 465 if use_ssl else 587
    try:
        smtp_port = int(os.getenv("SMTP_PORT", str(default_port)))
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="SMTP_PORT must be a valid port number.") from exc

    message = EmailMessage()
    message["Subject"] = "Your Smart Attendance sign-in code"
    message["From"] = smtp_from_email
    message["To"] = email
    message.set_content(
        f"Your Smart Attendance sign-in code is {otp}. "
        f"It expires in {EMAIL_OTP_TTL_SECONDS // 60} minutes. "
        "If you did not request this code, you can ignore this email."
    )

    try:
        smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
        with smtp_class(smtp_host, smtp_port, timeout=10) as smtp:
            if not use_ssl:
                smtp.starttls()
            smtp_username = os.getenv("SMTP_USERNAME")
            smtp_password = os.getenv("SMTP_PASSWORD")
            if smtp_username and smtp_password:
                smtp.login(smtp_username, smtp_password)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise HTTPException(status_code=502, detail="Unable to deliver the sign-in email. Please try again.") from exc

def _otp_digest(email: str, otp: str) -> str:
    hash_secret = os.getenv("OTP_HASH_SECRET")
    if not hash_secret:
        raise HTTPException(status_code=503, detail="OTP_HASH_SECRET is not configured.")
    return hmac.new(
        hash_secret.encode(),
        f"{email}:{otp}".encode(),
        hashlib.sha256,
    ).hexdigest()

@app.post("/auth/email/send-otp")
def send_email_otp(request: schemas.EmailOTPRequest, db: Session = Depends(get_db)):
    email = request.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=422, detail="Enter a valid email address.")

    db_user = db.query(models.User).filter(func.lower(models.User.email) == email).first()
    if not db_user:
        return {"success": True, "message": "If an account exists, a sign-in code has been sent."}

    now = datetime.datetime.utcnow()
    challenge = db.query(models.EmailOTPChallenge).filter(
        models.EmailOTPChallenge.email == email
    ).first()
    if challenge and (now - challenge.sent_at).total_seconds() < EMAIL_OTP_RESEND_SECONDS:
        raise HTTPException(status_code=429, detail="Please wait before requesting another code.")

    otp = f"{secrets.randbelow(1_000_000):06d}"
    otp_digest = _otp_digest(email, otp)
    _send_email_otp(email, otp)
    if challenge is None:
        challenge = models.EmailOTPChallenge(email=email)
        db.add(challenge)
    challenge.code_hash = otp_digest
    challenge.expires_at = now + datetime.timedelta(seconds=EMAIL_OTP_TTL_SECONDS)
    challenge.sent_at = now
    challenge.attempts = 0
    db.commit()

    return {"success": True, "message": "If an account exists, a sign-in code has been sent."}

@app.post("/auth/email/verify-otp")
def verify_email_otp(request: schemas.EmailOTPVerifyRequest, db: Session = Depends(get_db)):
    email = request.email.strip().lower()
    challenge = db.query(models.EmailOTPChallenge).filter(
        models.EmailOTPChallenge.email == email
    ).first()
    if challenge is None:
        raise HTTPException(status_code=401, detail="Invalid or expired sign-in code.")
    now = datetime.datetime.utcnow()
    if now >= challenge.expires_at:
        db.delete(challenge)
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid or expired sign-in code.")
    challenge.attempts += 1
    otp_digest = _otp_digest(email, request.otp)
    if challenge.attempts > EMAIL_OTP_MAX_ATTEMPTS:
        db.delete(challenge)
        db.commit()
        raise HTTPException(status_code=401, detail="Too many attempts. Request a new sign-in code.")
    if not hmac.compare_digest(challenge.code_hash, otp_digest):
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid or expired sign-in code.")

    db_user = db.query(models.User).filter(func.lower(models.User.email) == email).first()
    if not db_user:
        db.delete(challenge)
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid or expired sign-in code.")

    db.delete(challenge)
    db.commit()
    return {
        "success": True,
        "user_id": db_user.id,
        "needs_face_setup": not bool(db_user.face_embedding),
        "name": db_user.name,
        "email": db_user.email,
    }

@app.post("/send-otp/{phone}")
def send_otp(phone: str, method: str = "sms", db: Session = Depends(get_db)):
    # Check if user exists
    db_user = db.query(models.User).filter(models.User.phone == phone).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Account not found")

    if method not in ("sms", "whatsapp"):
        raise HTTPException(status_code=422, detail="Method must be sms or whatsapp.")

    if not Client or not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        raise HTTPException(status_code=503, detail="SMS delivery is not configured.")

    formatted_phone = phone if phone.startswith("+") else f"+91{phone}"
    sender = TWILIO_WHATSAPP_NUMBER if method == "whatsapp" else TWILIO_PHONE_NUMBER
    if not sender:
        raise HTTPException(status_code=503, detail=f"{method.upper()} delivery is not configured.")

    otp = f"{secrets.randbelow(1_000_000):06d}"
    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    try:
        client.messages.create(
            from_=f"whatsapp:{sender}" if method == "whatsapp" else sender,
            body=f"Your Smart Attendance verification code is: {otp}",
            to=f"whatsapp:{formatted_phone}" if method == "whatsapp" else formatted_phone,
        )
    except TwilioException as exc:
        raise HTTPException(status_code=502, detail="Unable to deliver the verification code.") from exc

    otp_storage[phone] = {
        "digest": hashlib.sha256(f"{phone}:{otp}".encode()).hexdigest(),
        "expires_at": datetime.datetime.utcnow() + datetime.timedelta(seconds=EMAIL_OTP_TTL_SECONDS),
    }
    return {"success": True, "message": f"OTP sent successfully via {method}."}

@app.post("/verify-otp")
def verify_otp(request: schemas.OTPVerifyRequest, db: Session = Depends(get_db)):
    stored_otp = otp_storage.get(request.phone)
    request_digest = hashlib.sha256(f"{request.phone}:{request.otp}".encode()).hexdigest()
    if (
        stored_otp
        and datetime.datetime.utcnow() < stored_otp["expires_at"]
        and hmac.compare_digest(stored_otp["digest"], request_digest)
    ):
        del otp_storage[request.phone]

        db_user = db.query(models.User).filter(models.User.phone == request.phone).first()
        if not db_user:
            raise HTTPException(status_code=401, detail="Invalid OTP")
        # If user has no face embedding stored, it's their first time face setup
        needs_face_setup = db_user.face_embedding is None or db_user.face_embedding == ""
        return {
            "success": True,
            "user_id": db_user.id,
            "needs_face_setup": needs_face_setup,
            "name": db_user.name
        }

    if stored_otp and datetime.datetime.utcnow() >= stored_otp["expires_at"]:
        del otp_storage[request.phone]
    raise HTTPException(status_code=401, detail="Invalid OTP")

@app.post("/register-face-only")
def register_face_only(request: schemas.PunchInRequest, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.id == request.user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    embedding = face_service.get_face_embedding(request.face_image_base64)
    if embedding is not None:
        db_user.face_embedding = json.dumps(embedding.tolist())
        db.commit()
        return {"status": "success", "message": "Face profile registered successfully for existing faculty!"}

    raise HTTPException(status_code=400, detail="Could not process face image embedding")

@app.post("/register", response_model=schemas.UserResponse)
def register_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    # Check if user exists
    db_user = db.query(models.User).filter(models.User.faculty_id == user.faculty_id).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Faculty ID already registered")

    embedding_json = None
    if user.face_image:
        embedding = face_service.get_face_embedding(user.face_image)
        if embedding is not None:
            embedding_json = json.dumps(embedding.tolist())

    # Create user data excluding face_image for the model
    user_data = user.dict()
    user_data.pop('face_image', None)

    db_user = models.User(**user_data, face_embedding=embedding_json)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

# Attendance Endpoints
@app.post("/attendance/punch-in")
def punch_in(punch: schemas.PunchInRequest, db: Session = Depends(get_db)):
    # 1. Fetch User
    db_user = db.query(models.User).filter(models.User.id == punch.user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    # 2. Verify Face Embedding
    if not db_user.face_embedding:
         raise HTTPException(status_code=400, detail="Face not registered for this user")

    stored_embedding = np.array(json.loads(db_user.face_embedding))
    current_embedding = face_service.get_face_embedding(punch.face_image_base64)

    if current_embedding is None:
        raise HTTPException(status_code=400, detail="No face detected in photo")

    is_verified = face_service.verify_faces(stored_embedding, current_embedding)

    if not is_verified:
        raise HTTPException(status_code=401, detail="Face verification failed")

    # 3. Verify GPS Location (Geofencing)
    # Fetch department coordinates
    dept = db.query(models.Department).filter(models.Department.id == db_user.department_id).first()
    if dept:
        # Calculate precise distance using Haversine formula
        dist_meters = haversine(dept.lat, dept.lng, punch.lat, punch.lng)

        # Check if user is within the allowed radius
        if dist_meters > dept.radius:
            raise HTTPException(
                status_code=403,
                detail=f"You are outside the department geofence ({int(dist_meters)}m away)"
            )

    # 4. Save Attendance
    new_attendance = models.Attendance(
        user_id=punch.user_id,
        punch_in=datetime.datetime.now(),
        status="Present"
    )
    db.add(new_attendance)
    db.commit()

    return {"status": "success", "message": f"Punched in at {datetime.datetime.now().strftime('%H:%M %p')}"}

@app.post("/attendance/break")
def toggle_break(user_id: int, db: Session = Depends(get_db)):
    return {"status": "success", "message": "Break status updated"}

# HOD / Admin Endpoints
@app.get("/hod/dashboard-summary")
def get_hod_summary(db: Session = Depends(get_db)):
    # Logic to count present, on break, absent
    return {
        "present": 18,
        "on_break": 2,
        "absent": 3,
        "staff_list": [
            {"name": "Dr. Patel", "status": "WORKING", "time": "09:02 AM"},
            {"name": "Prof. Shah", "status": "WORKING", "time": "08:55 AM"},
            {"name": "Prof. Mehta", "status": "ON BREAK", "time": "01:05 PM"},
            {"name": "Prof. Kumar", "status": "ABSENT", "time": "--"},
        ]
    }

@app.get("/hod/faculty-details/{faculty_id}")
def get_faculty_details(faculty_id: str, db: Session = Depends(get_db)):
    return {
        "name": "Dr. Patel",
        "punch_in": "09:02 AM",
        "punch_out": "05:58 PM",
        "total_work": "7h 59m",
        "total_break": "47m",
        "breaks": [
            {"in": "11:15 AM", "out": "11:25 AM"},
            {"in": "01:05 PM", "out": "01:42 PM"}
        ]
    }

# Leave Management
@app.post("/leave/apply")
def apply_leave(leave: schemas.LeaveRequestCreate, db: Session = Depends(get_db)):
    db_leave = models.LeaveRequest(**leave.dict())
    db.add(db_leave)
    db.commit()
    db.refresh(db_leave)
    return db_leave

@app.get("/leave/status/{user_id}")
def get_leave_status(user_id: int, db: Session = Depends(get_db)):
    return db.query(models.LeaveRequest).filter(models.LeaveRequest.user_id == user_id).all()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
