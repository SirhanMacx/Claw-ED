"""Tool: curriculum_visualizer — render the knowledge graph as interactive HTML."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult

logger = logging.getLogger(__name__)

_VIS_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Curriculum Map — {teacher_name}</title>
<script src="https://unpkg.com/vis-network@9/standalone/umd/vis-network.min.js"></script>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, sans-serif; background: #1a1a2e; color: #e6e6e6; }
  #graph { width: 100vw; height: 100vh; }
  #info {
    position: fixed; top: 12px; left: 12px; background: rgba(26,26,46,0.9);
    padding: 16px 20px; border-radius: 8px; border: 1px solid #333;
    max-width: 320px; z-index: 10;
  }
  #info h2 { font-size: 16px; color: #e94560; margin-bottom: 4px; }
  #info p { font-size: 12px; color: #999; }
  #info .stat { color: #4a9eff; font-weight: bold; }
  #detail {
    position: fixed; bottom: 12px; right: 12px; background: rgba(26,26,46,0.95);
    padding: 16px 20px; border-radius: 8px; border: 1px solid #333;
    max-width: 400px; z-index: 10; display: none;
  }
  #detail h3 { color: #16c79a; margin-bottom: 8px; }
  #detail ul { list-style: none; padding: 0; }
  #detail li { font-size: 13px; padding: 2px 0; color: #ccc; }
  #detail li .pred { color: #e94560; }
</style>
</head>
<body>
<div id="info">
  <h2>Curriculum Map</h2>
  <p>{teacher_name}</p>
  <p><span class="stat">{node_count}</span> concepts &middot;
     <span class="stat">{edge_count}</span> relationships</p>
  <p style="margin-top:8px;font-size:11px;color:#666">
    Click a node to see its connections. Scroll to zoom. Drag to pan.
  </p>
</div>
<div id="detail">
  <h3 id="detail-title"></h3>
  <ul id="detail-list"></ul>
</div>
<div id="graph"></div>
<script>
const data = {graph_json};
const TYPE_COLORS = {
  topic: '#4a9eff', standard: '#e94560', skill: '#16c79a',
  figure: '#f5a623', term: '#9b59b6', unit: '#1abc9c',
};
const nodes = new vis.DataSet(data.nodes.map(n => ({
  id: n.id, label: n.label,
  color: { background: TYPE_COLORS[n.type] || '#4a9eff', border: '#333' },
  font: { color: '#e6e6e6', size: Math.min(14 + (n.connections || 0), 24) },
  shape: 'dot', size: Math.min(8 + (n.connections || 0) * 2, 30),
})));
const edges = new vis.DataSet(data.edges.map(e => ({
  from: e.source, to: e.target,
  label: e.label || '', font: { color: '#666', size: 9 },
  color: { color: '#444', highlight: '#e94560' },
  arrows: 'to', smooth: { type: 'continuous' },
})));
const container = document.getElementById('graph');
const network = new vis.Network(container, { nodes, edges }, {
  physics: { solver: 'forceAtlas2Based', forceAtlas2Based: {
    gravitationalConstant: -50, centralGravity: 0.005, springLength: 120,
  }},
  interaction: { hover: true, tooltipDelay: 200 },
});
network.on('click', function(params) {
  const detail = document.getElementById('detail');
  if (params.nodes.length === 0) { detail.style.display = 'none'; return; }
  const nodeId = params.nodes[0];
  const node = data.nodes.find(n => n.id === nodeId);
  if (!node) return;
  document.getElementById('detail-title').textContent = node.label + ' (' + node.type + ')';
  const list = document.getElementById('detail-list');
  list.innerHTML = '';
  const rels = data.edges.filter(e => e.source === nodeId || e.target === nodeId);
  rels.slice(0, 15).forEach(r => {
    const other = r.source === nodeId ? r.target : r.source;
    const otherNode = data.nodes.find(n => n.id === other);
    const li = document.createElement('li');
    li.innerHTML = '<span class="pred">' + (r.label||'related') + '</span> → ' + (otherNode ? otherNode.label : other);
    list.appendChild(li);
  });
  detail.style.display = 'block';
});
</script>
</body>
</html>"""


class CurriculumVisualizerTool:
    """Render the curriculum knowledge graph as an interactive HTML page."""

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "curriculum_visualizer",
                "description": (
                    "Generate an interactive visual map of the teacher's "
                    "curriculum — shows how topics, standards, skills, and "
                    "vocabulary are connected. Opens in a browser."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "max_nodes": {
                            "type": "integer",
                            "description": "Max nodes to show (default 200)",
                            "default": 200,
                        },
                    },
                    "required": [],
                },
            },
        }

    async def execute(
        self, params: dict[str, Any], context: AgentContext
    ) -> ToolResult:
        max_nodes = params.get("max_nodes", 200)

        try:
            from clawed.agent_core.memory.knowledge_graph import CurriculumKG
        except ImportError:
            return ToolResult(text="Knowledge graph module not available.")

        kg = CurriculumKG()
        stats = kg.stats(context.teacher_id)

        if stats["entity_count"] == 0:
            return ToolResult(
                text="No curriculum data in the knowledge graph yet. "
                "Ingest your materials first with /ingest."
            )

        # Build graph data
        import sqlite3

        with sqlite3.connect(kg._db_path) as conn:
            conn.row_factory = sqlite3.Row

            # Get top entities by connection count
            entities = conn.execute(
                "SELECT e.id, e.name, e.entity_type, "
                "(SELECT COUNT(*) FROM kg_triples t "
                " WHERE t.subject = e.id OR t.object = e.id) AS connections "
                "FROM kg_entities e WHERE e.teacher_id = ? "
                "ORDER BY connections DESC LIMIT ?",
                (context.teacher_id, max_nodes),
            ).fetchall()

            entity_ids = {e["id"] for e in entities}

            # Get edges between visible nodes
            triples = conn.execute(
                "SELECT subject, predicate, object FROM kg_triples "
                "WHERE teacher_id = ? AND valid_to IS NULL",
                (context.teacher_id,),
            ).fetchall()

        nodes = [
            {
                "id": e["id"],
                "label": e["name"],
                "type": e["entity_type"],
                "connections": e["connections"],
            }
            for e in entities
        ]

        edges = [
            {
                "source": t["subject"],
                "target": t["object"],
                "label": t["predicate"].replace("_", " "),
            }
            for t in triples
            if t["subject"] in entity_ids and t["object"] in entity_ids
        ]

        graph_json = json.dumps({"nodes": nodes, "edges": edges})

        # Get teacher name
        teacher_name = "My Curriculum"
        try:
            tp = context.teacher_profile or {}
            if tp.get("name"):
                teacher_name = f"{tp['name']}'s Curriculum"
        except Exception:
            pass

        # Render HTML
        html = _VIS_TEMPLATE.format(
            teacher_name=teacher_name,
            node_count=len(nodes),
            edge_count=len(edges),
            graph_json=graph_json,
        )

        # Save to output dir
        output_dir = Path("~/clawed_output").expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / "curriculum_map.html"
        out_path.write_text(html, encoding="utf-8")

        return ToolResult(
            text=(
                f"Curriculum map generated: {out_path}\n"
                f"{len(nodes)} concepts, {len(edges)} relationships.\n"
                "Open in any browser to explore your curriculum visually."
            ),
            files=[out_path],
            side_effects=[f"Generated curriculum map: {out_path}"],
        )
