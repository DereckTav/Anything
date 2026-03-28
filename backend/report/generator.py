import os
import tempfile
import base64
from datetime import datetime

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image,
    HRFlowable,
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER

from config import PDF_MAX_STILLS

# Color palette matching the frontend
PRIMARY = HexColor("#f1dfbe")
BACKGROUND = HexColor("#121316")
SURFACE = HexColor("#1f1f23")
ON_SURFACE = HexColor("#e3e2e6")
ON_SURFACE_VARIANT = HexColor("#cec5b9")
ERROR = HexColor("#ffb4ab")
TEXT_DARK = HexColor("#2a2a2a")


def generate_pdf(session_data: dict) -> str:
    """Generate a PDF report from session data.

    Args:
        session_data: dict with report, narrations, stills, start_time, report_id.

    Returns:
        Path to the generated PDF file.
    """
    report = session_data.get("report", {})
    report_id = session_data.get("report_id", "CS-0000")
    narrations = report.get("narrative", session_data.get("narrations", []))
    score = report.get("score", "N/A")
    verdict = report.get("verdict", "No verdict available.")
    stills = session_data.get("stills", [])[:PDF_MAX_STILLS]

    # Calculate session duration
    start_time = session_data.get("start_time", 0)
    duration_s = int(session_data.get("end_time", datetime.now().timestamp()) - start_time)
    duration_str = f"{duration_s // 60:02d}:{duration_s % 60:02d}"

    # Create temp file for PDF
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp_path = tmp.name
    tmp.close()

    doc = SimpleDocTemplate(
        tmp_path,
        pagesize=letter,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
    )

    # Styles
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="ReportTitle",
        fontName="Helvetica-Bold",
        fontSize=24,
        textColor=TEXT_DARK,
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="ReportSubtitle",
        fontName="Helvetica",
        fontSize=10,
        textColor=HexColor("#666666"),
        spaceAfter=12,
    ))
    styles.add(ParagraphStyle(
        name="SectionHeader",
        fontName="Helvetica-Bold",
        fontSize=14,
        textColor=TEXT_DARK,
        spaceBefore=18,
        spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="NarrationTimestamp",
        fontName="Courier",
        fontSize=9,
        textColor=HexColor("#888888"),
    ))
    styles.add(ParagraphStyle(
        name="NarrationText",
        fontName="Helvetica",
        fontSize=10,
        textColor=TEXT_DARK,
        spaceAfter=8,
        leading=14,
    ))
    styles.add(ParagraphStyle(
        name="VerdictText",
        fontName="Helvetica-Oblique",
        fontSize=11,
        textColor=TEXT_DARK,
        spaceAfter=6,
        leading=15,
    ))
    styles.add(ParagraphStyle(
        name="ScoreText",
        fontName="Helvetica-Bold",
        fontSize=20,
        textColor=HexColor("#2a5a3a"),
        alignment=TA_CENTER,
    ))

    elements = []

    # Header
    elements.append(Paragraph("URBANLENS", styles["ReportTitle"]))
    elements.append(Paragraph("Urban Intelligence Report", styles["ReportSubtitle"]))
    elements.append(HRFlowable(width="100%", thickness=1, color=PRIMARY))
    elements.append(Spacer(1, 12))

    # Metadata
    meta_data = [
        ["Report ID", report_id],
        ["Date", datetime.now().strftime("%d %b %Y")],
        ["Session Duration", duration_str],
    ]
    meta_table = Table(meta_data, colWidths=[1.5 * inch, 4 * inch])
    meta_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Courier"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (0, -1), HexColor("#666666")),
        ("TEXTCOLOR", (1, 0), (1, -1), TEXT_DARK),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 16))

    # Narrative Log
    elements.append(Paragraph("Narrative Log", styles["SectionHeader"]))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=HexColor("#cccccc")))
    elements.append(Spacer(1, 8))

    for entry in narrations:
        ts = entry.get("timestamp", "00:00")
        text = entry.get("text", "")
        elements.append(Paragraph(f"[{ts}]", styles["NarrationTimestamp"]))
        elements.append(Paragraph(text, styles["NarrationText"]))

    if not narrations:
        elements.append(Paragraph("No narration entries recorded.", styles["NarrationText"]))

    elements.append(Spacer(1, 16))

    # Captured Stills
    if stills:
        elements.append(Paragraph("Captured Stills", styles["SectionHeader"]))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=HexColor("#cccccc")))
        elements.append(Spacer(1, 8))

        for i, still in enumerate(stills):
            img_b64 = still.get("image_b64", "")
            if img_b64:
                if "," in img_b64:
                    img_b64 = img_b64.split(",", 1)[1]
                try:
                    img_bytes = base64.b64decode(img_b64)
                    img_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
                    img_tmp.write(img_bytes)
                    img_tmp.close()
                    img = Image(img_tmp.name, width=4 * inch, height=2.5 * inch)
                    elements.append(img)
                    elements.append(Paragraph(
                        f"STILL_{i + 1:03d} — {still.get('timestamp', '00:00')}",
                        styles["NarrationTimestamp"],
                    ))
                    elements.append(Spacer(1, 8))
                except Exception:
                    pass

    # Summary Verdict
    elements.append(Spacer(1, 12))
    elements.append(Paragraph("Summary Verdict", styles["SectionHeader"]))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=HexColor("#cccccc")))
    elements.append(Spacer(1, 8))
    elements.append(Paragraph(f"{score}/10", styles["ScoreText"]))
    elements.append(Spacer(1, 8))
    elements.append(Paragraph(verdict, styles["VerdictText"]))

    # Footer
    elements.append(Spacer(1, 24))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=HexColor("#cccccc")))
    elements.append(Spacer(1, 6))
    elements.append(Paragraph(
        f"Generated by URBANLENS on {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        ParagraphStyle(
            name="Footer",
            fontName="Helvetica",
            fontSize=8,
            textColor=HexColor("#999999"),
            alignment=TA_CENTER,
        ),
    ))

    doc.build(elements)
    return tmp_path
