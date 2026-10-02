import sys
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send
import google.cloud.firestore as firestore
from request_context import current_user

#--------------------------------------------------

SERVICE_NAME = 'proyecto-test-mcp'
BASE_NAME = f'mcp-{SERVICE_NAME}'

#--------------------------------------------------

_PUBLIC_PATHS = {
    "/health",
    "/authorize",
    "/callback",
    "/token",
    "/register",
    "/.well-known/oauth-protected-resource",
    "/.well-known/oauth-authorization-server",
    "/.well-known/openid-configuration"
}

_db = firestore.Client(
    project="dm-agents-private",
    database=BASE_NAME
)

def log(msg: str):
    print(msg, flush=True)
    sys.stdout.flush()

def _get_email_by_session_token(token: str) -> str | None:
    doc = _db.collection("session_tokens").document(token).get()
    if doc.exists:
        return doc.to_dict().get("email")
    return None

class GoogleAuthMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        #----------------------------------------------------------------------
        path = scope.get("path")
        log(f"[PATH] Incoming: {path}")

        if path in _PUBLIC_PATHS:
            log(f"[PATH] ✅ Public: {path}")
            await self.app(scope, receive, send)
            return

        log(f"[PATH] 🔒 Protected: {path}")
        log("----------------------------------------------------------------")
        #----------------------------------------------------------------------

        headers     = dict(scope.get("headers", []))
        auth_header = headers.get(b"authorization", b"").decode()

        if auth_header.startswith("Bearer "):
            token = auth_header[len("Bearer "):]
            email = _get_email_by_session_token(token)
            if email:
                log(f"[AUTH] ✅ Conexión exitosa — Usuario: {email}")
                token_ctx = current_user.set(email)
                try:
                    await self.app(scope, receive, send)
                finally:
                    current_user.reset(token_ctx)
                return

            log("[AUTH] ❌ Token inválido o expirado.")
            # ── resource_metadata guía a Claude al flujo OAuth correcto ──
            response = JSONResponse({"error": "invalid token"}, status_code=401)
            await response(scope, receive, send)
            return

        log("[AUTH] ❌ Sin token Bearer.")
        # ── resource_metadata guía a Claude al flujo OAuth correcto ──
        response = JSONResponse(
            {"error": "unauthorized"},
            status_code=401,
            headers={
                "WWW-Authenticate": f'Bearer realm="mcp"'},
        )
        await response(scope, receive, send)