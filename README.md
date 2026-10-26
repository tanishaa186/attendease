# Smart Attendance Web Portal

This project uses a Flutter web frontend and a FastAPI backend. Sign-in uses
one-time codes sent to the email address of an existing faculty/staff account.

## Configure and run the backend

From the repository root, create the backend environment and copy its sample
configuration:

```powershell
Set-Location backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Set the SMTP values in `backend/.env` for your email provider; for Gmail, use
an app password rather than your account password. Set `OTP_HASH_SECRET` to a
long random value and keep it stable across backend restarts and workers.

Run the API from the `backend` directory:

```powershell
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Email codes expire after five minutes, allow five verification attempts, and
can only be requested once per minute. The code is never returned by the API.

## Run the web app locally

From `frontend`:

```powershell
flutter pub get
flutter run -d chrome --dart-define=API_BASE_URL=http://127.0.0.1:8000
```

The browser must grant camera and location permissions when those features are
used. Browser camera and location access require HTTPS in production; localhost
is permitted for local development.

## Build for deployment

Build with the publicly reachable HTTPS API URL:

```powershell
flutter build web --release --dart-define=API_BASE_URL=https://api.example.edu
```

Deploy the contents of `frontend/build/web` to a static web host over HTTPS.
Configure the backend CORS origins to the deployed web origin before exposing
the API publicly. The API currently stores OTP challenges in the configured
SQL database so they remain available across backend workers and restarts.
