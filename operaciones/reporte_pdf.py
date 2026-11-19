"""Diseño imprimible del reporte administrativo de transacciones."""

from io import BytesIO
from xml.sax.saxutils import escape


def generar_pdf(filas, filtros, generado):
    """Compone la tabla completa en A3 horizontal, con encabezados y folios."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A3, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

    salida = BytesIO()
    ancho, alto = landscape(A3)
    margen = 30
    documento = SimpleDocTemplate(
        salida, pagesize=(ancho, alto), leftMargin=margen, rightMargin=margen,
        topMargin=48, bottomMargin=42, title="Reporte de transacciones", author="Global Exchange",
    )
    tinta = colors.HexColor("#183345")
    verde = colors.HexColor("#12574E")
    cuerpo = ParagraphStyle("Celda", fontSize=10, leading=13, textColor=tinta)
    numero = ParagraphStyle("Importe", parent=cuerpo, alignment=TA_RIGHT)
    cabecera = ParagraphStyle("Columna", parent=cuerpo, fontName="Helvetica-Bold", textColor=colors.white)
    titulo = ParagraphStyle("Titulo", parent=cuerpo, fontSize=23, leading=28, fontName="Helvetica-Bold")

    def parrafo(valor, estilo=cuerpo):
        return Paragraph(escape(str(valor)).replace("\n", "<br/>"), estilo)

    def pie_y_marca(lienzo, doc):
        lienzo.saveState()
        lienzo.setFillColor(verde)
        lienzo.setFont("Helvetica-Bold", 11)
        lienzo.drawString(margen + 6, alto - 32, "GLOBAL EXCHANGE")
        lienzo.setFont("Helvetica", 10)
        lienzo.drawRightString(ancho - margen - 6, 24, f"Página {doc.page}")
        lienzo.restoreState()

    columnas = ("ID", "Fecha y hora", "Cliente", "Tipo", "Origen", "Destino", "Tasa aplicada",
                "Comisión", "Método", "Naturaleza histórica", "Estado", "Usuario / cajero")
    pesos = (46, 68, 145, 57, 119, 119, 120, 119, 94, 90, 77, 96)
    anchos = [(documento.width - 12) * peso / sum(pesos) for peso in pesos]
    datos = [[parrafo(nombre, cabecera) for nombre in columnas]]
    for fila in filas:
        datos.append([parrafo(valor, numero if 4 <= i <= 7 else cuerpo) for i, valor in enumerate(fila)])
    tabla = LongTable(datos, colWidths=anchos, repeatRows=1, style=TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), verde),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EFF5F4")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    documento.build([
        parrafo("Reporte de transacciones", titulo), Spacer(1, 9),
        parrafo(f"Generado el {generado:%d/%m/%Y a las %H:%M:%S} ({generado.tzinfo})"),
        parrafo(f"Filtros: {filtros}"), parrafo(f"Total de transacciones: {len(filas)}"),
        Spacer(1, 12), tabla,
    ], onFirstPage=pie_y_marca, onLaterPages=pie_y_marca)
    return salida.getvalue()
