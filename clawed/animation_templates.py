"""Pre-built Manim scene templates for common educational animation patterns.

Each template is a self-contained Manim Scene subclass that accepts structured
data and produces a clear, educational animation. Templates follow cognitive
load principles: max 6 on-screen elements, 2-3 second pauses between reveals,
sans-serif fonts for readability on projectors.

These templates are used by generate_animation tool when the LLM selects a
known pattern instead of generating custom Manim code from scratch.
"""

from __future__ import annotations

# ── Color palettes (education-friendly, high contrast) ──────────────
COLORS = {
    "bg": "#1a1a2e",  # dark navy background
    "text": "#e6e6e6",  # near-white text
    "accent": "#e94560",  # coral red accent
    "highlight": "#0f3460",  # deep blue highlight
    "success": "#16c79a",  # teal green
    "warning": "#f5a623",  # amber
    "info": "#4a9eff",  # bright blue
}

# ── Template: Historical Timeline ────────────────────────────────────

TIMELINE_TEMPLATE = '''
from manim import *

class HistoricalTimeline(Scene):
    """Animated timeline with era shading, event markers, and date labels."""

    def construct(self):
        title = Text("{title}", font_size=42, color="{text_color}").to_edge(UP, buff=0.4)
        self.play(Write(title), run_time=1)
        self.wait(0.5)

        # Timeline axis
        events = {events_repr}
        if not events:
            return

        min_year = min(e[0] for e in events)
        max_year = max(e[0] for e in events)
        span = max(max_year - min_year, 1)

        line = NumberLine(
            x_range=[min_year, max_year, max(span // 4, 1)],
            length=10,
            color=WHITE,
            include_numbers=True,
            font_size=24,
        ).shift(DOWN * 0.5)
        self.play(Create(line), run_time=1.5)
        self.wait(0.5)

        # Event markers with staggered labels (alternate above/below)
        for i, (year, label) in enumerate(events):
            dot = Dot(line.n2p(year), color="{accent_color}", radius=0.12)
            above = (i % 2 == 0)
            direction = UP if above else DOWN
            text = Text(
                label[:40],
                font_size=20,
                color="{text_color}",
            ).next_to(dot, direction, buff=0.3)

            # Connector line from dot to label
            connector = Line(
                dot.get_center(),
                text.get_center() - direction * 0.15,
                color=GREY_B,
                stroke_width=1,
            )

            self.play(
                FadeIn(dot, scale=1.5),
                Create(connector),
                FadeIn(text, shift=direction * 0.2),
                run_time=0.8,
            )
            self.wait(0.6)

        self.wait(2)
'''

# ── Template: Cause and Effect Diagram ───────────────────────────────

CAUSE_EFFECT_TEMPLATE = '''
from manim import *

class CauseEffectDiagram(Scene):
    """Animated cause-effect diagram with arrows connecting cause to effect."""

    def construct(self):
        title = Text("{title}", font_size=42, color="{text_color}").to_edge(UP, buff=0.4)
        self.play(Write(title), run_time=1)
        self.wait(0.5)

        causes = {causes_repr}
        effects = {effects_repr}

        n_pairs = min(len(causes), len(effects), 4)  # max 4 pairs on screen

        cause_header = Text("Causes", font_size=30, color="{accent_color}").move_to(LEFT * 4 + UP * 2)
        effect_header = Text("Effects", font_size=30, color="{success_color}").move_to(RIGHT * 4 + UP * 2)
        self.play(Write(cause_header), Write(effect_header), run_time=0.8)

        for i in range(n_pairs):
            y_pos = 1 - i * 1.2

            # Cause box
            cause_text = Text(causes[i][:35], font_size=22, color="{text_color}")
            cause_box = RoundedRectangle(
                corner_radius=0.15,
                width=cause_text.width + 0.5,
                height=0.7,
                color="{accent_color}",
            ).move_to(LEFT * 4 + UP * y_pos)
            cause_text.move_to(cause_box)

            # Effect box
            effect_text = Text(effects[i][:35], font_size=22, color="{text_color}")
            effect_box = RoundedRectangle(
                corner_radius=0.15,
                width=effect_text.width + 0.5,
                height=0.7,
                color="{success_color}",
            ).move_to(RIGHT * 4 + UP * y_pos)
            effect_text.move_to(effect_box)

            # Arrow
            arrow = Arrow(
                cause_box.get_right(),
                effect_box.get_left(),
                color=GREY_B,
                buff=0.1,
            )

            self.play(
                FadeIn(cause_box), Write(cause_text),
                run_time=0.6,
            )
            self.play(GrowArrow(arrow), run_time=0.5)
            self.play(
                FadeIn(effect_box), Write(effect_text),
                run_time=0.6,
            )
            self.wait(0.5)

        self.wait(2)
'''

# ── Template: Process Flow ───────────────────────────────────────────

PROCESS_FLOW_TEMPLATE = '''
from manim import *

class ProcessFlow(Scene):
    """Sequential process with step boxes and connecting arrows."""

    def construct(self):
        title = Text("{title}", font_size=42, color="{text_color}").to_edge(UP, buff=0.4)
        self.play(Write(title), run_time=1)
        self.wait(0.5)

        steps = {steps_repr}
        n = min(len(steps), 6)  # max 6 steps

        # Arrange in 2 rows of 3 for more than 3 steps
        if n <= 3:
            positions = [LEFT * (3 - i * 3) for i in range(n)]
        else:
            row1 = min(3, n)
            row2 = n - row1
            positions = []
            for i in range(row1):
                x = -3 + i * 3
                positions.append(RIGHT * x + UP * 0.5)
            for i in range(row2):
                x = -3 + i * 3
                positions.append(RIGHT * x + DOWN * 2)

        prev_box = None
        for i, (step, pos) in enumerate(zip(steps[:n], positions)):
            step_num = Text(str(i + 1), font_size=28, color="{accent_color}", weight=BOLD)
            step_text = Text(step[:30], font_size=20, color="{text_color}")
            box = RoundedRectangle(
                corner_radius=0.2,
                width=2.8,
                height=1.2,
                color="{info_color}",
            ).move_to(pos)
            step_num.move_to(box.get_top() + DOWN * 0.25)
            step_text.move_to(box.get_center() + DOWN * 0.15)

            anims = [FadeIn(box), Write(step_num), Write(step_text)]

            if prev_box is not None:
                arrow = Arrow(
                    prev_box.get_right() if pos[1] == prev_box.get_center()[1] else prev_box.get_bottom(),
                    box.get_left() if pos[1] == prev_box.get_center()[1] else box.get_top(),
                    color=GREY_B,
                    buff=0.1,
                )
                anims.append(GrowArrow(arrow))

            self.play(*anims, run_time=0.8)
            self.wait(0.8)
            prev_box = box

        self.wait(2)
'''

# ── Template: Concept Map ────────────────────────────────────────────

CONCEPT_MAP_TEMPLATE = '''
from manim import *
import numpy as np

class ConceptMap(Scene):
    """Central concept with branching related concepts."""

    def construct(self):
        # Central concept
        center_text = Text("{center}", font_size=36, color="{text_color}", weight=BOLD)
        center_circle = Circle(radius=1.2, color="{accent_color}", fill_opacity=0.15)
        center_text.move_to(center_circle)
        self.play(Create(center_circle), Write(center_text), run_time=1)
        self.wait(0.5)

        branches = {branches_repr}
        n = min(len(branches), 6)
        angles = [i * 2 * np.pi / n for i in range(n)]

        for i, (branch, angle) in enumerate(zip(branches[:n], angles)):
            direction = np.array([np.cos(angle), np.sin(angle), 0])
            pos = direction * 3

            branch_text = Text(branch[:25], font_size=22, color="{text_color}")
            branch_box = RoundedRectangle(
                corner_radius=0.15,
                width=max(branch_text.width + 0.4, 2),
                height=0.6,
                color="{info_color}",
                fill_opacity=0.1,
            ).move_to(pos)
            branch_text.move_to(branch_box)

            line = Line(
                center_circle.point_at_angle(angle * 180 / np.pi * DEGREES if hasattr(angle, '__float__') else angle),
                branch_box.get_center() - direction * 0.5,
                color=GREY_B,
            )

            self.play(
                Create(line),
                FadeIn(branch_box),
                Write(branch_text),
                run_time=0.7,
            )
            self.wait(0.4)

        self.wait(2)
'''

# ── Template: Venn Comparison ────────────────────────────────────────

VENN_TEMPLATE = '''
from manim import *

class VennComparison(Scene):
    """Two overlapping circles comparing concepts with shared traits."""

    def construct(self):
        title = Text("{title}", font_size=42, color="{text_color}").to_edge(UP, buff=0.4)
        self.play(Write(title), run_time=1)

        left_circle = Circle(radius=2.2, color="{accent_color}", fill_opacity=0.08).shift(LEFT * 1.3)
        right_circle = Circle(radius=2.2, color="{info_color}", fill_opacity=0.08).shift(RIGHT * 1.3)
        self.play(Create(left_circle), Create(right_circle), run_time=1)

        left_label = Text("{left_label}", font_size=28, color="{accent_color}").next_to(left_circle, UP)
        right_label = Text("{right_label}", font_size=28, color="{info_color}").next_to(right_circle, UP)
        self.play(Write(left_label), Write(right_label), run_time=0.6)

        # Left-only items
        left_items = {left_items_repr}
        for i, item in enumerate(left_items[:3]):
            t = Text(item[:25], font_size=18, color="{text_color}")
            t.move_to(LEFT * 2.8 + UP * (0.5 - i * 0.6))
            self.play(FadeIn(t, shift=LEFT * 0.2), run_time=0.4)

        # Shared items (center)
        shared_items = {shared_items_repr}
        for i, item in enumerate(shared_items[:3]):
            t = Text(item[:25], font_size=18, color="{success_color}")
            t.move_to(UP * (0.5 - i * 0.6))
            self.play(FadeIn(t, scale=1.2), run_time=0.4)

        # Right-only items
        right_items = {right_items_repr}
        for i, item in enumerate(right_items[:3]):
            t = Text(item[:25], font_size=18, color="{text_color}")
            t.move_to(RIGHT * 2.8 + UP * (0.5 - i * 0.6))
            self.play(FadeIn(t, shift=RIGHT * 0.2), run_time=0.4)

        self.wait(2)
'''

# ── Template: Vocabulary Card ────────────────────────────────────────

VOCAB_CARD_TEMPLATE = '''
from manim import *

class VocabularyCard(Scene):
    """Term-definition cards with flip animation, one at a time."""

    def construct(self):
        title = Text("{title}", font_size=42, color="{text_color}").to_edge(UP, buff=0.4)
        self.play(Write(title), run_time=1)
        self.wait(0.3)

        vocab = {vocab_repr}

        for term, definition in vocab[:6]:
            # Show term
            term_text = Text(term, font_size=36, color="{accent_color}", weight=BOLD)
            card = RoundedRectangle(
                corner_radius=0.3, width=8, height=3.5,
                color="{info_color}", fill_opacity=0.05,
            )
            term_text.move_to(card)
            self.play(FadeIn(card), Write(term_text), run_time=0.8)
            self.wait(1.5)

            # Flip to definition
            def_text = Text(
                definition[:80],
                font_size=24,
                color="{text_color}",
                line_spacing=1.3,
            ).move_to(card)

            self.play(
                term_text.animate.scale(0.01),
                run_time=0.3,
            )
            self.play(
                FadeIn(def_text, scale=0.01),
                run_time=0.3,
            )
            self.wait(2)

            # Clear for next card
            self.play(FadeOut(card), FadeOut(def_text), run_time=0.4)
            self.wait(0.3)

        self.wait(1)
'''

# ── Template registry ────────────────────────────────────────────────

TEMPLATES = {
    "timeline": TIMELINE_TEMPLATE,
    "diagram": CAUSE_EFFECT_TEMPLATE,
    "process": PROCESS_FLOW_TEMPLATE,
    "concept": CONCEPT_MAP_TEMPLATE,
    "comparison": VENN_TEMPLATE,
    "vocabulary": VOCAB_CARD_TEMPLATE,
}


def get_template(animation_type: str) -> str | None:
    """Get a Manim scene template by animation type."""
    return TEMPLATES.get(animation_type)


def list_templates() -> list[str]:
    """List available animation template types."""
    return list(TEMPLATES.keys())
