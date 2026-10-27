from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import serial_console as sc


class FakeSerial:
    def __init__(self, *chunks):
        self.chunks = [chunk.encode() if isinstance(chunk, str) else chunk for chunk in chunks]
        self.written = []

    @property
    def in_waiting(self):
        return len(self.chunks[0]) if self.chunks else 0

    def read(self, size):
        return self.chunks.pop(0)

    def write(self, data):
        self.written.append(data)


def write_env(directory, lines):
    path = Path(directory) / ".env"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


class CleanTests(unittest.TestCase):
    def test_strips_ansi_and_normalizes_newlines(self):
        self.assertEqual(sc._clean("\x1b[1;32muart:~$ \x1b[m"), "uart:~$ ")
        self.assertEqual(sc._clean("a\r\nb\rc"), "a\nb\nc")


class EnvTests(unittest.TestCase):
    def test_parses_comments_quotes_and_export(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_env(
                directory,
                [
                    "# comment",
                    "SERIAL_PORT=/dev/ttyUSB1",
                    'SERIAL_PROMPT="root@board:~#"',
                    "export SERIAL_USER='radxa'",
                    "no_separator_line",
                    "SERIAL_TIMEOUT = 30",
                ],
            )
            values = sc.read_env(path)
        self.assertEqual(values["SERIAL_PORT"], "/dev/ttyUSB1")
        self.assertEqual(values["SERIAL_PROMPT"], "root@board:~#")
        self.assertEqual(values["SERIAL_USER"], "radxa")
        self.assertEqual(values["SERIAL_TIMEOUT"], "30")

    def test_find_env_walks_up_to_repo_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".git").mkdir()
            env = write_env(root, ["SERIAL_PORT=/dev/null"])
            nested = root / "a" / "b"
            nested.mkdir(parents=True)
            self.assertEqual(sc.find_env(nested), env)

    def test_cli_overrides_env(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_env(
                directory,
                [
                    "SERIAL_PORT=/dev/ttyA",
                    "SERIAL_BAUD=115200",
                    "SERIAL_PROMPT=root@board:~#",
                ],
            )
            args = sc.parse_args(["--env-file", str(path), "--port", "/dev/ttyB"])
            settings, env_path = sc.resolve_settings(args)
        self.assertEqual(settings["port"], "/dev/ttyB")
        self.assertEqual(settings["baud"], 115200)
        self.assertEqual(settings["prompt"], "root@board:~#")
        self.assertEqual(settings["timeout"], sc.DEFAULT_TIMEOUT)
        self.assertEqual(env_path, path)

    def test_missing_fields_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_env(directory, ["SERIAL_PORT=/dev/ttyUSB0"])
            settings, _ = sc.resolve_settings(sc.parse_args(["--env-file", str(path)]))
        self.assertEqual(sc.missing_fields(settings), ["SERIAL_BAUD", "SERIAL_PROMPT"])


class StreamTests(unittest.TestCase):
    def test_returns_when_prompt_seen_after_ansi(self):
        ser = FakeSerial("\x1b[1;32mroot@board:~# \x1b[m")
        text, done = sc.stream_until(ser, 2.0, prompt="root@board:~#", quiet=0.01)
        self.assertTrue(done)
        self.assertIn("root@board:~#", text)
        self.assertNotIn("\x1b", text)

    def test_returns_on_stop_marker(self):
        ser = FakeSerial("board login: ")
        _, done = sc.stream_until(ser, 2.0, stop_on="login:", quiet=0.01)
        self.assertTrue(done)

    def test_times_out_without_prompt(self):
        ser = FakeSerial("partial output")
        _, done = sc.stream_until(ser, 0.1, prompt="$", quiet=0.01)
        self.assertFalse(done)


class LoginTests(unittest.TestCase):
    def test_already_logged_in(self):
        ser = FakeSerial("root@board:~# ")
        self.assertFalse(sc.login_if_needed(ser, None, None, "root@board:~#", 0.01))
        self.assertEqual(ser.written, [b"\r"])

    def test_requires_credentials(self):
        ser = FakeSerial("board login: ")
        self.assertTrue(sc.login_if_needed(ser, None, None, "root@board:~#", 0.01))
        self.assertEqual(ser.written, [b"\r"])

    def test_logs_in_with_credentials(self):
        ser = FakeSerial("board login: ", "Password: ", "root@board:~# ")
        done = sc.login_if_needed(ser, "radxa", "secret", "root@board:~#", 0.01)
        self.assertFalse(done)
        self.assertEqual(ser.written, [b"\r", b"radxa\r", b"secret\r"])


class MainTests(unittest.TestCase):
    def test_missing_config_exits_2(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_env(directory, ["SERIAL_PORT=/dev/ttyUSB0"])
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = sc.main(["--env-file", str(path), "uname -a"])
        self.assertEqual(code, 2)
        self.assertIn("SERIAL_BAUD", stderr.getvalue())

    def test_check_reports_and_exits_0(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_env(
                directory,
                [
                    "SERIAL_PORT=/dev/ttyNOPE",
                    "SERIAL_BAUD=1500000",
                    "SERIAL_PROMPT=radxa@rock-2:~$",
                    "SERIAL_PASSWORD=secret",
                ],
            )
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = sc.main(["--env-file", str(path), "--check"])
        output = stdout.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("***", output)
        self.assertNotIn("secret", output)
        self.assertIn("/dev/ttyNOPE", output)

    def test_check_works_without_pyserial(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_env(
                directory,
                ["SERIAL_PORT=/dev/ttyNOPE", "SERIAL_BAUD=115200", "SERIAL_PROMPT=$"],
            )
            saved = sc.serial
            sc.serial = None
            try:
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    code = sc.main(["--env-file", str(path), "--check"])
            finally:
                sc.serial = saved
        self.assertEqual(code, 0)
        self.assertIn(sc.PIP_HINT, stdout.getvalue())

    def test_missing_pyserial_exits_2(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_env(
                directory,
                ["SERIAL_PORT=/dev/ttyNOPE", "SERIAL_BAUD=115200", "SERIAL_PROMPT=$"],
            )
            saved = sc.serial
            sc.serial = None
            try:
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    code = sc.main(["--env-file", str(path), "uname -a"])
            finally:
                sc.serial = saved
        self.assertEqual(code, 2)
        self.assertIn("pyserial", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
