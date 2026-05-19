"""Automatic steering generation from memories.

This is the core differentiator: memories don't just get stored and retrieved,
they actively drive Agent behavior through auto-generated rules.
"""

from agent_bank.db import Database
from agent_bank.models import Memory


def generate_steering(db: Database) -> str:
    """Generate steering text from current memories.

    This text is served as an MCP Resource and automatically injected
    into the Agent's context. It tells the Agent HOW to use the memory
    system and WHAT behavioral rules to follow.

    Returns:
        Markdown-formatted steering text.
    """
    sections: list[str] = []

    # Header with core behavioral rules
    sections.append(_header())

    # Identity summary
    identity = db.get_all(category="identity")
    if identity:
        sections.append(_identity_section(identity))

    # People / leader style rules
    people = db.get_all(category="people")
    if people:
        sections.append(_people_section(people))

    # Work context
    work = db.get_all(category="work")
    if work:
        sections.append(_work_section(work))

    # Preferences
    preferences = db.get_all(category="preference")
    if preferences:
        sections.append(_preference_section(preferences))

    # Knowledge / terminology
    knowledge = db.get_all(category="knowledge")
    if knowledge:
        sections.append(_knowledge_section(knowledge))

    # Auto-capture rules (always present)
    sections.append(_capture_rules())

    return "\n\n".join(sections)


def _header() -> str:
    return """# agent-bank 行为规则（自动生成）

你连接了 agent-bank 记忆系统。请遵循以下规则：

1. **执行任务前先 recall**：涉及特定人、项目、汇报时，先调用 recall 获取相关记忆
2. **发现值得记的信息时 remember**：用户表达偏好、领导要求、工作变化时，主动调用 remember
3. **风格对齐**：生成材料时，参考相关人的风格偏好
4. **不要提及记忆系统本身**：除非用户主动问，否则不要说"我从记忆中找到..."，直接用记忆影响输出"""


def _identity_section(memories: list[Memory]) -> str:
    lines = ["## 用户身份"]
    for m in memories:
        lines.append(f"- {m.content}")
    return "\n".join(lines)


def _people_section(memories: list[Memory]) -> str:
    lines = ["## 人际网络与风格适配"]
    # Group by subject
    by_subject: dict[str, list[Memory]] = {}
    for m in memories:
        key = m.subject or "其他"
        by_subject.setdefault(key, []).append(m)

    for person, mems in by_subject.items():
        lines.append(f"\n### {person}")
        for m in mems:
            lines.append(f"- {m.content}")
    return "\n".join(lines)


def _work_section(memories: list[Memory]) -> str:
    lines = ["## 当前工作上下文"]
    for m in sorted(memories, key=lambda x: x.updated_at, reverse=True)[:10]:
        prefix = f"[{m.subject}] " if m.subject else ""
        lines.append(f"- {prefix}{m.content}")
    return "\n".join(lines)


def _preference_section(memories: list[Memory]) -> str:
    lines = ["## 用户偏好"]
    for m in memories:
        lines.append(f"- {m.content}")
    return "\n".join(lines)


def _knowledge_section(memories: list[Memory]) -> str:
    lines = ["## 知识与术语"]
    for m in memories:
        lines.append(f"- {m.content}")
    return "\n".join(lines)


def _capture_rules() -> str:
    return """## 自动捕获规则

对话中发现以下信号时，请主动调用 agent-bank 的 remember tool：

| 信号 | category | 示例 |
|------|----------|------|
| 用户说"记住/以后/总是/每次/不要再" | preference | "以后 PPT 不要超过 15 页" |
| 提到某人的偏好/要求/风格/反馈 | people | "潘总说要加 ROI 分析" |
| 工作状态变化 | work | "这周在做 POC"、"项目延期了" |
| 会议决策/待办 | work | "会上决定用方案 B" |
| 术语纠正 | knowledge | "不是青龙，是青冷" |
| 人际关系信息 | people | "李总是潘总的直属下级" |

**不要记**：一次性技术问题、纯操作指令、Agent 自己的推理过程。"""
