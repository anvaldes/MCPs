import base64
import hashlib
import json
import os
import secrets
from urllib.parse import urlencode

import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse
import google.cloud.firestore as firestore

#--------------------------------------------------

SERVICE_NAME = 'proyecto-test-mcp'
BASE_NAME = f'mcp-{SERVICE_NAME}'

#--------------------------------------------------

BASE_URL                 = os.environ["BASE_URL"]
GOOGLE_WEB_CLIENT_ID     = os.environ["GOOGLE_WEB_CLIENT_ID"]
GOOGLE_WEB_CLIENT_SECRET = os.environ["GOOGLE_WEB_CLIENT_SECRET"]
GOOGLE_AUTH_URL          = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL         = "https://oauth2.googleapis.com/token"

SCOPES = ["openid", "email"]  # Solo lo que necesitas: identificar al usuario

_db = firestore.Client(
    project="dm-agents-private",
    database=BASE_NAME
)

# ── Firestore allowlist ─────────────────────────────────────────

def _is_user_allowed(email: str) -> bool:
    doc = _db.collection("config").document(BASE_NAME).get()
    if not doc.exists:
        return False
    allowed = doc.to_dict().get("allowed", [])
    return email in allowed

# ── Firestore helpers ─────────────────────────────────────────

def _save_state(state: str, data: dict):
    _db.collection("oauth_states").document(state).set(data)

def _get_state(state: str) -> dict | None:
    doc = _db.collection("oauth_states").document(state).get()
    return doc.to_dict() if doc.exists else None

def _delete_state(state: str):
    _db.collection("oauth_states").document(state).delete()

def _save_code(code: str, data: dict):
    _db.collection("oauth_codes").document(code).set(data)

def _get_code(code: str) -> dict | None:
    doc = _db.collection("oauth_codes").document(code).get()
    return doc.to_dict() if doc.exists else None

def _delete_code(code: str):
    _db.collection("oauth_codes").document(code).delete()

def _save_session(token: str, email: str):
    _db.collection("session_tokens").document(token).set({"email": email})

# ── OAuth endpoints ───────────────────────────────────────────

async def oauth_authorization_server(request: Request):
    return JSONResponse({
        "issuer": BASE_URL,
        "authorization_endpoint": f"{BASE_URL}/authorize",
        "token_endpoint": f"{BASE_URL}/token",
        "registration_endpoint": f"{BASE_URL}/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["S256"],
        "scopes_supported": ["openid", "email"],
    })

async def register(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    return JSONResponse({
        "client_id": "claude",
        "client_secret": "",
        "redirect_uris": body.get("redirect_uris", []),
        "grant_types": ["authorization_code"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    })

async def oauth_protected_resource(request: Request):
    return JSONResponse({
        "resource": BASE_URL,
        "authorization_servers": [BASE_URL],
        "bearer_methods_supported": ["header"],
    })

async def authorize(request: Request):
    params                = dict(request.query_params)
    redirect_uri          = params.get("redirect_uri")
    state                 = params.get("state")
    code_challenge        = params.get("code_challenge")
    code_challenge_method = params.get("code_challenge_method", "S256")
    client_id             = params.get("client_id")

    if not redirect_uri or not state:
        return JSONResponse({"error": "missing parameters"}, status_code=400)

    _save_state(state, {
        "redirect_uri":          redirect_uri,
        "code_challenge":        code_challenge,
        "code_challenge_method": code_challenge_method,
        "client_id":             client_id,
    })

    google_params = {
        "client_id":     GOOGLE_WEB_CLIENT_ID,
        "redirect_uri":  f"{BASE_URL}/callback",
        "response_type": "code",
        "scope":         " ".join(SCOPES),
        "access_type":   "offline",
        "prompt":        "consent",
        "state":         state,
    }
    return RedirectResponse(f"{GOOGLE_AUTH_URL}?{urlencode(google_params)}")

async def callback(request: Request):
    params      = dict(request.query_params)
    google_code = params.get("code")
    state       = params.get("state")
    error       = params.get("error")

    if error:
        return JSONResponse({"error": error}, status_code=400)

    oauth_state = _get_state(state)
    if not oauth_state:
        return JSONResponse({"error": "invalid state"}, status_code=400)

    redirect_uri          = oauth_state["redirect_uri"]
    code_challenge        = oauth_state.get("code_challenge")
    code_challenge_method = oauth_state.get("code_challenge_method", "S256")

    async with httpx.AsyncClient() as client:
        resp = await client.post(GOOGLE_TOKEN_URL, data={
            "code":          google_code,
            "client_id":     GOOGLE_WEB_CLIENT_ID,
            "client_secret": GOOGLE_WEB_CLIENT_SECRET,
            "redirect_uri":  f"{BASE_URL}/callback",
            "grant_type":    "authorization_code",
        })

    if resp.status_code != 200:
        return JSONResponse({"error": "google token exchange failed"}, status_code=500)

    token_data = resp.json()
    id_token   = token_data.get("id_token", "")

    try:
        payload = id_token.split(".")[1]
        payload += "=" * (4 - len(payload) % 4)
        user_info = json.loads(base64.urlsafe_b64decode(payload))
        email = user_info.get("email")
    except Exception:
        return JSONResponse({"error": "could not decode id_token"}, status_code=500)

    if not email:
        return JSONResponse({"error": "could not get email"}, status_code=500)
    
    # ── Allow list check ──────────────────────────────────────

    if not _is_user_allowed(email):
        return RedirectResponse(
            f"{redirect_uri}?error=access_denied"
            f"&error_description=No+tienes+acceso+a+este+conector"
        )
    # ─────────────────────────────────────────────────────────

    our_code = secrets.token_urlsafe(32)
    _save_code(our_code, {
        "email":                 email,
        "redirect_uri":          redirect_uri,
        "code_challenge":        code_challenge,
        "code_challenge_method": code_challenge_method,
    })
    _delete_state(state)

    return RedirectResponse(f"{redirect_uri}?{urlencode({'code': our_code, 'state': state})}")

async def token(request: Request):
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        body = await request.json()
    else:
        form = await request.form()
        body = dict(form)

    grant_type    = body.get("grant_type")
    code          = body.get("code")
    code_verifier = body.get("code_verifier")

    if grant_type != "authorization_code" or not code:
        return JSONResponse({"error": "invalid_grant"}, status_code=400)

    code_data = _get_code(code)
    if not code_data:
        return JSONResponse({"error": "invalid_grant"}, status_code=400)

    # Verificación PKCE
    code_challenge = code_data.get("code_challenge")
    if code_challenge:
        if not code_verifier:
            return JSONResponse({"error": "code_verifier required"}, status_code=400)
        digest    = hashlib.sha256(code_verifier.encode()).digest()
        challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
        if challenge != code_challenge:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)

    email = code_data["email"]
    _delete_code(code)

    session_token = secrets.token_urlsafe(32)
    _save_session(session_token, email)

    return JSONResponse({
        "access_token": session_token,
        "token_type":   "bearer",
        "scope":        "openid email",
    })