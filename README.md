# serial-console — 串口控制台工具

通过 **UART 串口**访问 Linux 开发板控制台（如 Radxa ROCK 2A / RK3528 等）：必要时自动登录，执行**一条**命令，输出流式打印；看到 shell 提示符即返回，不必等满超时。

用于板子还没网络 / 没装 SSH、或系统起不来时做排障与验证。

## 依赖

- Python 3
- `pyserial`：`python3 -m pip install --user pyserial`

脚本自己检测依赖：没有 pyserial 时打印安装命令并以退出码 2 结束，不会有 traceback。

## 配置：跟随工程的 `.env`

板级参数**不放技能仓库、不放用户主目录**，放**当前工程根目录的 `.env`**：

| 键 | 必需 | 说明 |
|---|---|---|
| `SERIAL_PORT` | 是 | 串口设备，如 `/dev/ttyUSB0` |
| `SERIAL_BAUD` | 是 | 波特率 |
| `SERIAL_PROMPT` | 是 | shell 提示符，用于判断命令是否结束 |
| `SERIAL_USER` | 否 | 控制台停在 `login:` 时的用户名 |
| `SERIAL_PASSWORD` | 否 | 控制台停在 `login:` 时的密码 |
| `SERIAL_TIMEOUT` | 否 | 单条命令等待秒数，默认 120 |

把 `examples/env.example` 复制到工程根目录并改名为 `.env` 即可（各工程已忽略 `.env`，不会入库）。

查找顺序：**命令行参数 > `--env-file`（或环境变量 `SERIAL_CONSOLE_ENV`）> 从当前目录向上查找 `.env`**（向上止于含 `.git` 的目录）。

没有任何内置的板级默认值。缺 `SERIAL_PORT` / `SERIAL_BAUD` / `SERIAL_PROMPT` 会直接报缺哪一项并退出（2），不会悄悄用一个可能不对的波特率。

## 用法

```bash
# 执行一条命令
python3 scripts/serial_console.py "uname -a"

# 临时覆盖（不写 .env）
python3 scripts/serial_console.py --port /dev/ttyUSB1 --baud 115200 \
    --prompt 'root@board:~#' "ip -br addr"

# 指定配置文件
python3 scripts/serial_console.py --env-file /path/to/other.env "df -h /"

# 不带命令：只唤醒 /（必要时）登录，并打印当前控制台输出
python3 scripts/serial_console.py

# 自检：不打开串口，只报告环境与生效配置
python3 scripts/serial_console.py --check
```

`--check` 输出示例（密码打码）：

```
python   : 3.12.3
pyserial : 3.5
env file : /path/to/project/.env
SERIAL_PORT     : /dev/ttyUSB0
SERIAL_BAUD     : 1500000
SERIAL_PROMPT   : radxa@rock-2:~$
SERIAL_USER     : radxa
SERIAL_PASSWORD : ***
SERIAL_TIMEOUT  : 120.0
必需项   : 完整
端口     : /dev/ttyUSB0 可读写
可见串口 : /dev/ttyUSB0
```

## 退出码

| 退出码 | 含义 |
|---|---|
| 0 | 命令执行完毕，已回到 shell 提示符 |
| 1 | 达到 `--timeout` 上限（命令可能仍在运行） |
| 2 | 串口或配置不可用（缺配置、缺 pyserial、打不开设备） |
| 3 | 控制台停在 `login:`，但未提供 `SERIAL_USER` / `SERIAL_PASSWORD` |
| 130 | 手动中断（Ctrl+C）；命令可能仍在板子上执行 |

## 行为

- **一次一条命令**：串口没有流控与纠错，逐条执行才能判断"是否还在运行"、输出归属哪条命令。
- **流式输出**：边收边打印（实时 flush），不是攒够时间再一次性打印。
- **提示符判定结束**：命中 `SERIAL_PROMPT` 且短暂静默即返回；否则等到 `--timeout`。匹配前先去除 ANSI 转义，带颜色的提示符同样可识别。
- **自动登录**：仅当控制台显示 `login:` 且提供了凭据时才登录。
- **不转发交互输入**：只发一条命令行，不转发 Ctrl+C 等按键。

## 注意事项

1. **端口与波特率因板而异**（部分 Rockchip 板使用远高于常见值的波特率）。没有输出时先确认这两项，再查 TX/RX 是否接反、地线是否接好。
2. **提示符必须匹配实际登录身份**：换主机名、换用户或 `su` 之后提示符会变，`SERIAL_PROMPT` 不跟着改就会每次等到超时（退出码 1）。
3. **宿主侧权限**：串口通常属于 `dialout` / `plugdev` 组，缺组且无 ACL 时打不开（退出码 2）。`--check` 会直接报"不可读写"。
4. **长命令**：`apt-get update/install`、刷写等耗时命令请放宽 `--timeout`。
5. **凭据**：`--password` 会出现在 shell history / `ps` 里，优先放到 `.env`（已被忽略）或环境变量里。
6. **过期发行版的报错**（软件源 404 等）是发行版生命周期问题，与本工具无关。

## 在宿主工程里接入

本仓库是独立真源，宿主工程只放**软链**，并把自己原来的副本从 git 跟踪中移除：

```bash
ln -s ../../../../tools/serial-console .github/skills/serial-console   # 路径按实际深度调整
```

宿主工程的 `.gitignore` 里加上这两个路径，避免软链被提交。这样 agent 通过 `.github/skills/serial-console/SKILL.md` 加载契约，人按 `tools/serial-console/README.md` 查文档，两条路径都指向同一份代码。

## 测试

```bash
python3 -m unittest discover -s tests -v
```

测试用假的串口对象，不需要接板子。

## License

MIT
