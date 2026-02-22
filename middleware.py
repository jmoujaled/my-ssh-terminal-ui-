import ipaddress

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse

from auth import verify_session


class IPAllowlistMiddleware(BaseHTTPMiddleware):
    """
    Returns 403 for any IP not in the allowed CIDR networks.
    Only active when SSH_TERMINAL_ALLOWED_IPS is set.
    """

    def __init__(self, app, allowed_networks):
        super().__init__(app)
        self.allowed_networks = allowed_networks

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host
        try:
            addr = ipaddress.ip_address(client_ip)
            if not any(addr in net for net in self.allowed_networks):
                return JSONResponse({"detail": "Forbidden"}, status_code=403)
        except ValueError:
            return JSONResponse({"detail": "Forbidden"}, status_code=403)

        return await call_next(request)


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Redirects unauthenticated HTTP requests to /login.
    Only active when SSH_TERMINAL_ADMIN_PASSWORD is set.

    Exempt paths (no auth required):
    - /login (the login page itself)
    - /api/auth/* (login/logout endpoints)
    """

    EXEMPT_PATHS = {"/login", "/api/auth/login", "/api/auth/logout"}

    def __init__(self, app, secret_key: str, max_age_seconds: int = 1800):
        super().__init__(app)
        self.secret_key = secret_key
        self.max_age_seconds = max_age_seconds

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Let exempt paths through
        if path in self.EXEMPT_PATHS:
            return await call_next(request)

        # Let login page static assets through (if any)
        if path.startswith("/static/login"):
            return await call_next(request)

        # Check session cookie
        token = request.cookies.get("ssh_terminal_session")
        if not token or not verify_session(token, self.secret_key, self.max_age_seconds):
            return self._unauthorized(request)

        return await call_next(request)

    def _unauthorized(self, request: Request):
        """API requests get 401 JSON; browser requests get redirected to /login."""
        if request.url.path.startswith("/api/") or request.url.path.startswith("/ws/"):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return RedirectResponse("/login", status_code=302)
