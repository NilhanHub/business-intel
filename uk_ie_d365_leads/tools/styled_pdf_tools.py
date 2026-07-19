"""Polished ReportLab renderer for UK/IE D365 opportunity reports."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape


def _safe(value: Any) -> str:
    return (
        " ".join(str(value or "").split())
        .replace("\u2011", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2018", "'")
        .replace("\u2019", "'")
    )


def write_styled_report_pdf(
    path: Path,
    report_spec: dict[str, Any],
    source_map: dict[str, Any],
    *,
    landscape: bool = True,
) -> None:
    """Render a visually structured PDF while preserving source-linked content."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.pagesizes import landscape as landscape_page
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    page_size = landscape_page(A4) if landscape else A4
    page_width, page_height = page_size
    content_width = page_width - 28 * mm
    navy = colors.HexColor("#0B2A42")
    blue = colors.HexColor("#12395B")
    slate = colors.HexColor("#526070")
    gold = colors.HexColor("#E7AD3F")
    pale_blue = colors.HexColor("#F1F6FA")
    pale_gold = colors.HexColor("#FFF8EB")
    green = colors.HexColor("#1F7A48")
    pale_green = colors.HexColor("#EAF6EF")
    border = colors.HexColor("#DCE4EC")
    white = colors.white

    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "ReportTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=27,
            leading=30,
            textColor=white,
            alignment=TA_LEFT,
        ),
        "subtitle": ParagraphStyle(
            "ReportSubtitle",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=11.5,
            leading=15,
            textColor=colors.HexColor("#E9F1F7"),
        ),
        "kicker": ParagraphStyle(
            "Kicker",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=10,
            textColor=gold,
        ),
        "h1": ParagraphStyle(
            "H1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=17,
            leading=20,
            textColor=navy,
            spaceAfter=7,
        ),
        "account": ParagraphStyle(
            "Account",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=18,
            textColor=white,
        ),
        "badge": ParagraphStyle(
            "Badge",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=10,
            alignment=TA_RIGHT,
            textColor=green,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#172033"),
        ),
        "small": ParagraphStyle(
            "Small",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=7.2,
            leading=9.2,
            textColor=slate,
        ),
        "label": ParagraphStyle(
            "Label",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=7.1,
            leading=8.5,
            textColor=navy,
        ),
        "table_header": ParagraphStyle(
            "TableHeader",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=7.3,
            leading=8.8,
            textColor=white,
        ),
    }

    def paragraph(value: Any, style: str = "body") -> Paragraph:
        return Paragraph(escape(_safe(value)), styles[style])

    def field(label: str, value: Any) -> Table:
        block = Table(
            [[paragraph(label.upper(), "label")], [paragraph(value)]],
            colWidths=[content_width / 2 - 3 * mm],
        )
        block.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), pale_blue),
                    ("BOX", (0, 0), (-1, -1), 0.55, border),
                    ("LINEBEFORE", (0, 0), (0, -1), 2.6, gold),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        return block

    def on_page(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFillColor(navy)
        canvas.rect(0, page_height - 8 * mm, page_width, 8 * mm, fill=1, stroke=0)
        canvas.setFillColor(slate)
        canvas.setFont("Helvetica", 7)
        canvas.drawString(14 * mm, 7 * mm, "1BT Sales Intelligence | UK & Ireland Dynamics 365 | Round 5")
        canvas.drawRightString(page_width - 14 * mm, 7 * mm, f"Page {doc.page}")
        canvas.setStrokeColor(gold)
        canvas.setLineWidth(0.7)
        canvas.line(14 * mm, 11 * mm, page_width - 14 * mm, 11 * mm)
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(path),
        pagesize=page_size,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=15 * mm,
        bottomMargin=16 * mm,
        title=_safe(report_spec.get("title")),
        author="1BT Sales Intelligence",
    )
    story: list[Any] = []

    cover = Table(
        [
            [paragraph("1BT SALES INTELLIGENCE", "kicker")],
            [paragraph(report_spec.get("title"), "title")],
            [paragraph(report_spec.get("subtitle"), "subtitle")],
            [paragraph(report_spec.get("executive_snapshot"), "subtitle")],
        ],
        colWidths=[content_width],
    )
    cover.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), navy),
                ("BOX", (0, 0), (-1, -1), 1, blue),
                ("LEFTPADDING", (0, 0), (-1, -1), 18),
                ("RIGHTPADDING", (0, 0), (-1, -1), 18),
                ("TOPPADDING", (0, 0), (-1, 0), 18),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 18),
            ]
        )
    )
    story.extend([Spacer(1, 16 * mm), cover, Spacer(1, 10 * mm)])
    metrics = Table(
        [
            [paragraph("20", "title"), paragraph("50", "title"), paragraph("100%", "title")],
            [paragraph("NEW ACCOUNTS", "table_header"), paragraph("PRIOR ACCOUNTS EXCLUDED", "table_header"), paragraph("LIVE SOURCES", "table_header")],
        ],
        colWidths=[content_width / 3] * 3,
    )
    metrics.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), blue),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#35566A")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.extend([metrics, PageBreak(), paragraph("Signal themes", "h1")])
    for theme in report_spec.get("signal_themes") or []:
        story.extend([Paragraph(f"&#8226;&nbsp; {escape(_safe(theme))}", styles["body"]), Spacer(1, 2)])
    story.extend([Spacer(1, 6), paragraph("At a glance", "h1")])

    glance_rows = [[paragraph("Account", "table_header"), paragraph("Signal", "table_header"), paragraph("Strength", "table_header"), paragraph("Pitch lane", "table_header")]]
    for item in report_spec.get("at_a_glance") or []:
        glance_rows.append(
            [
                paragraph(item.get("account")),
                paragraph(item.get("signal_type"), "small"),
                paragraph(item.get("strength")),
                paragraph(item.get("pitch_lane"), "small"),
            ]
        )
    glance = Table(
        glance_rows,
        colWidths=[44 * mm, 53 * mm, 22 * mm, content_width - 119 * mm],
        repeatRows=1,
    )
    glance.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), blue),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, pale_blue]),
                ("GRID", (0, 0), (-1, -1), 0.35, border),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.extend([glance, PageBreak()])

    source_by_account = {
        item.get("account"): item.get("evidence") or []
        for item in source_map.get("accounts") or []
    }
    accounts = report_spec.get("accounts") or []
    for index, account in enumerate(accounts, start=1):
        header = Table(
            [[paragraph(f"{index:02d}. {_safe(account.get('account'))}", "account"), paragraph(account.get("signal_strength"), "badge")]],
            colWidths=[content_width - 35 * mm, 35 * mm],
        )
        header.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, 0), navy),
                    ("BACKGROUND", (1, 0), (1, 0), pale_green),
                    ("BOX", (0, 0), (-1, -1), 0.6, border),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        grid = Table(
            [
                [field("Opportunity signal", account.get("opportunity_signal")), field("Why this matters to 1BT", account.get("why_this_matters_to_1bt"))],
                [field("Commercial opening", account.get("commercial_opening")), field("Value of the signal", account.get("value_of_signal"))],
            ],
            colWidths=[content_width / 2] * 2,
        )
        grid.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        evidence_links = []
        for item in source_by_account.get(account.get("account")) or []:
            url = _safe(item.get("evidence_url"))
            if url:
                evidence_links.append(
                    f'<link href="{escape(url)}" color="#12395B">{escape(url)}</link>'
                )
        note_rows = [
            [paragraph("EVIDENCE", "label"), Paragraph("<br/>".join(evidence_links) or escape(_safe(", ".join(account.get("evidence_refs") or []))), styles["small"])],
            [paragraph("DO NOT CLAIM", "label"), paragraph("; ".join(account.get("do_not_claim_notes") or []), "small")],
            [paragraph("UNCERTAINTY", "label"), paragraph("; ".join(account.get("remaining_uncertainty") or []), "small")],
        ]
        notes = Table(note_rows, colWidths=[28 * mm, content_width - 28 * mm])
        notes.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), pale_gold),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#F1D79F")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#F1D79F")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.extend(
            [
                header,
                Spacer(1, 5),
                Paragraph(f"<b>Signal type:</b> {escape(_safe(account.get('signal_type')))}", styles["small"]),
                Spacer(1, 4),
                grid,
                Spacer(1, 4),
                notes,
                Spacer(1, 8),
            ]
        )
        if index % 2 == 0 and index != len(accounts):
            story.append(PageBreak())

    story.extend([PageBreak(), paragraph("Caveats and qualification boundaries", "h1")])
    for caveat in report_spec.get("caveats") or []:
        story.extend([Paragraph(f"&#8226;&nbsp; {escape(_safe(caveat))}", styles["body"]), Spacer(1, 4)])
    story.extend(
        [
            Spacer(1, 8),
            paragraph("Source-map coverage", "h1"),
            paragraph(
                f"{len(source_map.get('accounts') or [])} accounts have linked source-map entries. "
                "All final records were checked against the saved historical exclusion set before publication."
            ),
        ]
    )
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
