import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from google_auth_oauthlib.flow import Flow
from backend.app.database import get_db, settings
from backend.app.models import User, GoogleToken
from backend.app.auth.security import get_current_user
from backend.app.services.calendar_service import encrypt_token

router = APIRouter(prefix="/auth/google", tags=["Google OAuth"])

# Scopes needed for Google Calendar
SCOPES = ["https://www.googleapis.com/auth/calendar"]

def get_oauth_flow(state_param: str | None = None) -> Flow:
    flow = Flow.from_client_config(
        client_config={
            "web": {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [settings.GOOGLE_REDIRECT_URI]
            }
        },
        scopes=SCOPES,
        state=state_param
    )
    flow.redirect_uri = settings.GOOGLE_REDIRECT_URI
    return flow

@router.get("/login")
def google_login(current_user: User = Depends(get_current_user)):
    """
    Returns the Google Consent Screen URL.
    The state param encodes the user's ID for validation.
    """
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Calendar integration is not configured on this server."
        )

    flow = get_oauth_flow(state_param=str(current_user.id))
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent"
    )
    return {"url": authorization_url}

@router.get("/callback")
def google_callback(code: str, state: str, db: Session = Depends(get_db)):
    """
    Handles callback from Google. Exchanges code for tokens, encrypts, and stores them.
    Redirects back to the frontend dashboard.
    """
    try:
        user_id = int(state)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    flow = get_oauth_flow(state_param=state)
    try:
        flow.fetch_token(code=code)
    except Exception as e:
        logger_err = f"Failed to fetch Google OAuth token: {str(e)}"
        print(logger_err)
        return RedirectResponse(url="http://localhost:5173/dashboard?google_calendar=error")

    credentials = flow.credentials

    # Encrypt and store tokens in the database
    encrypted_access = encrypt_token(credentials.token)
    encrypted_refresh = encrypt_token(credentials.refresh_token) if credentials.refresh_token else None
    
    expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=credentials.expiry.timestamp() - datetime.datetime.utcnow().timestamp())

    # Check if user already has a token
    existing_token = db.query(GoogleToken).filter(GoogleToken.user_id == user_id).first()
    if existing_token:
        existing_token.access_token = encrypted_access
        if encrypted_refresh:
            existing_token.refresh_token = encrypted_refresh
        existing_token.expires_at = expires_at
    else:
        new_token = GoogleToken(
            user_id=user_id,
            access_token=encrypted_access,
            refresh_token=encrypted_refresh,
            expires_at=expires_at
        )
        db.add(new_token)

    db.commit()
    return RedirectResponse(url="http://localhost:5173/dashboard?google_calendar=success")

@router.get("/status")
def google_status(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Checks if current user has connected their Google Calendar.
    """
    token_rec = db.query(GoogleToken).filter(GoogleToken.user_id == current_user.id).first()
    return {"connected": token_rec is not None}

@router.delete("/disconnect", status_code=status.HTTP_204_NO_CONTENT)
def google_disconnect(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Disconnects the Google Calendar integration by removing stored credentials.
    """
    token_rec = db.query(GoogleToken).filter(GoogleToken.user_id == current_user.id).first()
    if token_rec:
        db.delete(token_rec)
        db.commit()
    return
