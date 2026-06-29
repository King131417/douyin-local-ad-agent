#!/usr/bin/env python3
"""Daemon launcher for Flask dashboard.
Starts the dashboard server as a detached daemon process.
"""
import os
import sys
import signal
import atexit

PROJECT_DIR = "/Users/selfgrowing/WorkBuddy/2026-06-22-23-51-30/douyin-local-ad-agent"
PID_FILE = "/tmp/dashboard_daemon.pid"

def daemonize():
    """Double-fork to daemonize the process."""
    # First fork
    try:
        pid = os.fork()
        if pid > 0:
            # Parent exits
            sys.exit(0)
    except OSError as e:
        sys.stderr.write(f"First fork failed: {e}\n")
        sys.exit(1)

    # Decouple from parent environment
    os.chdir(PROJECT_DIR)
    os.setsid()
    os.umask(0)

    # Second fork
    try:
        pid = os.fork()
        if pid > 0:
            # Parent exits
            sys.exit(0)
    except OSError as e:
        sys.stderr.write(f"Second fork failed: {e}\n")
        sys.exit(1)

    # Redirect standard file descriptors
    sys.stdout.flush()
    sys.stderr.flush()
    with open("/dev/null", "r") as devnull:
        os.dup2(devnull.fileno(), sys.stdin.fileno())
    with open("/tmp/dashboard.log", "a") as f:
        os.dup2(f.fileno(), sys.stdout.fileno())
        os.dup2(f.fileno(), sys.stderr.fileno())

    # Write PID file
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    # Register cleanup
    atexit.register(lambda: os.remove(PID_FILE) if os.path.exists(PID_FILE) else None)
    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))


if __name__ == "__main__":
    daemonize()

    # Now in daemon process - start Flask + scheduler
    sys.path.insert(0, PROJECT_DIR)

    # Load .env so API keys are available
    from pathlib import Path
    import os as _os
    env_path = Path(PROJECT_DIR) / ".env"
    if env_path.exists():
        for _line in env_path.read_text().splitlines():
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _k, _, _v = _line.partition("=")
            _os.environ.setdefault(_k.strip(), _v.strip().strip("'\""))

    from src.web.app import start_dashboard
    start_dashboard(port=8888, debug=False)
