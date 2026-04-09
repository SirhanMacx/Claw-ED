"""Knowledge-graph-powered lesson connections.

Uses the 227K-entity curriculum knowledge graph to suggest cross-unit
connections, prerequisite checks, and "Previously on..." Do Now hooks.

Examples:
- "Your students learned about Hammurabi's Code last week. Today's
  Enlightenment lesson could open with: 'Remember Hammurabi?'"
- "Students haven't covered the prerequisite 'cause-effect analysis'.
  Consider adding a 2-minute scaffolding activity."
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def suggest_connections(
    topic: str,
    teacher_id: str = "",
) -> dict:
    """Query the knowledge graph for connections to a lesson topic.

    Returns:
        {
            "related_topics": [{"name": ..., "relationship": ...}],
            "prerequisites": [{"name": ..., "covered": bool}],
            "previously_on": str | None,  # suggested hook referencing prior lesson
            "cross_unit_links": [{"name": ..., "relationship": ...}],
        }
    """
    result = {
        "related_topics": [],
        "prerequisites": [],
        "previously_on": None,
        "cross_unit_links": [],
    }

    try:
        from clawed.agent_core.memory.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph()

        # Get related topics
        related = kg.query_related(teacher_id, topic, direction="both")
        for r in related[:10]:
            entry = {
                "name": r.get("entity", ""),
                "relationship": r.get("predicate", "related_to"),
                "entity_type": r.get("entity_type", "topic"),
            }
            if r.get("predicate") in ("prerequisite_for", "builds_on"):
                result["prerequisites"].append({
                    "name": r["entity"],
                    "covered": True,  # If it's in the KG, teacher has covered it
                })
            elif r.get("predicate") in ("contrasts_with", "related_to"):
                result["cross_unit_links"].append(entry)
            else:
                result["related_topics"].append(entry)

        # Generate a "Previously on..." hook if we have prerequisites
        if result["prerequisites"]:
            prereq_names = [p["name"] for p in result["prerequisites"][:3]]
            result["previously_on"] = (
                f"Remember when we studied {prereq_names[0]}? "
                f"Today we're building on that foundation."
            )
            if len(prereq_names) > 1:
                others = " and ".join(prereq_names[1:])
                result["previously_on"] = (
                    f"We've already explored {prereq_names[0]} and {others}. "
                    f"Today we'll see how {topic} connects to what you already know."
                )

        logger.info(
            "KG connections for '%s': %d related, %d prerequisites, %d cross-unit",
            topic,
            len(result["related_topics"]),
            len(result["prerequisites"]),
            len(result["cross_unit_links"]),
        )

    except Exception as exc:
        logger.debug("KG connection query failed: %s", exc)

    return result


def inject_connections_into_prompt(
    topic: str,
    teacher_id: str = "",
) -> str:
    """Generate a prompt section with KG-powered connections.

    Returns a string to be appended to the lesson generation prompt,
    providing the LLM with curriculum context from the knowledge graph.
    """
    connections = suggest_connections(topic, teacher_id)

    parts: list[str] = []

    if connections["previously_on"]:
        parts.append(
            "## Prior Learning Connection\n"
            f"Suggested Do Now hook: \"{connections['previously_on']}\"\n"
            "Consider referencing this in the lesson's opening hook."
        )

    if connections["prerequisites"]:
        prereqs = ", ".join(p["name"] for p in connections["prerequisites"])
        parts.append(
            "## Prerequisites (from Knowledge Graph)\n"
            f"Students have already studied: {prereqs}\n"
            "Build on this knowledge. Do NOT re-teach these concepts."
        )

    if connections["cross_unit_links"]:
        links = ", ".join(
            f"{link['name']} ({link['relationship'].replace('_', ' ')})"
            for link in connections["cross_unit_links"][:5]
        )
        parts.append(
            "## Cross-Unit Connections\n"
            f"Related topics from other units: {links}\n"
            "Mention these connections where appropriate to help students "
            "see the bigger picture."
        )

    return "\n\n".join(parts)
