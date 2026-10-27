# Changelog

## 0.1.0

- 独立仓库：`SKILL.md` + `scripts/serial_console.py` 自成一套技能包，不再依赖宿主工程的 venv。
- 板级参数改为跟随工程 `.env`（`SERIAL_*`），移除脚本内的板级默认值（端口 / 波特率 / 账号 / 提示符）。
- 新增 `--check`：报告 python / pyserial / 解析到的 `.env` / 生效配置（密码打码）/ 端口权限 / 可见串口。
- 新增退出码 `3`：控制台要求登录但未提供凭据。
- 依赖改为惰性检测：缺 pyserial 时打印安装命令并返回 2。
