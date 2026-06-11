"""Generate a local memory governance dashboard."""

from __future__ import annotations

import json
from dataclasses import dataclass
from html import escape
from pathlib import Path

from agent_bank.models import Memory


CATEGORY_LABELS = {
    "identity": "我是谁",
    "people": "我身边的人",
    "work": "我在做什么",
    "knowledge": "知识与术语",
    "preference": "我的偏好",
}

RELATION_LABELS = {
    "knows_person": "关键人",
    "works_on": "当前工作",
    "knows_concept": "术语",
    "prefers": "偏好",
    "describes_self": "身份",
    "relates_to": "关联",
}

EVENT_LABELS = {
    "remembered": "新增记忆",
    "fact_confirmed": "确认事实",
    "fact_rejected": "废弃事实",
    "fact_stale": "标记过期",
    "fact_merged": "合并事实",
}

FACT_STATUS_LABELS = {
    "active": "待确认",
    "confirmed": "已确认",
    "rejected": "已废弃",
    "stale": "已过期",
    "merged": "已合并",
}


@dataclass(frozen=True)
class TimelineEvent:
    """A display event derived from memory creation or evolution."""

    date: str
    title: str
    body: str


def render_dashboard_html(store) -> str:
    """Render the full HTML dashboard for the current memory bank."""
    memories = store.get_all()
    by_category = _group_by_category(memories)
    graph = store.graph_snapshot()
    timeline = _build_timeline(memories, graph)

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>agent-bank 记忆中枢</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f8fb;
      --panel: #ffffff;
      --text: #1f2a3d;
      --muted: #5f6e82;
      --line: #dbe3ee;
      --soft: #eef4fb;
      --accent: #243b5a;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.5;
    }}
    main {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 28px 20px 42px;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      gap: 18px;
      align-items: flex-start;
      margin-bottom: 20px;
    }}
    h1 {{
      margin: 0 0 6px;
      font-size: 28px;
      letter-spacing: 0;
    }}
    h2 {{
      margin: 0 0 12px;
      font-size: 17px;
      letter-spacing: 0;
    }}
    h3 {{
      margin: 0 0 8px;
      font-size: 14px;
      letter-spacing: 0;
    }}
    p {{ margin: 0; }}
    .subtitle {{ color: var(--muted); }}
    .grid {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 360px;
      gap: 16px;
      align-items: start;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }}
    .summary {{
      font-size: 18px;
      line-height: 1.55;
      margin-bottom: 14px;
    }}
    .chips {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .chip {{
      border: 1px solid #cbd8e7;
      border-radius: 999px;
      background: #fff;
      color: #43546a;
      padding: 5px 9px;
      font-size: 12px;
    }}
    .section-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      margin-top: 16px;
    }}
    .memory-card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #fbfdff;
      min-height: 120px;
    }}
    .memory-card ul {{
      margin: 0;
      padding-left: 18px;
      color: #35465d;
    }}
    .memory-card li {{ margin: 6px 0; }}
    .map {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
    }}
    .node {{
      border: 1px solid #9fb5d0;
      border-radius: 999px;
      background: #f8fbff;
      padding: 8px 11px;
      font-size: 13px;
    }}
    .node.core {{
      background: var(--accent);
      border-color: var(--accent);
      color: #fff;
    }}
    .arrow {{ color: #91a4ba; }}
    .timeline {{
      display: grid;
      gap: 10px;
    }}
    .event {{
      border-left: 3px solid #91a8c4;
      padding: 4px 0 8px 12px;
    }}
    .date {{
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 2px;
    }}
    .event strong {{ display: block; }}
    .rule {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      background: #fbfdff;
      margin-bottom: 8px;
    }}
    .meta {{
      color: var(--muted);
      font-size: 12px;
      margin-top: 5px;
    }}
    @media (max-width: 860px) {{
      .grid, .section-grid {{ grid-template-columns: 1fr; }}
      header {{ display: block; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>agent-bank 记忆中枢</h1>
        <p class="subtitle">画像摘要优先：先看 Agent 当前怎么理解我，再看图谱关系和时间演进。</p>
      </div>
      <div class="chip">本地生成 · 不上传</div>
    </header>

    <div class="grid">
      <section class="panel">
        <h2>Agent 当前怎么理解我</h2>
        <p class="summary">{_profile_summary(by_category)}</p>
        <div class="chips">{_category_chips(by_category)}</div>

        <div class="section-grid">
          {_category_card("identity", by_category)}
          {_category_card("work", by_category)}
          {_category_card("people", by_category)}
          {_category_card("preference", by_category)}
          {_category_card("knowledge", by_category)}
          {_behavior_preview(by_category)}
        </div>
      </section>

      <aside class="panel">
        <h2>时间轴</h2>
        <div class="timeline">{_timeline_html(timeline)}</div>
      </aside>
    </div>

    <section class="panel" style="margin-top:16px">
      <h2>记忆图谱</h2>
      <div class="map">{_memory_map(graph)}</div>
      <p class="meta">MVP 先展示核心关联。下一步可把每个节点展开到证据、时间线、治理动作。</p>
    </section>

    <section class="panel" style="margin-top:16px">
      <h2>事实治理状态</h2>
      <div class="timeline">{_fact_status_html(graph)}</div>
    </section>
  </main>
</body>
</html>
"""


def write_dashboard(store, output_path: Path) -> Path:
    """Write the generated dashboard HTML and return its path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_dashboard_html(store), encoding="utf-8")
    return output_path


def _group_by_category(memories: list[Memory]) -> dict[str, list[Memory]]:
    grouped = {category: [] for category in CATEGORY_LABELS}
    for memory in memories:
        grouped.setdefault(memory.category, []).append(memory)
    for category_memories in grouped.values():
        category_memories.sort(key=lambda m: (m.importance, m.updated_at), reverse=True)
    return grouped


def _profile_summary(by_category: dict[str, list[Memory]]) -> str:
    identity = _first_content(by_category, "identity", "还没有足够身份记忆")
    work = _first_content(by_category, "work", "当前工作上下文还不完整")
    people = _first_content(by_category, "people", "关键人偏好还不完整")
    preference = _first_content(by_category, "preference", "输出偏好还不完整")
    return escape(f"{identity}。当前重点：{work}。重要关系：{people}。默认偏好：{preference}。")


def _first_content(
    by_category: dict[str, list[Memory]], category: str, fallback: str
) -> str:
    memories = by_category.get(category, [])
    if not memories:
        return fallback
    return memories[0].content.rstrip("。")


def _category_chips(by_category: dict[str, list[Memory]]) -> str:
    chips = []
    for category, label in CATEGORY_LABELS.items():
        count = len(by_category.get(category, []))
        chips.append(f'<span class="chip">{escape(label)} · {count}</span>')
    return "".join(chips)


def _category_card(category: str, by_category: dict[str, list[Memory]]) -> str:
    label = CATEGORY_LABELS[category]
    items = by_category.get(category, [])[:4]
    if not items:
        body = '<p class="subtitle">暂未记录。后续可通过 remember 或引导录入补齐。</p>'
    else:
        body = "<ul>" + "".join(_memory_item(m) for m in items) + "</ul>"
    return f"""
<article class="memory-card">
  <h3>{escape(label)}</h3>
  {body}
</article>"""


def _memory_item(memory: Memory) -> str:
    subject = f"{memory.subject}：" if memory.subject else ""
    return (
        f"<li>{escape(subject + memory.content)}"
        f'<div class="meta">重要性 {memory.importance:.1f} · 更新 {_date(memory.updated_at)}</div></li>'
    )


def _behavior_preview(by_category: dict[str, list[Memory]]) -> str:
    rules = []
    for memory in by_category.get("people", [])[:2]:
        subject = memory.subject or "相关人"
        rules.append(f"给{subject}的材料：参考 {memory.content}")
    for memory in by_category.get("preference", [])[:2]:
        rules.append(memory.content)
    for memory in by_category.get("knowledge", [])[:2]:
        rules.append(f"术语纠错：{memory.content}")

    if not rules:
        content = '<p class="subtitle">暂无可预览规则。</p>'
    else:
        content = "".join(f'<div class="rule">{escape(rule)}</div>' for rule in rules[:5])

    return f"""
<article class="memory-card">
  <h3>会如何影响 Agent 行为</h3>
  {content}
</article>"""


def _memory_map(graph: dict[str, list[dict]]) -> str:
    nodes_by_id = {node["id"]: node for node in graph["nodes"]}
    pieces = ['<span class="node core">我 / 用户画像</span>']
    for edge in graph["edges"][:12]:
        target = nodes_by_id.get(edge["target_node_id"])
        if not target:
            continue
        relation = RELATION_LABELS.get(edge["relation"], edge["relation"])
        pieces.append(f'<span class="arrow">关系：{escape(relation)} →</span>')
        pieces.append(f'<span class="node">{escape(target["name"])}</span>')
    if len(pieces) == 1:
        pieces.append('<span class="arrow">暂无关系</span>')
    return "".join(pieces)


def _build_timeline(
    memories: list[Memory], graph: dict[str, list[dict]]
) -> list[TimelineEvent]:
    events: list[TimelineEvent] = []
    for event in graph["timeline"]:
        label = EVENT_LABELS.get(event["event_type"], event["event_type"])
        subject = event["subject"] or CATEGORY_LABELS.get(event["category"], event["category"])
        events.append(
            TimelineEvent(
                date=event["occurred_at"],
                title=f"{label} · {subject}",
                body=event["content"],
            )
        )

    for memory in memories:
        for entry in memory.timeline:
            reason = entry.get("reason") or "记忆被更新"
            old_content = entry.get("old_content", "")
            events.append(
                TimelineEvent(
                    date=entry.get("date", memory.updated_at),
                    title=reason,
                    body=f"旧认知：{old_content} → 新认知：{memory.content}",
                )
            )

    events.sort(key=lambda event: event.date, reverse=True)
    return events[:12]


def _timeline_html(events: list[TimelineEvent]) -> str:
    if not events:
        return '<p class="subtitle">还没有记忆演进记录。</p>'
    return "".join(
        f"""
<div class="event">
  <div class="date">{escape(_date(event.date))}</div>
  <strong>{escape(event.title)}</strong>
  <p>{escape(event.body)}</p>
</div>"""
        for event in events
    )


def _fact_status_html(graph: dict[str, list[dict]]) -> str:
    facts = graph["facts"][:12]
    if not facts:
        return '<p class="subtitle">还没有可治理的事实。</p>'

    rows = []
    for fact in facts:
        status = FACT_STATUS_LABELS.get(fact["status"], fact["status"])
        metadata = _json_object(fact.get("metadata"))
        reason = metadata.get("reason") or "暂无治理原因"
        rows.append(
            f"""
<div class="event">
  <div class="date">{escape(status)}</div>
  <strong>{escape(fact["statement"])}</strong>
  <p>{escape(reason)}</p>
</div>"""
        )
    return "".join(rows)


def _json_object(value) -> dict:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _date(value: str | None) -> str:
    if not value:
        return "未知时间"
    return value[:10]
