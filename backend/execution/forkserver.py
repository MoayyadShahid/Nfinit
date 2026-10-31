"""Client for the warm CAD fork server.

Importing build123d loads OpenCASCADE, which takes seconds. The fork server
(``worker.py serve``) pays that once; each job then runs in a fresh child
forked from it, with the same limits as a one-shot worker. A job that runs
past its deadline is killed, exactly like a one-shot worker.
"""

import json
import logging
import os
import select
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# A cold OpenCASCADE import on a fresh container can take far longer than a
# warm one; jobs that arrive meanwhile wait for it instead of failing.
STARTUP_TIMEOUT_SECONDS = 180
# Inspection/topology JSON is small; leave ample space for semantic metadata
# while ensuring an escaped child cannot make the API process buffer an
# unbounded line from its private job socket.
MAX_WORKER_RESPONSE_BYTES = 8 * 1024 * 1024


class ForkServerUnavailable(RuntimeError):
    """The fork server could not be started or reached."""


class ForkedJobTimeout(RuntimeError):
    pass


class ForkedJobDied(RuntimeError):
    """The child exited without sending a response."""


class ForkServer:
    def __init__(self, command: list[str], environment_for):
        self._command = command
        self._environment_for = environment_for
        self._lock = threading.Lock()
        self._process: subprocess.Popen | None = None
        self._directory: Path | None = None

    @property
    def socket_path(self) -> Path:
        assert self._directory is not None
        return self._directory / "server.sock"

    def _alive(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def ensure_started(self) -> None:
        with self._lock:
            if self._alive():
                return
            self._stop_locked()
            self._start_locked()

    def _start_locked(self) -> None:
        directory = Path(tempfile.mkdtemp(prefix="nfinit-forkserver-"))
        os.chmod(directory, 0o700)
        started = time.monotonic()
        process = subprocess.Popen(
            [*self._command, "serve", str(directory / "server.sock")],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            cwd=directory,
            env=self._environment_for(directory),
        )
        self._process, self._directory = process, directory
        ready, _, _ = select.select([process.stdout], [], [], STARTUP_TIMEOUT_SECONDS)
        line = process.stdout.readline() if ready else b""
        if line.strip() != b"ready":
            self._stop_locked()
            raise ForkServerUnavailable(
                "The CAD fork server did not start "
                f"(exit status {process.poll()})."
            )
        logger.info(
            "CAD fork server ready in %.1fs (pid %s).",
            time.monotonic() - started,
            process.pid,
        )

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()

    def _stop_locked(self) -> None:
        process, directory = self._process, self._directory
        self._process = self._directory = None
        if process is not None:
            if process.stdin:
                process.stdin.close()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            if process.stdout:
                process.stdout.close()
        if directory is not None:
            shutil.rmtree(directory, ignore_errors=True)

    def _connect(self, timeout: float) -> socket.socket:
        """Connect to the server, restarting it once if it has died."""
        for attempt in range(2):
            self.ensure_started()
            connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            connection.settimeout(timeout)
            try:
                connection.connect(str(self.socket_path))
                return connection
            except (FileNotFoundError, ConnectionRefusedError, AssertionError):
                connection.close()
                if attempt == 0:
                    logger.warning("CAD fork server is unreachable; restarting it.")
                    self.stop()
        raise ForkServerUnavailable("The CAD fork server is unreachable.")

    def run(self, request: dict, timeout: float) -> str:
        """Run one job and return the child's response line."""
        deadline = time.monotonic() + timeout
        connection = self._connect(timeout)
        pid = None
        try:
            reader = connection.makefile("rb")
            header = reader.readline()
            if not header:
                raise ForkServerUnavailable("The CAD fork server closed the job.")
            pid = int(json.loads(header)["pid"])
            connection.sendall(json.dumps(request).encode())
            connection.shutdown(socket.SHUT_WR)

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise socket.timeout
            connection.settimeout(remaining)
            response = reader.readline(MAX_WORKER_RESPONSE_BYTES + 1)
            if len(response) > MAX_WORKER_RESPONSE_BYTES or (
                response and not response.endswith(b"\n")
            ):
                if pid is not None:
                    _kill(pid)
                raise ForkedJobDied("The CAD worker response exceeded its limit.")
        except socket.timeout as error:
            if pid is not None:
                _kill(pid)
            raise ForkedJobTimeout() from error
        finally:
            connection.close()

        if not response.strip():
            raise ForkedJobDied()
        return response.decode()


def _kill(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def bootstrap_command(worker: Path, package_paths: list[str], bootstrap: str) -> list[str]:
    return [sys.executable, "-I", "-c", bootstrap, str(worker), json.dumps(package_paths)]
