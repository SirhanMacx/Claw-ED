"""Tool: curriculum_visualizer — render the knowledge graph as interactive HTML.

Uses a self-contained canvas renderer with zero external dependencies.
Works in any browser including Telegram's in-app browser.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult
from clawed.noise_words import ALL_NOISE

logger = logging.getLogger(__name__)


class CurriculumVisualizerTool:
    """Render the curriculum knowledge graph as an interactive HTML page."""

    risk_level = "read_only"

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
                            "description": "Max nodes to show (default 150)",
                            "default": 150,
                        },
                    },
                    "required": [],
                },
            },
        }

    async def execute(
        self, params: dict[str, Any], context: AgentContext
    ) -> ToolResult:
        max_nodes = params.get("max_nodes", 150)

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

        # Build graph data with aggressive noise filtering
        import sqlite3

        with sqlite3.connect(kg._db_path) as conn:
            conn.row_factory = sqlite3.Row

            # Ensure indexes exist for performance
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_kg_triple_subj_fast "
                "ON kg_triples(subject)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_kg_triple_obj_fast "
                "ON kg_triples(object)"
            )

            entities_raw = conn.execute(
                "SELECT e.id, e.name, e.entity_type, "
                "(SELECT COUNT(*) FROM kg_triples t "
                " WHERE t.subject = e.id OR t.object = e.id) AS connections "
                "FROM kg_entities e WHERE e.teacher_id = ? "
                "AND e.entity_type IN ('topic', 'standard', 'figure') "
                "AND length(e.name) > 5 "
                "ORDER BY connections DESC LIMIT ?",
                (context.teacher_id, max_nodes * 5),
            ).fetchall()

            # Filter noise using shared canonical noise words
            entities = []
            for e in entities_raw:
                name_lower = e["name"].lower().strip()
                if name_lower in ALL_NOISE:
                    continue
                # Skip if contains slide markers
                if "[slide" in name_lower or "slide]" in name_lower:
                    continue
                # Skip single short words
                words = name_lower.split()
                if len(words) == 1 and len(name_lower) < 7:
                    continue
                # Skip if mostly numbers
                alpha = sum(1 for c in name_lower if c.isalpha())
                if len(name_lower) > 0 and alpha / len(name_lower) < 0.5:
                    continue
                entities.append(e)
                if len(entities) >= max_nodes:
                    break

            entity_ids = {e["id"] for e in entities}

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

        # Get teacher name
        teacher_name = "My Curriculum"
        try:
            tp = context.teacher_profile or {}
            if tp.get("name"):
                teacher_name = f"{tp['name']}'s Curriculum"
        except (KeyError, ValueError):
            pass

        # Build self-contained HTML with canvas renderer
        html = _build_canvas_html(
            nodes, edges, teacher_name,
        )

        # Save
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


def _build_canvas_html(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    teacher_name: str,
) -> str:
    """Build a self-contained HTML page with canvas-based graph renderer.

    Zero external dependencies — works in any browser.
    """
    # Double-encode JSON: inject as string literal, parse at runtime.
    # This prevents special characters in labels from breaking JS on
    # strict parsers (iOS Safari, Telegram in-app browser).
    data_json_str = json.dumps(json.dumps({"nodes": nodes, "edges": edges}))

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Curriculum Map</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
html,body {{ width:100%; height:100%; background:#1a1a2e; font-family:-apple-system,sans-serif; overflow:hidden; }}
canvas {{ display:block; cursor:grab; width:100vw; height:100vh; position:fixed; top:0; left:0; }}
canvas:active {{ cursor:grabbing; }}
#info {{
  position:fixed; top:10px; left:10px; background:rgba(26,26,46,0.95);
  padding:12px 16px; border-radius:8px; border:1px solid #333;
  color:#e6e6e6; font-size:13px; z-index:10; max-width:280px;
}}
#info h2 {{ color:#e94560; font-size:15px; margin-bottom:4px; }}
#info .s {{ color:#4a9eff; font-weight:bold; }}
#detail {{
  position:fixed; bottom:10px; right:10px; background:rgba(26,26,46,0.95);
  padding:12px 16px; border-radius:8px; border:1px solid #333;
  color:#ccc; font-size:12px; z-index:10; max-width:300px; display:none;
}}
#detail h3 {{ color:#16c79a; margin-bottom:6px; font-size:14px; }}
#detail .r {{ padding:2px 0; }}
#detail .p {{ color:#e94560; }}
#legend {{
  position:fixed; top:10px; right:10px; background:rgba(26,26,46,0.95);
  padding:10px 14px; border-radius:8px; border:1px solid #333;
  color:#999; font-size:11px; z-index:10;
}}
#legend span {{ display:inline-block; width:10px; height:10px; border-radius:50%;
  margin-right:4px; vertical-align:middle; }}
</style>
</head>
<body>
<div id="info">
  <h2>Curriculum Map</h2>
  <p>{teacher_name}</p>
  <p><span class="s">{len(nodes)}</span> topics &middot;
     <span class="s">{len(edges)}</span> connections</p>
  <p style="margin-top:6px;font-size:11px;color:#555">
    Click node for details. Drag to pan. Scroll to zoom.</p>
</div>
<div id="legend">
  <span style="background:#4a9eff"></span>Topic
  <span style="background:#e94560;margin-left:8px"></span>Standard
  <span style="background:#f5a623;margin-left:8px"></span>Figure
</div>
<div id="detail">
  <h3 id="dt"></h3>
  <div id="dl"></div>
</div>
<canvas id="c"></canvas>
<script>
var D=JSON.parse({data_json_str});
var cv=document.getElementById("c"),cx=cv.getContext("2d"),W,H;
var ns=D.nodes,es=D.edges,nm={{}};
ns.forEach(function(n){{nm[n.id]=n}});
var TC={{topic:"#4a9eff",standard:"#e94560",skill:"#16c79a",figure:"#f5a623",term:"#9b59b6"}};
var PI2=Math.PI*2;
// Init positions in circle
ns.forEach(function(n,i){{
  var a=PI2*i/ns.length,r=Math.min(400,ns.length*4);
  n.x=Math.cos(a)*r+(Math.random()-.5)*80;
  n.y=Math.sin(a)*r+(Math.random()-.5)*80;
  n.vx=0;n.vy=0;
  n.r=Math.min(5+(n.connections||0)*0.3,18);
  n.c=TC[n.type]||"#4a9eff";
}});
// Edge index
var ei={{}};
es.forEach(function(e){{
  if(!ei[e.source])ei[e.source]=[];
  if(!ei[e.target])ei[e.target]=[];
  ei[e.source].push(e);ei[e.target].push(e);
}});
// Physics
function sim(){{
  var rep=3000,k=0.008,dmp=0.88;
  for(var i=0;i<ns.length;i++){{
    var a=ns[i];
    for(var j=i+1;j<ns.length;j++){{
      var b=ns[j],dx=a.x-b.x,dy=a.y-b.y;
      var d=Math.sqrt(dx*dx+dy*dy)||1;
      var f=rep/(d*d);
      a.vx+=dx/d*f;a.vy+=dy/d*f;
      b.vx-=dx/d*f;b.vy-=dy/d*f;
    }}
    a.vx-=a.x*0.0008;a.vy-=a.y*0.0008;
  }}
  es.forEach(function(e){{
    var a=nm[e.source],b=nm[e.target];
    if(!a||!b)return;
    var dx=b.x-a.x,dy=b.y-a.y;
    var d=Math.sqrt(dx*dx+dy*dy)||1;
    var f=(d-120)*k;
    a.vx+=dx/d*f;a.vy+=dy/d*f;
    b.vx-=dx/d*f;b.vy-=dy/d*f;
  }});
  ns.forEach(function(n){{n.vx*=dmp;n.vy*=dmp;n.x+=n.vx;n.y+=n.vy}});
}}
// Camera
var cam={{x:0,y:0,z:1}},drag=false,ds={{x:0,y:0}},cs={{x:0,y:0}},sel=null;
function resize(){{W=cv.width=window.innerWidth;H=cv.height=window.innerHeight}}
window.onresize=resize;resize();
function ts(x,y){{return[(x-cam.x)*cam.z+W/2,(y-cam.y)*cam.z+H/2]}}
function tw(sx,sy){{return[(sx-W/2)/cam.z+cam.x,(sy-H/2)/cam.z+cam.y]}}
function draw(){{
  cx.fillStyle="#1a1a2e";cx.fillRect(0,0,W,H);
  // Edges
  cx.lineWidth=Math.max(0.3,0.5*cam.z);
  es.forEach(function(e){{
    var a=nm[e.source],b=nm[e.target];
    if(!a||!b)return;
    var p1=ts(a.x,a.y),p2=ts(b.x,b.y);
    cx.strokeStyle="rgba(100,100,130,0.25)";
    cx.beginPath();cx.moveTo(p1[0],p1[1]);cx.lineTo(p2[0],p2[1]);cx.stroke();
  }});
  // Nodes
  ns.forEach(function(n){{
    var p=ts(n.x,n.y),r=n.r*cam.z;
    if(r<1)return;
    cx.beginPath();cx.arc(p[0],p[1],r,0,PI2);
    cx.fillStyle=n===sel?"#ffffff":n.c;
    cx.fill();
    if(n===sel){{cx.strokeStyle="#fff";cx.lineWidth=2;cx.stroke()}}
    if(r>3){{
      cx.fillStyle=n===sel?"#fff":"rgba(230,230,230,0.9)";
      var fs=Math.max(8,Math.min(13,r*1.2));
      cx.font=fs+"px -apple-system,sans-serif";
      cx.textAlign="center";
      var lbl=n.label.length>28?n.label.substring(0,26)+"..":n.label;
      cx.fillText(lbl,p[0],p[1]-r-4);
    }}
  }});
}}
function hit(sx,sy){{
  var w=tw(sx,sy);
  for(var i=ns.length-1;i>=0;i--){{
    var n=ns[i],dx=n.x-w[0],dy=n.y-w[1];
    if(dx*dx+dy*dy<(n.r+6)*(n.r+6))return n;
  }}
  return null;
}}
cv.onmousedown=cv.ontouchstart=function(e){{
  e.preventDefault();
  var pt=e.touches?e.touches[0]:e;
  var nd=hit(pt.clientX,pt.clientY);
  if(nd){{
    sel=nd;
    document.getElementById("dt").textContent=nd.label+" ("+nd.type+")";
    var dl=document.getElementById("dl");dl.innerHTML="";
    (ei[nd.id]||[]).slice(0,12).forEach(function(edge){{
      var oid=edge.source===nd.id?edge.target:edge.source;
      var on=nm[oid];
      if(on)dl.innerHTML+='<div class="r"><span class="p">'+edge.label+'</span> &rarr; '+on.label+'</div>';
    }});
    document.getElementById("detail").style.display="block";
  }}else{{
    sel=null;document.getElementById("detail").style.display="none";
    drag=true;ds={{x:pt.clientX,y:pt.clientY}};cs={{x:cam.x,y:cam.y}};
  }}
}};
cv.onmousemove=cv.ontouchmove=function(e){{
  if(!drag)return;e.preventDefault();
  var pt=e.touches?e.touches[0]:e;
  cam.x=cs.x-(pt.clientX-ds.x)/cam.z;
  cam.y=cs.y-(pt.clientY-ds.y)/cam.z;
}};
cv.onmouseup=cv.ontouchend=function(){{drag=false}};
cv.onwheel=function(e){{
  cam.z=Math.max(0.1,Math.min(5,cam.z*(e.deltaY>0?0.9:1.1)));
  e.preventDefault();
}};
// Simulate then animate
for(var i=0;i<300;i++)sim();
function loop(){{resize();sim();draw();requestAnimationFrame(loop)}}
// Delayed start to handle Telegram/mobile late layout
setTimeout(function(){{resize();loop()}},100);
setTimeout(resize,500);
setTimeout(resize,1000);
</script>
</body>
</html>'''
