from fastapi import Request, HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import socket
from typing import Optional, Dict, Any
from backend.config import settings
from backend.user_auth import verify_session_token

security = HTTPBearer(auto_error=False)

def is_local_request(client_ip: Optional[str]) -> bool:
    """Check if the requesting client is running locally on the PC."""
    if not client_ip:
        return True
    local_ips = {"127.0.0.1", "::1", "localhost", "testclient"}
    return client_ip in local_ips

def get_lan_and_tailscale_ips():
    """Discover local LAN and Tailscale IP addresses for phone connection."""
    ips = []
    try:
        # Discover primary socket IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        primary_ip = s.getsockname()[0]
        s.close()
        ips.append({"type": "LAN", "ip": primary_ip, "port": settings.PORT})
    except Exception:
        pass

    # Discover other network interface IPs
    try:
        host_name = socket.gethostname()
        for ip in socket.gethostbyname_ex(host_name)[2]:
            if not ip.startswith("127.") and ip not in [item["ip"] for item in ips]:
                ip_type = "Tailscale" if ip.startswith("100.") else "Network"
                ips.append({"type": ip_type, "ip": ip, "port": settings.PORT})
    except Exception:
        pass

    return ips

def _extract_token(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = None) -> Optional[str]:
    """Extract candidate token from Bearer header, X-Jenni-Token, or query param."""
    if credentials and credentials.credentials:
        return credentials.credentials.strip()

    auth_header = request.headers.get("Authorization", "").strip()
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    elif auth_header:
        return auth_header

    token_header = request.headers.get("X-Jenni-Token", "").strip()
    if token_header:
        return token_header

    token_param = request.query_params.get("token", "").strip()
    if token_param:
        return token_param

    return None

async def verify_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security)
) -> Dict[str, Any]:
    """
    Authenticate requests:
    - If request is from localhost and REQUIRE_AUTH_FOR_LOCAL is False, allow immediately.
    - Otherwise:
      1. Check MongoDB session via verify_session_token(token)
      2. Or check static settings.AUTH_TOKEN (for Tasker / system automation)
    """
    client_ip = request.client.host if request.client else None

    # Check if local and allowed without auth
    if is_local_request(client_ip) and not settings.REQUIRE_AUTH_FOR_LOCAL:
        return {"username": "local_user", "role": "admin"}

    token = _extract_token(request, credentials)

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Jenni AI requires a valid session token. Please log in."
        )

    # 1. Check MongoDB session token
    user = verify_session_token(token)
    if user:
        return user

    # 2. Check static AUTH_TOKEN (backward compatibility for Tasker / system automation)
    if settings.AUTH_TOKEN and token == settings.AUTH_TOKEN:
        return {"username": "mobile_device", "role": "user"}

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized: Invalid or expired session. Please log in again."
    )
