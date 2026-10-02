import os
import uvicorn
from fastmcp import FastMCP
from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import JSONResponse

from middleware_google import GoogleAuthMiddleware
from oauth_google import (
    authorize, callback, token, register,
    oauth_authorization_server, oauth_protected_resource,
)
from request_context import current_user
from tool_context import tool_context

import time
from zoneinfo import ZoneInfo
from datetime import datetime, timezone

#--------------------------------------------------

SERVICE_NAME = 'proyecto-test-mcp'

#--------------------------------------------------

mcp = FastMCP(SERVICE_NAME)

#----------------------------------------------------------------------

# 1. Tool 1
 
@mcp.tool()
async def tool_1(input: str) -> dict:
    """Entrega una transformación a tu input"""
 
    async with tool_context(SERVICE_NAME, {"input": input}) as ctx:
        ctx.result = f"Esta es la transformación a tu input: {input[::-1]}"
 
    return {"result": ctx.result}
 
# ──────────────────────────────────────────────────────────────────────────────
 
# 2. Tool 2
 
@mcp.tool()
async def tool_2(input: str) -> dict:
    """Entrega una transformación a tu input"""
 
    async with tool_context(SERVICE_NAME, {"input": input}) as ctx:
        ctx.result = f"Esta es la transformación a tu input: {input.lower()}"
 
    return {"result": ctx.result}

#----------------------------------------------------------------------

async def health(request: Request):
    return JSONResponse({"status": "ok"})

#----------------------------------------------------------------------

if __name__ == "__main__":

    port    = int(os.environ.get("PORT", "8080"))
    raw_app = mcp.streamable_http_app()

    raw_app.routes.append(Route("/health",                                 health))
    raw_app.routes.append(Route("/.well-known/oauth-authorization-server", oauth_authorization_server))
    raw_app.routes.append(Route("/.well-known/oauth-protected-resource",   oauth_protected_resource))
    raw_app.routes.append(Route("/authorize",                              authorize))
    raw_app.routes.append(Route("/callback",                               callback))
    raw_app.routes.append(Route("/token",                                  token, methods=["POST"]))
    raw_app.routes.append(Route("/register",                               register, methods=["POST"]))

    final_app = GoogleAuthMiddleware(raw_app)

    print(f"Iniciando MCP server en el puerto {port}")

    uvicorn.run(
        final_app,
        host="0.0.0.0",
        port=port,
        access_log=False,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )

    #----------------------------------------------------------------------