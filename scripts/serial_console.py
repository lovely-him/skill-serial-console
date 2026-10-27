#!/usr/bin/env python3
"""通过串口访问 Linux 开发板控制台: (必要时)登录 + 执行一条命令, 输出流式打印。

退出码:
  0    已回到 shell 提示符 (命令执行完毕)
  1    达到超时上限 (命令可能仍在运行)
  2    串口或配置不可用
  3    控制台要求登录, 但未提供凭据
  130  手动中断 (Ctrl+C)
"""

import argparse
import os
import re
import sys
import time
from pathlib import Path

try:
    import serial
except ImportError:
    serial = None

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07")

ENV_KEY_BY_FIELD = {
    "port": "SERIAL_PORT",
    "baud": "SERIAL_BAUD",
    "user": "SERIAL_USER",
    "password": "SERIAL_PASSWORD",
    "prompt": "SERIAL_PROMPT",
    "timeout": "SERIAL_TIMEOUT",
}
REQUIRED_FIELDS = ("port", "baud", "prompt")
DEFAULT_TIMEOUT = 120.0
DEFAULT_QUIET = 0.4
PIP_HINT = "python3 -m pip install --user pyserial"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="serial_console.py",
        description="通过串口登录开发板并执行一条命令 (输出流式打印)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "配置来源优先级: 命令行参数 > --env-file > 从当前目录向上查找的 .env\n"
            "必填项: SERIAL_PORT, SERIAL_BAUD, SERIAL_PROMPT\n"
            "示例:\n"
            '  serial_console.py "uname -a"\n'
            '  serial_console.py --port /dev/ttyUSB1 --baud 115200 --prompt "root@board:~#" "ip -br addr"\n'
            "  serial_console.py --check\n"
        ),
    )
    parser.add_argument(
        "command",
        nargs="?",
        default=None,
        help="要执行的命令 (省略则只唤醒/登录并打印当前控制台输出)",
    )
    parser.add_argument("--port", help="串口设备, 如 /dev/ttyUSB0")
    parser.add_argument("--baud", type=int, help="波特率")
    parser.add_argument("--user", help="登录用户名")
    parser.add_argument("--password", help="登录密码 (建议放在 .env 里)")
    parser.add_argument("--prompt", help="shell 提示符, 用于判断命令是否结束")
    parser.add_argument(
        "--timeout", type=float, help=f"单条命令最大等待秒数 (默认 {DEFAULT_TIMEOUT:g})"
    )
    parser.add_argument(
        "--quiet", type=float, help=f"命中提示符后再静默多少秒算结束 (默认 {DEFAULT_QUIET:g})"
    )
    parser.add_argument("--env-file", help="指定 .env 路径")
    parser.add_argument("--check", action="store_true", help="自检并打印生效配置, 不打开串口")
    return parser.parse_args(argv)


def read_env(path):
    values = {}
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        values[key] = value.strip().strip("'\"")
    return values


def find_env(start):
    for directory in [Path(start).resolve(), *Path(start).resolve().parents]:
        candidate = directory / ".env"
        if candidate.is_file():
            return candidate
        if (directory / ".git").exists():
            return None
    return None


def resolve_settings(args):
    explicit = args.env_file or os.environ.get("SERIAL_CONSOLE_ENV")
    env_path = Path(explicit).expanduser() if explicit else find_env(Path.cwd())
    values = read_env(env_path) if env_path and env_path.is_file() else {}
    settings = {field: getattr(args, field) for field in ENV_KEY_BY_FIELD}
    for field, key in ENV_KEY_BY_FIELD.items():
        if settings[field] is None and values.get(key):
            settings[field] = values[key]
    settings["timeout"] = (
        float(settings["timeout"]) if settings["timeout"] is not None else DEFAULT_TIMEOUT
    )
    settings["baud"] = int(settings["baud"]) if settings["baud"] is not None else None
    settings["quiet"] = args.quiet if args.quiet is not None else DEFAULT_QUIET
    return settings, env_path


def missing_fields(settings):
    return [ENV_KEY_BY_FIELD[field] for field in REQUIRED_FIELDS if not settings.get(field)]


def check(settings, env_path):
    print(f"python   : {sys.version.split()[0]}")
    if serial is None:
        print(f"pyserial : 未安装 -> {PIP_HINT}")
    else:
        print(f"pyserial : {serial.__version__}")
    print(f"env file : {env_path if env_path else '未找到'}")
    for field, key in ENV_KEY_BY_FIELD.items():
        value = settings.get(field)
        if field == "password":
            value = "***" if value else "-"
        print(f"{key:<16}: {value if value not in (None, '') else '-'}")
    missing = missing_fields(settings)
    print(f"必需项   : {'完整' if not missing else '缺 ' + ', '.join(missing)}")
    port = settings.get("port")
    if port:
        if not Path(port).exists():
            print(f"端口     : {port} 不存在")
        elif os.access(port, os.R_OK | os.W_OK):
            print(f"端口     : {port} 可读写")
        else:
            print(f"端口     : {port} 不可读写 (检查 dialout / plugdev 组权限)")
    if serial is not None:
        from serial.tools import list_ports

        devices = [item.device for item in list_ports.comports()]
        print(f"可见串口 : {', '.join(devices) if devices else '无'}")
    return 0


def _clean(text):
    return ANSI_RE.sub("", text).replace("\r\n", "\n").replace("\r", "\n")


def stream_until(ser, max_secs, prompt=None, stop_on=None, quiet=DEFAULT_QUIET):
    start = time.time()
    last_rx = time.time()
    buf = ""
    while time.time() - start < max_secs:
        pending = ser.in_waiting
        if pending:
            text = _clean(ser.read(pending).decode("utf-8", "replace"))
            buf += text
            last_rx = time.time()
            sys.stdout.write(text)
            sys.stdout.flush()
            if stop_on and stop_on in buf:
                return buf, True
        else:
            time.sleep(0.05)
            if prompt and buf.rstrip().endswith(prompt) and (time.time() - last_rx) > quiet:
                return buf, True
    return buf, False


def open_console(port, baud):
    ser = serial.Serial(port, baud, timeout=0.2)
    time.sleep(0.3)
    ser.reset_input_buffer()
    return ser


def login_if_needed(ser, user, password, prompt, quiet):
    ser.write(b"\r")
    out, _ = stream_until(ser, 3.0, prompt=prompt, stop_on="login:", quiet=quiet)
    if "login:" not in out.lower():
        return False
    if not user or not password:
        print(
            "[serial] 控制台要求登录, 但未提供 SERIAL_USER / SERIAL_PASSWORD",
            file=sys.stderr,
        )
        return True
    ser.write((user + "\r").encode())
    out2, _ = stream_until(ser, 3.0, stop_on="assword:", quiet=quiet)
    if "assword" in out2.lower():
        ser.write((password + "\r").encode())
    stream_until(ser, 10.0, prompt=prompt, quiet=quiet)
    return False


def run_command(ser, command, prompt, timeout, quiet):
    ser.write(command.encode() + b"\r")
    return stream_until(ser, timeout, prompt=prompt, quiet=quiet)


def run_session(settings, command):
    phase = "打开串口"
    finished = True
    try:
        try:
            ser = open_console(settings["port"], settings["baud"])
        except serial.SerialException as exc:
            print(f"[serial] 打开串口失败: {exc}", file=sys.stderr)
            return 2

        with ser:
            phase = "登录"
            if login_if_needed(
                ser, settings["user"], settings["password"], settings["prompt"], settings["quiet"]
            ):
                return 3
            ser.write(b"\r")
            stream_until(ser, 2.0, prompt=settings["prompt"], quiet=settings["quiet"])

            if command is None:
                return 0

            phase = "执行命令"
            print(f"\n=== $ {command}", flush=True)
            _, finished = run_command(
                ser, command, settings["prompt"], settings["timeout"], settings["quiet"]
            )
            ser.write(b"\r")
            stream_until(ser, 1.5, prompt=settings["prompt"], quiet=settings["quiet"])
    except KeyboardInterrupt:
        print(f"\n[serial] 已手动中断 (Ctrl+C, 阶段: {phase})", file=sys.stderr)
        if phase == "执行命令":
            print(
                "[serial] 注意: 中断的只是本地读取, 板子上的命令很可能仍在继续执行",
                file=sys.stderr,
            )
        return 130

    if not finished:
        print(
            f"\n[serial] 达到上限 {settings['timeout']:g}s, 命令可能仍在运行", file=sys.stderr
        )
        return 1
    return 0


def main(argv=None):
    args = parse_args(argv)
    settings, env_path = resolve_settings(args)
    if args.check:
        return check(settings, env_path)

    missing = missing_fields(settings)
    if missing:
        source = f"配置文件 {env_path}" if env_path else "未找到 .env, 用 --env-file 指定"
        print(f"[serial] 缺少配置: {', '.join(missing)} ({source})", file=sys.stderr)
        return 2
    if serial is None:
        print(f"[serial] 缺少 pyserial, 请执行: {PIP_HINT}", file=sys.stderr)
        return 2
    return run_session(settings, args.command)


if __name__ == "__main__":
    sys.exit(main())
