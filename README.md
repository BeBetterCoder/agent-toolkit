# Agent Toolkit

个人开发的 Agent 工具集，采用 monorepo 管理可复用的 Skills、MCP Servers、
Workflows、Prompts、Configs 和配套示例。

## Projects

| Project | Type | Description |
| --- | --- | --- |
| [`task-continuity`](skills/task-continuity/) | Agent skill | 在额度或上下文不足前保存可恢复的任务检查点，并在新会话中安全续接。 |
| [`jev-decision-mcp`](mcp-servers/jev-decision-mcp/) | MCP server | 使用 Jev / TypeSafe 进行带置信度门控的结构化语义判断。 |

## Repository layout

```text
agent-toolkit/
├── skills/        # 可独立安装或复制的 Agent skills
├── mcp-servers/   # 独立开发、测试和发布的 MCP servers
├── workflows/     # 多步骤 Agent 工作流
├── prompts/       # 可复用 Prompt 模板
├── configs/       # 跨工具的示例配置（不存放密钥）
├── examples/      # 端到端使用示例
├── scripts/       # 仓库级开发与维护脚本
├── docs/          # 设计文档与使用指南
└── .github/       # GitHub Actions 与社区配置
```

## Development model

每个子项目是一个自包含单元，拥有自己的依赖清单、锁文件、测试和发布配置。
根目录不强制统一运行时或包管理器，避免不同类型的 Agent 工具相互耦合。

进入对应子项目后，按照该目录中的 `README.md` 开发和测试。例如：

```bash
cd mcp-servers/jev-decision-mcp
uv sync --dev
uv run pytest
```

## Adding a project

1. 根据类型选择顶层目录，并为项目创建独立子目录。
2. 提供项目级 `README.md`、测试和明确的运行入口。
3. 将项目添加到上方 Projects 表格。
4. 不提交 API keys、tokens、个人路径或机器专用配置。

## License

Unless stated otherwise inside a subproject, this repository is licensed under
the [MIT License](LICENSE).
