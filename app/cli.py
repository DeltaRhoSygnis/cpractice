"""The ``cpractice`` command line entry point.

The command is deliberately thin: the browser is the product, and this module
only starts the server, opens it, lists the shelf, and diagnoses the machine.

Import discipline: nothing here imports :mod:`app.main` at module scope. The
grading runner it eventually uses imports the Unix-only :mod:`resource`
module, so a top-level import would make ``cpractice doctor`` raise a traceback
on native Windows instead of explaining WSL2.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from collections.abc import Sequence
from pathlib import Path

import httpx

from app.config import Settings
from app.grading.probe import GradingProbe, probe_grading
from app.runtime import (
    ensure_runtime_directories,
    read_state,
    write_state,
)

#: Hosts that are safe to bind without an explicit LAN opt-in.
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

#: How long ``start`` waits for its own server before giving up on the browser.
_STARTUP_WAIT_SECONDS = 15.0

#: Shown instead of a traceback on native Windows, where the grading runner
#: cannot import its Unix-only dependencies.
WINDOWS_MESSAGE = """\
CPractice needs a Unix-like Python (the grading runner uses Unix process
controls), so it cannot run in native Windows Python.

Use WSL2:
  1. In an Administrator PowerShell:  wsl --install
  2. Open the Ubuntu shell and install what CPractice needs:
       sudo apt update && sudo apt install -y python3 python3-venv build-essential pipx
  3. Install and start CPractice inside WSL2:
       pipx install "cpractice @ git+https://github.com/DeltaRhoSygnis/cpractice.git"
       cpractice start

Then open the printed address in your Windows browser."""


def build_parser() -> argparse.ArgumentParser:
    """Create the argument parser with every subcommand."""
    parser = argparse.ArgumentParser(
        prog="cpractice",
        description="Practise C with deterministic grading. The browser is the interface.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    start = subcommands.add_parser("start", help="start the local app and open it")
    start.add_argument("--host", help="address to bind (default 127.0.0.1)")
    start.add_argument("--port", type=int, help="port to bind (default 8000)")
    start.add_argument(
        "--no-browser", action="store_true", help="do not open a browser"
    )
    start.add_argument(
        "--allow-lan",
        action="store_true",
        help="allow a non-loopback bind (no authentication, trusted networks only)",
    )

    subcommands.add_parser("doctor", help="check this machine and print exact fixes")
    subcommands.add_parser("problems", help="list the locally available problems")
    subcommands.add_parser("open", help="open the running app in a browser")
    subcommands.add_parser("version", help="print the version and data folder")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse ``argv`` and dispatch to the matching ``cmd_*`` function."""
    args = build_parser().parse_args(argv)
    handler = globals().get(f"cmd_{args.command}")
    if handler is None:  # pragma: no cover - parser guarantees a command
        print(f"unknown command: {args.command}", file=sys.stderr)
        return 2
    return int(handler(args))


def is_windows() -> bool:
    """True on native Windows Python (WSL2 reports Linux instead)."""
    return platform.system() == "Windows"


def is_termux() -> bool:
    """True inside Termux on Android."""
    return "com.termux" in os.environ.get("PREFIX", "") or bool(
        os.environ.get("TERMUX_VERSION")
    )


def compiler_remediation() -> str:
    """One exact command that installs a C compiler on this platform."""
    if is_termux():
        return "pkg install clang"
    if platform.system() == "Darwin":
        return "xcode-select --install"
    if shutil.which("apt-get") is not None:
        return "sudo apt install build-essential"
    if shutil.which("dnf") is not None:
        return "sudo dnf install gcc"
    if shutil.which("pacman") is not None:
        return "sudo pacman -S gcc"
    if shutil.which("apk") is not None:
        return "sudo apk add build-base"
    return "install gcc with your system package manager"


def server_is_cpractice(url: str) -> bool:
    """True when ``url`` answers ``/api/health`` as a CPractice server."""
    try:
        response = httpx.get(url.rstrip("/") + "/api/health", timeout=1.5)
    except httpx.HTTPError:
        return False
    if response.status_code != 200:
        return False
    try:
        return response.json().get("app") == "CPractice"
    except ValueError:
        return False


def port_is_free(host: str, port: int) -> bool:
    """True when ``host:port`` can be bound right now."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _python_ok() -> bool:
    return sys.version_info >= (3, 12)


def _check_home(settings: Settings) -> tuple[bool, str]:
    """Create the runtime directories, then prove the home is writable."""
    try:
        ensure_runtime_directories(settings)
        marker = Path(settings.home) / ".cpractice-write-test"
        marker.write_text("ok", encoding="utf-8")
        marker.unlink()
    except OSError as exc:
        return False, f"{settings.home} is not writable ({exc.strerror or exc})"
    return True, str(settings.home)


def _check_grading(settings: Settings) -> GradingProbe:
    return probe_grading(
        compiler=settings.cc_compiler,
        standard=settings.cc_standard,
        workdir=settings.workspaces_path,
        use_cache=False,
    )


def _check_port(settings: Settings) -> tuple[bool, str]:
    url = f"http://{settings.host}:{settings.port}"
    if port_is_free(settings.host, settings.port):
        return True, f"port {settings.port} is free on {settings.host}"
    if server_is_cpractice(url):
        return True, f"CPractice is already running at {url}"
    return False, (
        f"port {settings.port} on {settings.host} is held by another service; "
        "choose another with `cpractice start --port <n>`"
    )


def cmd_doctor(args: argparse.Namespace) -> int:
    """Print one line per check and exit non-zero when practice cannot work."""
    del args  # doctor takes no options
    if is_windows():
        print(WINDOWS_MESSAGE)
        return 1

    settings = Settings()
    failures = 0

    python_ok = _python_ok()
    if python_ok:
        print(f"[ok]   Python {platform.python_version()}")
    else:
        failures += 1
        print(
            f"[fail] Python {platform.python_version()} - CPractice needs "
            "Python 3.12 or newer"
        )
        print("       fix: install Python 3.12 from https://www.python.org/downloads/")

    home_ok, home_detail = _check_home(settings)
    if home_ok:
        print(f"[ok]   data folder {home_detail}")
    else:
        failures += 1
        print(f"[fail] data folder {home_detail}")
        print("       fix: set CPRACTICE_HOME to a writable directory")

    probe = _check_grading(settings)
    if probe.ready:
        print(f"[ok]   C grading ({probe.compiler}, {probe.standard})")
    else:
        failures += 1
        print(f"[fail] C grading - {probe.detail or 'compile and run failed'}")
        print(f"       fix: {compiler_remediation()}")

    port_ok, port_detail = _check_port(settings)
    if port_ok:
        print(f"[ok]   {port_detail}")
    else:
        failures += 1
        print(f"[fail] {port_detail}")

    if settings.any_ai_key_configured:
        print(
            f"[info] AI generation on ({settings.resolved_ai_provider}); "
            "grading never depends on it"
        )
    else:
        print(
            "[info] AI offline - optional; set KENARI_API_KEY in "
            f"{Path(settings.home) / '.env'} to generate new problems"
        )

    if failures:
        print(f"\n{failures} check(s) failed. Fix the [fail] lines above and rerun.")
        return 1
    print("\nEverything CPractice needs is ready. Start it with: cpractice start")
    return 0


def resolve_bind(args: argparse.Namespace, settings: Settings) -> tuple[str, int]:
    """Resolve the bind address: CLI flags, then env, then settings, then defaults."""
    host = args.host or os.environ.get("CPRACTICE_HOST") or settings.host or "127.0.0.1"
    port_value = (
        args.port
        if args.port is not None
        else os.environ.get("CPRACTICE_PORT") or settings.port or 8000
    )
    try:
        port = int(port_value)
    except (TypeError, ValueError):
        port = settings.port or 8000
    return host, port


def open_browser(url: str) -> None:
    """Open ``url`` in the user's browser, falling back on Termux."""
    if is_termux():
        termux_open = shutil.which("termux-open-url")
        if termux_open is not None:
            try:
                subprocess.run([termux_open, url], check=False)
                return
            except OSError:
                pass
    webbrowser.open(url)


def _run_server(app, host: str, port: int) -> None:
    """Serve ``app`` in this process until interrupted."""
    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="info")


def _open_when_ready(url: str) -> None:
    """Wait for the server to answer, then open it (daemon thread target)."""
    deadline = time.monotonic() + _STARTUP_WAIT_SECONDS
    while time.monotonic() < deadline:
        if server_is_cpractice(url):
            open_browser(url)
            return
        time.sleep(0.2)
    print(f"The server did not answer at {url} within {_STARTUP_WAIT_SECONDS:.0f}s.")


def _server_url(host: str, port: int) -> str:
    return f"http://{host}:{port}"


def cmd_start(args: argparse.Namespace) -> int:
    """Start the local app, reusing an instance that already answers."""
    if is_windows():
        print(WINDOWS_MESSAGE)
        return 1

    settings = Settings()
    host, port = resolve_bind(args, settings)

    if host not in LOOPBACK_HOSTS and not args.allow_lan:
        print(
            f"Refusing to bind {host}: CPractice has no authentication.\n"
            "Use --allow-lan only on a network you trust."
        )
        return 2

    url = _server_url(host, port)
    if server_is_cpractice(url):
        print(f"CPractice is already running at {url}")
        if not args.no_browser:
            open_browser(url)
        return 0

    if not port_is_free(host, port):
        print(
            f"Port {port} on {host} is held by another service.\n"
            "Choose another port with: cpractice start --port <n>"
        )
        return 1

    ensure_runtime_directories(settings)
    write_state(settings.home, host=host, port=port)

    if host not in LOOPBACK_HOSTS:
        print(
            f"CPractice will be reachable from your local network at {url}.\n"
            "There is no authentication: stop it when you are done."
        )

    from app.main import create_app

    app = create_app(settings)
    print(f"CPractice is starting at {url}  (Ctrl+C stops it)")

    if not args.no_browser:
        threading.Thread(
            target=_open_when_ready, args=(url,), daemon=True
        ).start()

    _run_server(app, host, port)
    return 0


def cmd_open(args: argparse.Namespace) -> int:
    """Open the running app, using the address recorded by ``start``."""
    del args
    if is_windows():
        print(WINDOWS_MESSAGE)
        return 1

    settings = Settings()
    state = read_state(settings.home) or {}
    host = str(state.get("host") or settings.host)
    port = int(state.get("port") or settings.port)
    url = _server_url(host, port)
    if not server_is_cpractice(url):
        print(
            f"No CPractice server is running at {url}.\n"
            "Start it with: cpractice start"
        )
        return 1
    open_browser(url)
    return 0


def cmd_problems(args: argparse.Namespace) -> int:
    """Print the locally available problems: id, title and difficulty."""
    del args
    from app.storage.problem_repository import ProblemRepository

    settings = Settings()
    ensure_runtime_directories(settings)
    problems = ProblemRepository(settings.problems_path).load_all()
    if not problems:
        print(
            f"No problems found in {settings.problems_path}.\n"
            "Start the app once (cpractice start) to seed the examples."
        )
        return 0
    for problem in problems:
        metadata = problem.metadata
        print(f"{metadata.id}  {metadata.title}  ({metadata.difficulty.value})")
    return 0


def cmd_version(args: argparse.Namespace) -> int:
    """Print the version and the data folder this installation uses."""
    del args
    settings = Settings()
    print(f"CPractice {settings.app_version}")
    print(f"home: {settings.home}")
    return 0


if __name__ == "__main__":  # pragma: no cover - console script calls main()
    raise SystemExit(main())
