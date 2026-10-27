# serial-console

Talk to a Linux board's console over **UART**: optionally log in, run **one** command, stream the output, and return as soon as the shell prompt comes back.

Useful when the board has no network yet, no SSH, or fails to boot.

## Requirements

- Python 3
- `pyserial`: `python3 -m pip install --user pyserial`

The script checks the dependency itself: if pyserial is missing it prints the install command and exits with code 2 instead of a traceback.

## Configuration: a project-scoped `.env`

Board parameters are **not** stored in this repository and **not** in the user home directory. They live in the project's own `.env`:

| Key | Required | Meaning |
|---|---|---|
| `SERIAL_PORT` | yes | Serial device, e.g. `/dev/ttyUSB0` |
| `SERIAL_BAUD` | yes | Baud rate |
| `SERIAL_PROMPT` | yes | Shell prompt used to detect command completion |
| `SERIAL_USER` | no | Login name when the console sits at `login:` |
| `SERIAL_PASSWORD` | no | Login password when the console sits at `login:` |
| `SERIAL_TIMEOUT` | no | Per-command timeout in seconds, default 120 |

Copy `examples/env.example` to the project root as `.env`.

Resolution order: **command line > `--env-file` (or `SERIAL_CONSOLE_ENV`) > nearest `.env` walking up from the current directory**, stopping at the directory that contains `.git`.

There are no built-in board defaults: a missing `SERIAL_PORT` / `SERIAL_BAUD` / `SERIAL_PROMPT` is reported as an error (exit 2) instead of silently falling back to a possibly wrong baud rate.

## Usage

```bash
python3 scripts/serial_console.py "uname -a"
python3 scripts/serial_console.py --port /dev/ttyUSB1 --baud 115200 --prompt 'root@board:~#' "ip -br addr"
python3 scripts/serial_console.py --env-file /path/to/other.env "df -h /"
python3 scripts/serial_console.py            # wake up / log in and print current console output
python3 scripts/serial_console.py --check    # report environment and resolved config, no serial access
```

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Command finished, prompt is back |
| 1 | Per-command timeout reached (the command may still be running) |
| 2 | Serial device or configuration unavailable |
| 3 | Console asked for a login but no credentials were configured |
| 130 | Interrupted locally with Ctrl+C (the board-side command may still be running) |

## Notes

1. Port and baud rate differ per board. When nothing comes back, check both first, then TX/RX wiring and ground.
2. `SERIAL_PROMPT` must match the actual logged-in identity; change of hostname or user requires updating it, otherwise every call ends in a timeout.
3. The serial device usually belongs to `dialout` / `plugdev`; without group access or an ACL it cannot be opened. `--check` reports this directly.
4. Passwords on the command line leak into shell history and `ps`; prefer `.env` or the environment.
5. Only one command per invocation, and no interactive input forwarding by design.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

Tests use a fake serial object; no hardware required.

## License

MIT
