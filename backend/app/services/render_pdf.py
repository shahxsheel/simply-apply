"""Single-page PDF renderer using a Jake's Resume-inspired layout.

The typography and structure follow Jake Gutierrez's MIT-licensed LaTeX template:
compact serif text, a centered contact header, ruled uppercase sections, paired
role/date lines, and tight bullets. ``KeepInFrame(mode="shrink")`` guarantees that the
human-facing PDF remains one page even when content runs slightly long.

Source inspiration: https://github.com/jakegut/resume (MIT License).
"""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape as _xml_escape

from reportlab.lib.colors import black
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    KeepInFrame,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.flowables import _listWrapOn

from app.schemas import StructuredResume

BODY_FONT = "Times-Roman"
BOLD_FONT = "Times-Bold"
ITALIC_FONT = "Times-Italic"

LEFT_MARGIN = RIGHT_MARGIN = 0.5 * inch
TOP_MARGIN = BOTTOM_MARGIN = 0.45 * inch
_PAGE_W, _PAGE_H = LETTER
FRAME_W = _PAGE_W - LEFT_MARGIN - RIGHT_MARGIN
FRAME_H = _PAGE_H - TOP_MARGIN - BOTTOM_MARGIN


class PDFRenderError(RuntimeError):
    """ReportLab produced no usable PDF."""


class _VerticallyFilledFrame(KeepInFrame):
    """Use the full page by spreading spare height uniformly between content blocks."""

    def __init__(self, width: float, height: float, content: list) -> None:
        self._base_content = list(content)
        super().__init__(
            width,
            height,
            content=self._base_content,
            mode="shrink",
            hAlign="LEFT",
            vAlign="TOP",
        )

    def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
        max_width = min(float(self.maxWidth or avail_width), avail_width)
        max_height = min(float(self.maxHeight or avail_height), avail_height)
        _, natural_height = _listWrapOn(
            self._base_content,
            max_width,
            self.canv,
            fakeWidth=self.fakeWidth,
        )
        gaps = len(self._base_content) - 1
        if gaps > 0 and natural_height < max_height:
            gap_height = (max_height - natural_height) / gaps
            filled: list = []
            for index, flowable in enumerate(self._base_content):
                if index:
                    filled.append(Spacer(1, gap_height))
                filled.append(flowable)
            self._content = filled
        else:
            self._content = list(self._base_content)
        return super().wrap(avail_width, avail_height)


_NAME = ParagraphStyle(
    "Name",
    fontName=BOLD_FONT,
    fontSize=22,
    leading=23,
    alignment=TA_CENTER,
    textColor=black,
    spaceAfter=1,
)
_CONTACT = ParagraphStyle(
    "Contact",
    fontName=BODY_FONT,
    fontSize=9,
    leading=10.5,
    alignment=TA_CENTER,
    textColor=black,
    spaceAfter=3,
)
_HEADING = ParagraphStyle(
    "Heading",
    fontName=BOLD_FONT,
    fontSize=11.5,
    leading=12,
    textColor=black,
    spaceBefore=5,
    spaceAfter=0,
)
_BODY = ParagraphStyle(
    "Body",
    fontName=BODY_FONT,
    fontSize=9.5,
    leading=11,
    textColor=black,
    spaceAfter=1,
)
_LEFT_BOLD = ParagraphStyle(
    "LeftBold", parent=_BODY, fontName=BOLD_FONT, spaceAfter=0
)
_LEFT_ITALIC = ParagraphStyle(
    "LeftItalic", parent=_BODY, fontName=ITALIC_FONT, spaceAfter=0
)
_RIGHT = ParagraphStyle("Right", parent=_BODY, alignment=2, spaceAfter=0)
_RIGHT_ITALIC = ParagraphStyle(
    "RightItalic", parent=_RIGHT, fontName=ITALIC_FONT
)
_BULLET = ParagraphStyle(
    "Bullet",
    parent=_BODY,
    leftIndent=11,
    firstLineIndent=-7,
    bulletIndent=0,
    spaceAfter=0.5,
)


def _esc(value: object) -> str:
    return _xml_escape("" if value is None else str(value))


def _date_range(start: str, end: str) -> str:
    if start and end:
        return f"{start} - {end}"
    return start or end or ""


def _contact_line(resume: StructuredResume) -> str:
    basics = resume.basics
    location = ", ".join(
        value for value in (basics.location.city, basics.location.region) if value
    )
    pieces = [basics.phone, basics.email, location, basics.url]
    pieces += [profile.url for profile in basics.profiles if profile.url]
    return " | ".join(piece for piece in pieces if piece)


def _heading(text: str) -> list:
    return [
        Paragraph(_esc(text.upper()), _HEADING),
        HRFlowable(
            width="100%",
            thickness=0.75,
            color=black,
            spaceBefore=0,
            spaceAfter=2,
        ),
    ]


def _paired_line(
    left: str,
    right: str = "",
    *,
    italic: bool = False,
    gap_before: float = 0,
) -> list:
    left_style = _LEFT_ITALIC if italic else _LEFT_BOLD
    right_style = _RIGHT_ITALIC if italic else _RIGHT
    table = Table(
        [[Paragraph(_esc(left), left_style), Paragraph(_esc(right), right_style)]],
        colWidths=[FRAME_W * 0.72, FRAME_W * 0.28],
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), gap_before),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return [table]


def _flowables(resume: StructuredResume) -> list:
    story: list = [Paragraph(_esc(resume.basics.name), _NAME)]
    contact = _contact_line(resume)
    if contact:
        story.append(Paragraph(_esc(contact), _CONTACT))

    if resume.basics.summary:
        story += _heading("Professional Summary")
        story.append(Paragraph(_esc(resume.basics.summary), _BODY))

    if resume.work:
        story += _heading("Experience")
        for job in resume.work:
            story += _paired_line(
                job.position or job.name,
                _date_range(job.startDate, job.endDate),
                gap_before=1.5,
            )
            employer = job.name if job.position else ""
            if employer or job.location:
                story += _paired_line(employer, job.location, italic=True)
            if job.summary:
                story.append(Paragraph(_esc(job.summary), _BODY))
            for highlight in job.highlights:
                story.append(Paragraph(_esc(highlight), _BULLET, bulletText="-"))

    if resume.education:
        story += _heading("Education")
        for education in resume.education:
            story += _paired_line(
                education.institution,
                _date_range(education.startDate, education.endDate),
                gap_before=1.5,
            )
            degree = " in ".join(
                part for part in (education.studyType, education.area) if part
            )
            detail = " | ".join(
                part
                for part in (
                    degree,
                    f"GPA: {education.score}" if education.score else "",
                )
                if part
            )
            if detail:
                story.append(Paragraph(f"<i>{_esc(detail)}</i>", _BODY))
            if education.courses:
                story.append(
                    Paragraph(
                        f"Relevant Coursework: {_esc(', '.join(education.courses))}",
                        _BODY,
                    )
                )

    if resume.projects:
        story += _heading("Projects")
        for project in resume.projects:
            technologies = ", ".join(project.keywords)
            left = project.name
            if technologies:
                left = f"{left} | {technologies}" if left else technologies
            story += _paired_line(
                left,
                _date_range(project.startDate, project.endDate),
                gap_before=1.5,
            )
            if project.description:
                story.append(Paragraph(_esc(project.description), _BODY))
            for highlight in project.highlights:
                story.append(Paragraph(_esc(highlight), _BULLET, bulletText="-"))

    if resume.skills:
        story += _heading("Technical Skills")
        for skill in resume.skills:
            if skill.name and skill.keywords:
                text = f"<b>{_esc(skill.name)}:</b> {_esc(', '.join(skill.keywords))}"
            elif skill.name:
                text = _esc(skill.name)
            elif skill.keywords:
                text = _esc(", ".join(skill.keywords))
            else:
                continue
            story.append(Paragraph(text, _BODY))

    return story


def render_pdf(resume: StructuredResume, output_path: Path) -> Path:
    """Render ``resume`` to an exact one-page PDF at ``output_path``."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    story = _flowables(resume) or [Spacer(1, 1)]
    fitted = _VerticallyFilledFrame(FRAME_W, FRAME_H, story)
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=LETTER,
        leftMargin=LEFT_MARGIN,
        rightMargin=RIGHT_MARGIN,
        topMargin=TOP_MARGIN,
        bottomMargin=BOTTOM_MARGIN,
        title=f"{resume.basics.name} - Resume" if resume.basics.name else "Resume",
    )
    try:
        doc.build([fitted])
    except Exception as exc:
        raise PDFRenderError(f"PDF generation failed: {exc}") from exc
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise PDFRenderError("PDF generation produced an empty file.")
    return output_path
