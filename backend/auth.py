from fastapi import Request, HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import socket
from typing import Optional
from backend.config import settings

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

async def verify_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security)
) -> bool:
    """
    Authenticate requests:
    - If request is from localhost and REQUIRE_AUTH_FOR_LOCAL is False, allow immediately.
    - If request is remote (e.g. Android phone), require matching AUTH_TOKEN in header or param.
    """
    client_ip = request.client.host if request.client else None

    # Check if local and allowed without auth
    if is_local_request(client_ip) and not settings.REQUIRE_AUTH_FOR_LOCAL:
        return True

    # 1. Check Authorization: Bearer <token>
    token_candidate = None
    if credentials:
        token_candidate = credentials.credentials

    # 2. Check X-Jenni-Token header
    if not token_candidate:
        token_candidate = request.headers.get("X-Jenni-Token")

    # 3. Check query param ?token=...
    if not token_candidate:
        token_candidate = request.query_params.get("token")

    if not token_candidate or token_candidate != settings.AUTH_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Jenni AI requires a valid authentication token for remote access."
        )

    return True
