---
name: serial-console
description: "Use when: 需要经串口(UART)访问 Linux 开发板控制台做排障或验证 —— 板子登录、看系统/网络/服务状态、排查装包报错、确认某命令输出。触发词: 串口, UART, console, 开发板, 板子, radxa, 板子连不上, ttyUSB, 波特率, 登录板子。"
license: "MIT"
compatibility: "Requires Python 3 and pyserial (`python3 -m pip install --user pyserial`). Board parameters are read from the project's .env; the tool carries no board defaults."
---

# 串口控制台 (serial console)

## 何时使用

- 板子还没网络 / 没装 SSH，或系统起不来，只能用调试串口排障。
- 需要以**原始串口输出**为准，确认真实状态（系统信息、装包报错、服务是否运行）。

## 何时不用

- 板子 SSH 可用且登录正常 → 直接用 ssh。
- 需要交互式操作（u-boot 菜单、按 Ctrl+C 打断板子上的进程）→ 用 minicom 等终端。

## 配置契约

板级参数**不放技能仓库、不放用户主目录**，放**当前工程根目录的 `.env`**：

| 键 | 必需 | 说明 |
|---|---|---|
| `SERIAL_PORT` | 是 | 串口设备，如 `/dev/ttyUSB0` |
| `SERIAL_BAUD` | 是 | 波特率 |
| `SERIAL_PROMPT` | 是 | shell 提示符，决定"命令是否结束" |
| `SERIAL_USER` | 否 | 控制台停在 `login:` 时的用户名 |
| `SERIAL_PASSWORD` | 否 | 控制台停在 `login:` 时的密码 |
| `SERIAL_TIMEOUT` | 否 | 单条命令等待秒数，默认 120 |

优先级：命令行参数 > `--env-file`（或环境变量 `SERIAL_CONSOLE_ENV`）> 从当前目录向上查找 `.env`（止于含 `.git` 的目录）。

工具**没有**板级内置默认值：缺 `SERIAL_PORT` / `SERIAL_BAUD` / `SERIAL_PROMPT` 直接报错（退出码 2），不会退回某个可能不对的波特率。

## 执行

```bash
python3 scripts/serial_console.py "<命令>"
python3 scripts/serial_console.py --check
```

缺配置或首次连某块板子时，**先跑 `--check`**：它打印 python/pyserial 版本、解析到的 `.env`、生效配置（密码打码）、端口权限、系统可见串口列表。

## 约定

1. **一次只跑一条命令**：串口没有流控与纠错，逐条执行才能判断"是否还在运行"、输出归属哪条命令。
2. **输出是流式的**：边收边打印，看到提示符即返回；长命令（如 `apt-get`）放宽 `--timeout`。
3. **换板子先确认 `SERIAL_PORT` / `SERIAL_BAUD` / `SERIAL_PROMPT`**：提示符与登录身份、主机名绑定，换了就必须改，否则每次等到超时（退出码 1）。无输出时优先怀疑波特率与 TX/RX 接反。
4. **退出码**：`0` 完成 / `1` 超时 / `2` 串口或配置不可用 / `3` 需登录但无凭据 / `130` 手动中断。
5. **不要伪造结论**：以串口原始打印为准；报错（如软件源 404）先判断是发行版生命周期问题还是操作问题。
6. 不转发交互输入（Ctrl+C、按键），命令卡住只能等超时或另开终端。

## 完成标准

- 报告执行了什么命令、串口原始输出的关键行。
- 非 0 退出码时说明是"配置缺失 / 打不开串口 / 需要登录 / 超时"中的哪一种，并给出下一步（如 `--check` 输出、调整 `SERIAL_PROMPT`）。
