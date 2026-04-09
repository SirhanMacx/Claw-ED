"""Compile a guided learning journey — interactive step-by-step HTML walkthrough.

Transforms a MasterContent lesson into a visual, self-paced student
experience with checkpoints, reveal-on-click content, and progress
tracking. Inspired by DeepTutor's Guided Learning mode.

The output is a single self-contained HTML file (no external deps)
that students can open in any browser.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from clawed.master_content import MasterContent
    from clawed.models import TeacherPersona

logger = logging.getLogger(__name__)


async def compile_journey(
    master: "MasterContent",
    persona: "TeacherPersona | None" = None,
    output_dir: Path | None = None,
) -> Path | None:
    """Generate an interactive learning journey HTML from lesson content."""
    if output_dir is None:
        output_dir = Path("~/clawed_output").expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # Build journey steps from MasterContent
    steps = []

    # Step 1: Hook (Do Now)
    if master.do_now:
        steps.append({
            "title": "Warm Up",
            "type": "question",
            "content": master.do_now.stimulus,
            "questions": master.do_now.questions[:2],
        })

    # Step 2-N: Vocabulary (if any)
    if master.vocabulary:
        vocab_items = [
            f"<b>{v.term}</b>: {v.definition}"
            for v in master.vocabulary[:8]
        ]
        steps.append({
            "title": "Key Vocabulary",
            "type": "reveal",
            "content": "Learn these terms before we begin.",
            "items": vocab_items,
        })

    # Step 3-N: Direct instruction sections
    for i, section in enumerate(master.direct_instruction):
        step = {
            "title": section.heading,
            "type": "content",
            "content": section.content,
        }
        if section.key_points:
            step["key_points"] = section.key_points[:4]
        steps.append(step)

    # Step N+1: Guided practice
    if master.guided_notes:
        steps.append({
            "title": "Check Your Understanding",
            "type": "quiz",
            "items": [
                {"q": n.prompt, "a": n.answer}
                for n in master.guided_notes[:5]
            ],
        })

    # Step N+2: Exit ticket
    if master.exit_ticket:
        steps.append({
            "title": "Exit Ticket",
            "type": "question",
            "content": master.exit_ticket[0].stimulus if master.exit_ticket else "",
            "questions": [
                q.question for q in master.exit_ticket[:3]
            ],
        })

    if not steps:
        return None

    # Build HTML
    steps_json = json.dumps(steps)
    safe_title = master.title.replace('"', '\\"')

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{safe_title} — Learning Journey</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,sans-serif;background:#f8f9fa;color:#333;
  max-width:700px;margin:0 auto;padding:20px}}
h1{{font-size:1.5rem;color:#1a1a2e;margin-bottom:8px}}
.sub{{color:#666;font-size:0.9rem;margin-bottom:24px}}
.step{{background:#fff;border-radius:12px;padding:20px 24px;margin-bottom:16px;
  box-shadow:0 2px 8px rgba(0,0,0,0.06);border-left:4px solid #4a9eff;
  cursor:pointer;transition:all 0.2s}}
.step.done{{border-left-color:#16c79a;opacity:0.7}}
.step.active{{border-left-color:#e94560;box-shadow:0 4px 16px rgba(0,0,0,0.1)}}
.step h3{{font-size:1.1rem;color:#1a1a2e;margin-bottom:8px}}
.step .body{{display:none;margin-top:12px;line-height:1.6}}
.step.active .body{{display:block}}
.step .tag{{font-size:0.7rem;color:#fff;background:#4a9eff;padding:2px 8px;
  border-radius:10px;display:inline-block;margin-bottom:8px}}
.step .tag.quiz{{background:#e94560}}
.step .tag.reveal{{background:#f5a623}}
.kp{{background:#f0f4ff;padding:8px 12px;border-radius:6px;margin:4px 0;font-size:0.9rem}}
.reveal-item{{background:#fafafa;padding:10px 14px;border-radius:8px;margin:6px 0;
  cursor:pointer;border:1px solid #eee}}
.reveal-item .answer{{display:none;margin-top:8px;color:#16c79a;font-weight:500}}
.reveal-item.shown .answer{{display:block}}
.progress{{background:#e9ecef;border-radius:20px;height:8px;margin-bottom:20px}}
.progress-bar{{background:linear-gradient(90deg,#4a9eff,#16c79a);height:100%;
  border-radius:20px;transition:width 0.3s}}
.btn{{background:#4a9eff;color:#fff;border:none;padding:10px 20px;border-radius:8px;
  font-size:0.95rem;cursor:pointer;margin-top:12px}}
.btn:hover{{background:#3a8adf}}
</style>
</head>
<body>
<h1>{safe_title}</h1>
<p class="sub">{master.objective}</p>
<div class="progress"><div class="progress-bar" id="pb" style="width:0%"></div></div>
<div id="steps"></div>
<script>
var steps={steps_json};
var current=0;
var container=document.getElementById("steps");
function render(){{
  container.innerHTML="";
  steps.forEach(function(s,i){{
    var div=document.createElement("div");
    div.className="step"+(i===current?" active":"")+(i<current?" done":"");
    var tag=s.type==="quiz"?"quiz":s.type==="reveal"?"reveal":"content";
    var h='<span class="tag '+tag+'">Step '+(i+1)+"/"+steps.length+"</span>";
    h+="<h3>"+s.title+"</h3>";
    h+='<div class="body">';
    if(s.content)h+="<p>"+s.content+"</p>";
    if(s.key_points)s.key_points.forEach(function(kp){{h+='<div class="kp">'+kp+"</div>"}});
    if(s.items&&s.type==="reveal")s.items.forEach(function(item,j){{
      h+='<div class="reveal-item" onclick="this.classList.toggle(\'shown\')">'+
        "Click to reveal"+'<div class="answer">'+item+"</div></div>"}});
    if(s.items&&s.type==="quiz")s.items.forEach(function(item){{
      h+='<div class="reveal-item" onclick="this.classList.toggle(\'shown\')">'+
        item.q+'<div class="answer">'+item.a+"</div></div>"}});
    if(s.questions)s.questions.forEach(function(q){{h+="<p><b>"+q+"</b></p>"}});
    if(i===current)h+='<button class="btn" onclick="next()">Continue &rarr;</button>';
    h+="</div>";
    div.innerHTML=h;
    div.onclick=function(){{if(i<=current){{current=i;render()}}}};
    container.appendChild(div);
  }});
  document.getElementById("pb").style.width=Math.round((current/steps.length)*100)+"%";
}}
function next(){{if(current<steps.length-1){{current++;render()}}
  else{{document.getElementById("pb").style.width="100%";
    alert("Journey complete! Great work.")}}}}
render();
</script>
</body>
</html>'''

    from clawed.io import safe_filename
    filename = safe_filename(master.title, max_len=50) + "_journey.html"
    out_path = output_dir / filename
    out_path.write_text(html, encoding="utf-8")
    logger.info("Learning journey: %s (%d steps)", out_path.name, len(steps))
    return out_path
