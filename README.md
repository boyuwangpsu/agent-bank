# agent-bank

**让你的 AI 助手越用越懂你。**

agent-bank 是一个职场记忆 MCP Server。装上之后，你的 AI 助手会记住你的偏好、你的领导风格、你的工作上下文——跨所有项目、所有 workspace，越用越懂你。

## 它能做什么

- 🧠 **记住你是谁**：角色、部门、沟通风格、工作偏好
- 👥 **记住你的人际网络**：领导的汇报风格、同事负责什么、谁注重细节谁看大方向
- 💼 **记住你的工作**：当前项目、KPI、会议决策
- 📝 **自动积累**：对话中发现值得记的信息时，Agent 自动存入记忆
- 🎯 **驱动行为**：生成材料时自动适配领导风格，不需要你每次提醒

## 30 秒安装

### Kiro

编辑 `~/.kiro/settings/mcp.json`（全局配置，所有 workspace 生效）：

```json
{
  "mcpServers": {
    "agent-bank": {
      "command": "uvx",
      "args": ["agent-bank@latest"]
    }
  }
}
```

### Claude Code

```bash
claude mcp add --scope user agent-bank -- uvx agent-bank@latest
```

装完就行了。不需要专门的 workspace，不需要写配置文件，不需要 API key。

## 使用方式

### 首次使用：告诉 AI 你是谁

装好后，在任何对话中说：

> "帮我录入一些基本信息到记忆里"

Agent 会引导你录入身份、领导风格、工作偏好等信息。大约 5 分钟。

### 日常使用：自动积累

正常使用 AI 办公即可。agent-bank 会自动：

- 你说"潘总要求加 ROI 分析" → 自动记住潘总的偏好
- 你说"以后 PPT 不超过 15 页" → 自动记住你的偏好
- 你说"这周在做 AI 平台 POC" → 自动更新工作上下文

### 生成材料时：自动适配

```
你：帮我写个周报给潘总

AI：（自动调用记忆，获取潘总的风格偏好 + 你的工作进展 + KPI）
    （生成的周报自动：数据驱动、包含 ROI、简洁不超过 15 页）
```

你不需要每次提醒"潘总喜欢数据"——Agent 已经记住了。

### 查看记忆

```
你：帮我看看你记住了什么
你：关于潘总你知道什么？
你：忘掉关于王总的记忆
```

## 记忆模型

agent-bank 把记忆分为 5 层：

| 层 | 说明 | 示例 |
|----|------|------|
| **identity** | 你是谁 | "我是张三，数智发展部，负责数据平台" |
| **people** | 人际网络 | "潘总注重数据和 ROI，不喜欢长汇报" |
| **work** | 工作上下文 | "当前在做 AI 使能平台 POC" |
| **knowledge** | 知识术语 | "青冷 = 青岛中集冷藏箱，不是青龙" |
| **preference** | 偏好习惯 | "PPT 不超过 15 页，用中文回复" |

## MCP Tools

| Tool | 说明 |
|------|------|
| `remember` | 存入记忆（Agent 自动调用） |
| `recall` | 检索相关记忆（Agent 自动调用） |
| `people` | 查询某人的完整信息 |
| `profile` | 获取用户画像 |
| `context` | 获取当前工作上下文 |
| `forget` | 删除记忆 |
| `stats` | 查看记忆统计 |

## 核心机制：记忆驱动行为

agent-bank 不只是"存取记忆"。它通过 **MCP Resource** 自动向 Agent 注入行为规则：

- 有领导记忆 → Agent 自动适配领导风格
- 有术语表 → Agent 自动纠正错误术语
- 有偏好 → Agent 自动遵循你的习惯

这些规则随记忆变化自动更新，你不需要手动维护任何配置文件。

## 数据安全

- 所有数据存储在本地 `~/.agent-bank/memory.db`
- 不上传任何数据到云端
- 不需要 API key
- 不需要网络连接

## 技术栈

- Python 3.11+
- SQLite（零依赖存储）
- MCP SDK（标准协议）

## 开发

```bash
git clone https://github.com/你的用户名/agent-bank.git
cd agent-bank
pip install -e ".[dev]"
pytest
```

## License

MIT
