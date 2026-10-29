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
import sys
from collections.abc import Sequence
from pathlib import Path

import httpx

from app.config import Settings
from app.grading.probe import GradingProbe, probe_grading
from app.runtime import ensure_runtime_directories

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


def cmd_problems(args: argparse.Namespace) -> int:  # pragma: no cover - Task 6
    del args
    raise NotImplementedError("cpractice problems is implemented in the next task")


def cmd_open(args: argparse.Namespace) -> int:  # pragma: no cover - Task 6
    del args
    raise NotImplementedError("cpractice open is implemented in the next task")


def cmd_version(args: argparse.Namespace) -> int:  # pragma: no cover - Task 6
    del args
    raise NotImplementedError("cpractice version is implemented in the next task")


def cmd_start(args: argparse.Namespace) -> int:  # pragma: no cover - Task 6
    del args
    raise NotImplementedError("cpractice start is implemented in the next task")


if __name__ == "__main__":  # pragma: no cover - console script calls main()
    raise SystemExit(main())
