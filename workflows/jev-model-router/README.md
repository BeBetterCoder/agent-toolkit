# Jev Model Router

Jev Model Router 为 Codex CLI 提供按任务动态选择模型的能力。每当用户开始一个新任务，路由器会让 Jev 判断所需的推理强度（`FAST`、`BALANCED` 或 `DEEP`），再根据本地配置选择 Codex 模型和 reasoning effort。

路由发生在 Codex App Server 的 `turn/start` 之前。Jev 只判断推理等级；任务执行、工具调用、审批和会话历史仍由 Codex 处理。当前提供终端版 Codex 的 `jev-codex` 启动器，以及供自定义 App Server 客户端使用的 JSONL 代理。

## 前置条件

- macOS（已验证）。实现依赖 Unix socket；Linux 和 WSL2 尚未验证，Windows 原生环境目前不支持。
- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- 已安装并登录的 Codex CLI
- TypeSafe API key（环境变量 `TYPESAFE_API_KEY`）

## 快速开始

在 `agent-toolkit` 仓库中安装依赖，并从示例创建本地配置：

```bash
cd workflows/jev-model-router
uv sync --dev
cp config.example.toml config.toml
```

编辑 `config.toml`，将 `mode` 设为 `route`，并把三个等级映射到你可使用的模型。通过环境变量提供 TypeSafe API key：

```bash
export TYPESAFE_API_KEY="你的密钥"
```

进入需要使用 Codex 的项目目录，启动终端版 Codex：

```bash
cd /path/to/your/project
/absolute/path/to/agent-toolkit/workflows/jev-model-router/.venv/bin/jev-codex
```

将路径替换为本机实际路径。若已将 `.venv/bin` 加入 `PATH`，直接运行 `jev-codex` 即可。启动器默认读取路由项目目录中的 `config.toml`；可用 `jev-codex --config /path/to/config.toml` 指定其他配置。启动后像平常一样在 Codex 中输入任务，每个新的用户 turn 都会单独路由。

## 配置

配置文件格式见 [`config.example.toml`](config.example.toml)：

```toml
mode = "route"
confidence_threshold = 0.8
jev_timeout_seconds = 5.0
telemetry_path = "./router-events.jsonl"

[tiers.FAST]
model = "gpt-5.6-luna"
effort = "low"

[tiers.BALANCED]
model = "gpt-5.6-sol"
effort = "medium"

[tiers.DEEP]
model = "gpt-5.6-sol"
effort = "high"
```

示例中的模型名称仅供参考，须与你的账号可用模型一致。配置项说明：

| 配置项 | 作用 |
| --- | --- |
| `mode` | `shadow` 只记录路由决策；`route` 将选出的模型和 effort 用于新 turn。示例配置默认是 `shadow`。 |
| `confidence_threshold` | Jev 置信度低于此值时，回退到 `BALANCED`。 |
| `jev_timeout_seconds` | Jev 判断的超时时间；超时或出错也回退到 `BALANCED`。 |
| `telemetry_path` | JSONL 事件日志路径，相对于配置文件所在目录解析。 |
| `tiers.*` | 每个推理等级对应的 Codex `model` 和 `effort`。 |

修改配置后需要重新启动 `jev-codex`。默认日志位于路由项目目录的 `router-events.jsonl`；查看其中的 `tier`、`selected_model`、`effective_model` 和 `fallback_reason`，即可核对每轮的判断与实际路由。任务文本会发送给 TypeSafe API，日志也会保存截断后的任务文本；请按你的数据要求使用。

## 其他接入方式与支持范围

自定义 Codex App Server 客户端可在路由项目目录运行 `uv run jev-model-router --config config.toml`，用它代替 `codex app-server --stdio`。该命令通过标准输入/输出提供 JSONL 代理，本身不启动交互式 Codex，也不安装或写入全局配置。普通终端使用只需运行 `jev-codex`。

路由仅作用于通过上述入口启动的会话，不会接管已经打开的 Codex 桌面版、IDE 或其他 CLI 会话。当前实现按 `codex-cli 0.159.0` 的 App Server schema 开发；升级 Codex 后应验证 `turn/start` 的 `model` 和 `effort` 字段是否仍兼容。
