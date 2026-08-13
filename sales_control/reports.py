from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

import reportlab
from reportlab.graphics.barcode.code128 import Code128
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

LABEL_PAGE_SIZE = (40 * mm, 25 * mm)
LABEL_BAR_WIDTH = 0.25 * mm
LABEL_BAR_HEIGHT = 8.5 * mm
LABEL_QUIET_ZONE = 1.5 * mm
MONTH_NAMES = (
    "JANEIRO",
    "FEVEREIRO",
    "MARÇO",
    "ABRIL",
    "MAIO",
    "JUNHO",
    "JULHO",
    "AGOSTO",
    "SETEMBRO",
    "OUTUBRO",
    "NOVEMBRO",
    "DEZEMBRO",
)
REPORT_FONT = "Vera"
REPORT_FONT_BOLD = "VeraBd"


def _register_pdf_fonts():
    font_dir = Path(reportlab.__file__).resolve().parent / "fonts"
    fonts = {
        REPORT_FONT: font_dir / "Vera.ttf",
        REPORT_FONT_BOLD: font_dir / "VeraBd.ttf",
        "VeraIt": font_dir / "VeraIt.ttf",
        "VeraBI": font_dir / "VeraBI.ttf",
    }
    for name, path in fonts.items():
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, path))
    pdfmetrics.registerFontFamily(
        REPORT_FONT,
        normal=REPORT_FONT,
        bold=REPORT_FONT_BOLD,
        italic="VeraIt",
        boldItalic="VeraBI",
    )


_register_pdf_fonts()


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
    styles["Normal"].fontName = REPORT_FONT
    styles["BodyText"].fontName = REPORT_FONT
    styles["Title"].fontName = REPORT_FONT_BOLD
    styles.add(
        ParagraphStyle(
            name="Right", parent=styles["BodyText"], alignment=TA_RIGHT
        )
    )
    styles.add(
        ParagraphStyle(
            name="TableCell",
            parent=styles["BodyText"],
            fontName=REPORT_FONT,
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
                ("FONTNAME", (0, 0), (-1, 0), REPORT_FONT_BOLD),
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


def _report_period(start, end):
    start_date = datetime.strptime(start, "%Y-%m-%d").date()
    end_date = datetime.strptime(end, "%Y-%m-%d").date()
    start_month = MONTH_NAMES[start_date.month - 1]
    end_month = MONTH_NAMES[end_date.month - 1]
    if (start_date.year, start_date.month) == (end_date.year, end_date.month):
        return start_month
    if start_date.year == end_date.year:
        return f"{start_month} A {end_month}"
    return f"{start_month}/{start_date.year} A {end_month}/{end_date.year}"


def revenue_pdf(path, rows, start, end):
    path = Path(path)
    styles = _styles()
    total = sum(row["total_cents"] for row in rows)
    story = [
        Paragraph("Relatório de Faturamento Bruto", styles["Title"]),
        Paragraph(f"Período: {_report_period(start, end)}", styles["BodyText"]),
        Spacer(1, 7 * mm),
    ]
    report_rows = [
        [
            Paragraph(escape(str(row["client_name"])), styles["TableCell"]),
            str(row["product_count"]),
            money(row["total_cents"]),
        ]
        for row in rows
    ] or [["Nenhuma venda no período", "0", money(0)]]
    data = [["Cliente", "PRODUTOS", "Valor comprado"], *report_rows]
    report_table = _table(data, [110 * mm, 25 * mm, 45 * mm])
    report_table.setStyle(
        TableStyle([("ALIGN", (1, 1), (1, -1), "CENTER")])
    )
    story += [
        report_table,
        Spacer(1, 6 * mm),
        Paragraph(f"TOTAL BRUTO: <b>{money(total)}</b>", styles["Right"]),
    ]
    _doc(path, "Relatório de Faturamento Bruto").build(story)
    return path


def _fit_label_name(name: str, maximum_width: float):
    text = " ".join(str(name).strip().upper().split()) or "PRODUTO"
    font_name = REPORT_FONT_BOLD
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
    label.setFont(REPORT_FONT_BOLD, title_size)
    label.drawCentredString(page_width / 2, 19.0 * mm, title)

    barcode = _label_barcode(barcode_value)
    barcode.drawOn(label, (page_width - barcode.width) / 2, 5.0 * mm)

    label.setFont(REPORT_FONT_BOLD, 8.6)
    label.drawCentredString(page_width / 2, 1.55 * mm, barcode_value)
    label.showPage()
    label.save()
    return path
