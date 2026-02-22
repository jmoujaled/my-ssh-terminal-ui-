import os
import secrets
import ipaddress
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root
load_dotenv(Path(__file__).parent / ".env")


class Settings:
    """
    Centralized configuration loaded from environment variables.

    All security features are opt-in:
    - If no env vars are set, the app runs with open access (no auth, no restrictions).
    - Set SSH_TERMINAL_ADMIN_PASSWORD to enable the login page.
    - Set SSH_TERMINAL_ALLOWED_IPS to restrict access by IP.
    """

    def __init__(self):
        # --- Authentication ---
        self.admin_password: str = os.environ.get("SSH_TERMINAL_ADMIN_PASSWORD", "")

        # --- Session ---
        self.session_timeout_minutes: int = int(
            os.environ.get("SSH_TERMINAL_SESSION_TIMEOUT", "30")
        )
        # Auto-generate secret key if not provided (sessions won't persist across restarts)
        self.secret_key: str = (
            os.environ.get("SSH_TERMINAL_SECRET_KEY", "") or secrets.token_hex(32)
        )

        # --- IP Allowlist ---
        raw_ips: str = os.environ.get("SSH_TERMINAL_ALLOWED_IPS", "")
        self.allowed_ips: str = raw_ips
        self.allowed_networks = self._parse_networks(raw_ips) if raw_ips else []

    def _parse_networks(self, raw: str):
        """Parse comma-separated IPs and CIDRs into network objects."""
        networks = []
        for entry in raw.split(","):
            entry = entry.strip()
            if entry:
                try:
                    networks.append(ipaddress.ip_network(entry, strict=False))
                except ValueError:
                    pass  # Skip invalid entries
        return networks

    def is_ip_allowed(self, ip_str: str) -> bool:
        """Check if an IP address is in the allowlist. Returns True if no allowlist is set."""
        if not self.allowed_networks:
            return True
        try:
            addr = ipaddress.ip_address(ip_str)
            return any(addr in network for network in self.allowed_networks)
        except ValueError:
            return False

    @property
    def auth_enabled(self) -> bool:
        return bool(self.admin_password)


# Singleton — imported by other modules
settings = Settings()
