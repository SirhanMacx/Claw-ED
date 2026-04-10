"""Generation quality report — accumulated throughout the pipeline, surfaced to teacher."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GenerationReport(BaseModel):
    warnings: list[str] = Field(default_factory=list)
    quality_review_passed: bool | None = None
    quality_review_issues: list[str] = Field(default_factory=list)
    voice_check_passed: bool | None = None
    voice_check_issues: list[str] = Field(default_factory=list)
    delegation_violations: list[str] = Field(default_factory=list)
    teacher_materials_found: int = 0
    images_embedded: int = 0
    images_failed: int = 0
    alignment_score: float = 0.0
    completeness_errors: list[str] = Field(default_factory=list)

    def summary(self) -> str:
        lines = []
        if self.teacher_materials_found:
            lines.append(f"Referenced {self.teacher_materials_found} of your existing materials")
        if self.images_embedded:
            lines.append(f"Embedded {self.images_embedded} images")
        if self.images_failed:
            lines.append(f"Could not fetch {self.images_failed} images")
        if self.alignment_score:
            lines.append(f"Content alignment: {self.alignment_score:.0f}%")
        if self.quality_review_passed is False:
            for issue in self.quality_review_issues[:3]:
                lines.append(f"Quality note: {issue}")
        if self.voice_check_passed is False:
            for issue in self.voice_check_issues[:3]:
                lines.append(f"Voice note: {issue}")
        if self.delegation_violations:
            for v in self.delegation_violations[:3]:
                lines.append(f"Warning: {v}")
        if self.completeness_errors:
            for e in self.completeness_errors[:3]:
                lines.append(f"Issue: {e}")
        if self.warnings:
            for w in self.warnings[:3]:
                lines.append(f"Note: {w}")
        return "\n".join(lines) if lines else ""
