"""
PDF generation for AngebotPlus B2B offers, using ReportLab.
Layout follows a DIN 5008-inspired German business document structure.
"""
from datetime import datetime, timedelta
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    NextPageTemplate,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

NAVY = colors.HexColor("#0F172A")
EMERALD = colors.HexColor("#059669")
GRAY_BORDER = colors.HexColor("#E2E8F0")
GRAY_TEXT = colors.HexColor("#64748B")
COOL_GRAY = colors.HexColor("#F8FAFC")

UNIT_LABELS = {"Std": "Std.", "Pauschal": "Pauschal", "m2": "m²", "Stk": "Stk."}

DOC_TYPE_TEXTS = {
    "angebot": {
        "title": "Angebot",
        "number_label": "Angebotsnummer",
        "meta3_label": "Gültig bis",
        "intro": "Sehr geehrte Damen und Herren,<br/>vielen Dank für Ihre Anfrage. Wir unterbreiten Ihnen gerne folgendes Angebot:",
        "closing": lambda d: f"Zahlbar innerhalb von 14 Tagen ohne Abzug. Dieses Angebot ist gültig bis {d}.<br/>Wir freuen uns auf Ihren Auftrag.",
    },
    "rechnung": {
        "title": "Rechnung",
        "number_label": "Rechnungsnummer",
        "meta3_label": "Zahlbar bis",
        "intro": "Sehr geehrte Damen und Herren,<br/>für die erbrachten Leistungen stellen wir Ihnen wie folgt in Rechnung:",
        "closing": lambda d: f"Bitte überweisen Sie den Rechnungsbetrag bis zum {d} unter Angabe der Rechnungsnummer auf u. g. Konto.<br/>Vielen Dank für Ihr Vertrauen.",
    },
    "auftragsbestaetigung": {
        "title": "Auftragsbestätigung",
        "number_label": "Auftragsnummer",
        "meta3_label": "Ausführung bis",
        "intro": "Sehr geehrte Damen und Herren,<br/>hiermit bestätigen wir den folgenden Auftrag gemäß Ihrer Bestellung:",
        "closing": lambda d: f"Die Ausführung erfolgt voraussichtlich bis zum {d}.<br/>Wir freuen uns auf die Zusammenarbeit.",
    },
}


def fmt_eur(value: float) -> str:
    s = f"{value:,.2f}"
    s = s.replace(",", "§").replace(".", ",").replace("§", ".")
    return f"{s} €"


def fmt_qty(value: float) -> str:
    if float(value).is_integer():
        s = f"{int(value):,}"
    else:
        s = f"{value:,.2f}".rstrip("0").rstrip(".")
    return s.replace(",", ".")


def fmt_date_de(iso_str: str) -> str:
    try:
        d = datetime.strptime(iso_str[:10], "%Y-%m-%d")
        return d.strftime("%d.%m.%Y")
    except ValueError:
        return iso_str


def generate_offer_pdf(offer: dict) -> bytes:
    doc_texts = DOC_TYPE_TEXTS.get(offer.get("document_type", "angebot"), DOC_TYPE_TEXTS["angebot"])

    buf = BytesIO()
    doc = BaseDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2.5 * cm,
        rightMargin=2 * cm,
        topMargin=1.5 * cm,
        bottomMargin=2 * cm,
        title=f"{doc_texts['title']} {offer['offer_number']}",
    )
    frame = Frame(
        doc.leftMargin, doc.bottomMargin,
        doc.width, doc.height,
        id="normal",
    )

    styles = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8, textColor=GRAY_TEXT, leading=11)
    normal = ParagraphStyle("normalX", parent=styles["Normal"], fontSize=9.5, leading=13.5)
    label = ParagraphStyle("label", parent=styles["Normal"], fontSize=7.5, textColor=GRAY_TEXT, leading=10)
    h1 = ParagraphStyle("h1", parent=styles["Normal"], fontSize=22, textColor=NAVY, leading=26, spaceAfter=2, fontName="Helvetica-Bold")
    provider_small = ParagraphStyle("provider_small", parent=styles["Normal"], fontSize=7.5, textColor=GRAY_TEXT, leading=10)

    story = []

    provider = offer["provider"]
    client = offer["client"]
    items = offer["items"]

    # --- Sender line (DIN 5008 window position) + meta box ---
    sender_line = Paragraph(
        f"{provider['name']} · {provider['address'].replace(chr(10), ', ')}",
        provider_small,
    )

    meta_data = [
        [Paragraph(doc_texts["number_label"], label), Paragraph(offer["offer_number"], normal)],
        [Paragraph("Datum", label), Paragraph(fmt_date_de(offer["offer_date"]), normal)],
        [Paragraph(doc_texts["meta3_label"], label), Paragraph(_valid_until(offer), normal)],
    ]
    meta_table = Table(meta_data, colWidths=[3.1 * cm, 3.4 * cm])
    meta_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))

    header_row = Table(
        [[sender_line, meta_table]],
        colWidths=[doc.width - 6.5 * cm, 6.5 * cm],
    )
    header_row.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
    ]))
    story.append(header_row)
    story.append(Spacer(1, 1.1 * cm))

    # --- Recipient address block (window position) ---
    client_lines = [client["name"]]
    if client.get("company"):
        client_lines.append(client["company"])
    client_lines += [l for l in client["address"].split("\n") if l.strip()]
    client_block = Paragraph("<br/>".join(client_lines), normal)
    story.append(client_block)
    story.append(Spacer(1, 1.3 * cm))

    # --- Title ---
    story.append(Paragraph(doc_texts["title"], h1))
    story.append(Paragraph(doc_texts["intro"], normal))
    story.append(Spacer(1, 0.6 * cm))

    # --- Items table ---
    header = ["Pos.", "Beschreibung", "Menge", "Einheit", "Einzelpreis", "Gesamtpreis"]
    table_data = [header]
    for idx, item in enumerate(items, start=1):
        line_total = item["quantity"] * item["unit_price"]
        table_data.append([
            str(idx),
            Paragraph(item["description"], normal),
            fmt_qty(item["quantity"]),
            UNIT_LABELS.get(item["unit"], item["unit"]),
            fmt_eur(item["unit_price"]),
            fmt_eur(line_total),
        ])

    col_widths = [1.2 * cm, doc.width - (1.2 + 2.2 + 2.2 + 3.1 + 3.1) * cm, 2.2 * cm, 2.2 * cm, 3.1 * cm, 3.1 * cm]
    items_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8.5),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, 0), 0.75, NAVY),
        ("LINEBELOW", (0, 1), (-1, -1), 0.5, GRAY_BORDER),
    ]
    for i in range(1, len(table_data)):
        if i % 2 == 0:
            style_cmds.append(("BACKGROUND", (0, i), (-1, i), COOL_GRAY))
    items_table.setStyle(TableStyle(style_cmds))
    story.append(items_table)
    story.append(Spacer(1, 0.5 * cm))

    # --- Totals block ---
    totals_rows = [["Nettobetrag", fmt_eur(offer["subtotal_net"])]]
    if offer["discount_percent"]:
        totals_rows.append([f"Rabatt ({offer['discount_percent']:g} %)", f"− {fmt_eur(offer['discount_amount'])}"])
        totals_rows.append(["Zwischensumme", fmt_eur(offer["net_after_discount"])])
    if offer["vat_rate"] > 0:
        totals_rows.append([f"zzgl. MwSt. ({offer['vat_rate']:g} %)", fmt_eur(offer["vat_amount"])])
    else:
        totals_rows.append(["Umsatzsteuer", "0,00 €"])
    totals_rows.append(["Gesamtbetrag brutto", fmt_eur(offer["gross_total"])])

    totals_table = Table(totals_rows, colWidths=[doc.width - 5.5 * cm, 5.5 * cm])
    t_style = [
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TEXTCOLOR", (0, 0), (-1, -2), NAVY),
        ("LINEABOVE", (0, -1), (-1, -1), 1, NAVY),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, -1), (-1, -1), 12),
        ("TOPPADDING", (0, -1), (-1, -1), 7),
    ]
    totals_table.setStyle(TableStyle(t_style))
    story.append(totals_table)

    if offer["vat_rate"] == 0:
        story.append(Spacer(1, 0.3 * cm))
        story.append(Paragraph(
            "Gemäß § 19 UStG wird keine Umsatzsteuer berechnet (Kleinunternehmerregelung).",
            small,
        ))

    story.append(Spacer(1, 1 * cm))
    story.append(Paragraph(doc_texts["closing"](_valid_until(offer)), normal))

    def draw_footer(canvas, _doc):
        canvas.saveState()
        y = 1.4 * cm
        canvas.setStrokeColor(GRAY_BORDER)
        canvas.setLineWidth(0.5)
        canvas.line(2.5 * cm, y + 0.9 * cm, A4[0] - 2 * cm, y + 0.9 * cm)

        canvas.setFont("Helvetica-Bold", 7.5)
        canvas.setFillColor(NAVY)
        canvas.drawString(2.5 * cm, y + 0.55 * cm, provider["name"])

        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(GRAY_TEXT)
        bank_line = f"IBAN: {provider.get('iban') or '–'}"
        tax_line = f"USt-IdNr./Steuernr.: {provider.get('tax_id') or '–'}"
        contact_line = f"E-Mail: {provider.get('email') or '–'}"
        canvas.drawString(2.5 * cm, y + 0.05 * cm, f"{tax_line}    {bank_line}    {contact_line}")

        canvas.setFont("Helvetica-Oblique", 7)
        canvas.setFillColor(GRAY_TEXT)
        canvas.drawString(
            2.5 * cm, y - 0.45 * cm,
            "Dies ist eine interaktive Demo-Anwendung zu Portfolio-Zwecken. Alle Angaben ohne Gewähr.",
        )

        canvas.setFont("Helvetica", 7)
        canvas.drawRightString(A4[0] - 2 * cm, y - 0.45 * cm, f"Seite {canvas.getPageNumber()}")
        canvas.restoreState()

    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=draw_footer)])
    doc.build(story)
    return buf.getvalue()


def _valid_until(offer: dict) -> str:
    try:
        d = datetime.strptime(offer["offer_date"][:10], "%Y-%m-%d")
        until = d + timedelta(days=int(offer["validity_days"]))
        return until.strftime("%d.%m.%Y")
    except (ValueError, KeyError):
        return "–"
