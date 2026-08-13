from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.graphics.barcode.code128 import Code128
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

LABEL_PAGE_SIZE = (40 * mm, 25 * mm)
LABEL_BAR_WIDTH = 0.25 * mm
LABEL_BAR_HEIGHT = 8.5 * mm
LABEL_QUIET_ZONE = 1.5 * mm


def money(cents: int) -> str:
    cents = int(cents)
    sign = "-" if cents < 0 else ""
    whole, fraction = divmod(abs(cents), 100)
    grouped = f"{whole:,}".replace(",", ".")
    return f"{sign}R$ {grouped},{fraction:02d}"


def _doc(path, title):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return SimpleDocTemplate(
        str(path),
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=title,
    )


def _styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="Right", parent=styles["BodyText"], alignment=TA_RIGHT
        )
    )
    styles.add(
        ParagraphStyle(
            name="TableCell",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=9,
            leading=11,
        )
    )
    return styles


def _table(data, widths):
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E78")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#B8C4CE")),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#F4F7F9")],
                ),
                ("ALIGN", (-1, 1), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def product_pdf(path, products):
    path = Path(path)
    styles = _styles()
    story = [
        Paragraph("Lista de Produtos", styles["Title"]),
        Paragraph(
            f"Emitido em {datetime.now():%d/%m/%Y %H:%M}", styles["BodyText"]
        ),
        Spacer(1, 7 * mm),
    ]
    data = [["Produto", "Preço"]] + [
        [Paragraph(escape(str(product["name"])), styles["TableCell"]), money(product["price_cents"])]
        for product in products
    ]
    story += [
        _table(data, [135 * mm, 45 * mm]),
        Spacer(1, 5 * mm),
        Paragraph(
            f"Total de produtos cadastrados: <b>{len(products)}</b>",
            styles["Right"],
        ),
    ]
    _doc(path, "Lista de Produtos").build(story)
    return path


def revenue_pdf(path, rows, start, end, client_label):
    path = Path(path)
    styles = _styles()
    total = sum(row["total_cents"] for row in rows)
    start_label = datetime.strptime(start, "%Y-%m-%d").strftime("%d/%m/%Y")
    end_label = datetime.strptime(end, "%Y-%m-%d").strftime("%d/%m/%Y")
    story = [
        Paragraph("Relatório de Faturamento Bruto", styles["Title"]),
        Paragraph(f"Período: {start_label} a {end_label}", styles["BodyText"]),
        Paragraph(f"Filtro: {escape(str(client_label))}", styles["BodyText"]),
        Spacer(1, 7 * mm),
    ]
    report_rows = [
        [
            Paragraph(escape(str(row["client_name"])), styles["TableCell"]),
            money(row["total_cents"]),
        ]
        for row in rows
    ] or [["Nenhuma venda no período", money(0)]]
    data = [["Cliente", "Valor comprado"], *report_rows]
    story += [
        _table(data, [130 * mm, 50 * mm]),
        Spacer(1, 6 * mm),
        Paragraph(f"TOTAL BRUTO: <b>{money(total)}</b>", styles["Right"]),
    ]
    _doc(path, "Relatório de Faturamento Bruto").build(story)
    return path


def _fit_label_name(name: str, maximum_width: float):
    text = " ".join(str(name).strip().upper().split()) or "PRODUTO"
    font_name = "Helvetica-Bold"
    font_size = 11.5
    while font_size > 6.5 and stringWidth(text, font_name, font_size) > maximum_width:
        font_size -= 0.25
    if stringWidth(text, font_name, font_size) <= maximum_width:
        return text, font_size

    suffix = "..."
    while text and stringWidth(text + suffix, font_name, font_size) > maximum_width:
        text = text[:-1]
    return (text.rstrip() + suffix) if text else "PRODUTO", font_size


def _label_barcode(value: str):
    barcode = str(value).strip()
    if not barcode or not barcode.isascii() or not barcode.isdigit():
        raise ValueError("O produto não possui um código numérico válido para a etiqueta.")
    return Code128(
        barcode,
        barWidth=LABEL_BAR_WIDTH,
        barHeight=LABEL_BAR_HEIGHT,
        humanReadable=False,
        quiet=True,
        lquiet=LABEL_QUIET_ZONE,
        rquiet=LABEL_QUIET_ZONE,
    )


def product_label_pdf(path, product):
    """Create one browser-printable thermal label on an exact 40 x 25 mm page."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    product_name = str(product["name"])
    barcode_value = str(product["barcode"])
    label = canvas.Canvas(str(path), pagesize=LABEL_PAGE_SIZE, pageCompression=1)
    label.setTitle(f"Etiqueta - {product_name}")
    page_width, _page_height = LABEL_PAGE_SIZE

    title, title_size = _fit_label_name(product_name, 34 * mm)
    label.setFillColor(colors.black)
    label.setFont("Helvetica-Bold", title_size)
    label.drawCentredString(page_width / 2, 19.0 * mm, title)

    barcode = _label_barcode(barcode_value)
    barcode.drawOn(label, (page_width - barcode.width) / 2, 5.0 * mm)

    label.setFont("Helvetica-Bold", 8.6)
    label.drawCentredString(page_width / 2, 1.55 * mm, barcode_value)
    label.showPage()
    label.save()
    return path
