import paramiko
import logging
from socket import timeout as socket_timeout

logger = logging.getLogger("ssh_manager")


class SSHManager:
    """
    Manages a paramiko SSH connection with a persistent PTY shell channel.

    The channel is a raw bidirectional pipe:
    - Write user keystrokes TO the channel
    - Read terminal output FROM the channel

    xterm.js on the frontend handles all rendering, ANSI codes, cursor
    movement, colors, etc. We just pass raw bytes through.
    """

    def __init__(self):
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.connected = False
        self.channel = None

    def connect(self, host, port, username, password=None, key_path=None,
                cols=120, rows=30):
        """
        Connect to remote server and open a PTY shell.
        Returns (success, error_message).
        """
        try:
            if key_path:
                key = paramiko.RSAKey.from_private_key_file(key_path)
                self.client.connect(
                    host, port=port, username=username, pkey=key, timeout=10
                )
            else:
                self.client.connect(
                    host, port=port, username=username, password=password,
                    timeout=10
                )

            # Open interactive shell with PTY
            self.channel = self.client.invoke_shell(
                term="xterm-256color", width=cols, height=rows
            )
            self.channel.settimeout(0.1)
            self.connected = True
            return True, None

        except paramiko.AuthenticationException:
            return False, "Authentication failed — check username/password"
        except paramiko.SSHException as e:
            return False, f"SSH error: {e}"
        except TimeoutError:
            return False, "Connection timed out — check host IP and that SSH is enabled"
        except OSError as e:
            return False, f"Connection failed: {e}"
        except Exception as e:
            logger.exception("Connect error")
            return False, f"Unexpected error: {e}"

    def read(self):
        """
        Read available data from the shell channel.
        Returns bytes (may be empty if nothing available).
        Non-blocking — returns immediately if no data.
        """
        if not self.channel:
            return b""
        try:
            if self.channel.recv_ready():
                return self.channel.recv(4096)
        except socket_timeout:
            pass
        except Exception:
            pass
        return b""

    def write(self, data):
        """Write raw bytes to the shell channel (user keystrokes)."""
        if self.channel:
            try:
                self.channel.sendall(data)
            except Exception as e:
                logger.error(f"Write error: {e}")

    def resize(self, cols, rows):
        """Resize the PTY to match the frontend terminal size."""
        if self.channel:
            try:
                self.channel.resize_pty(width=cols, height=rows)
            except Exception as e:
                logger.debug(f"Resize error: {e}")

    def is_active(self):
        """Check if the channel is still alive."""
        if not self.channel:
            return False
        return not self.channel.closed and self.channel.get_transport() is not None

    def disconnect(self):
        """Close the shell channel and SSH connection."""
        try:
            if self.channel:
                self.channel.close()
        except Exception:
            pass
        try:
            self.client.close()
        except Exception:
            pass
        self.channel = None
        self.connected = False
