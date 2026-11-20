"""Presentación decimal compartida sin alterar precisión ni contrato."""

from decimal import Decimal, localcontext

from django.template import Context, Template
from django.test import SimpleTestCase

from usuarios.templatetags.importes import importe_legible, importe_pyg


class ImportesPYGTests(SimpleTestCase):
    def test_redondeo_visual_entero_y_miles(self):
        for valor, esperado in (("0", "0"), ("51660.000000", "51.660"),
                                ("738000", "738.000"), ("1234.49", "1.234"),
                                ("1234.50", "1.235"), (None, "")):
            with self.subTest(valor=valor):
                self.assertEqual(importe_pyg(valor), esperado)
        self.assertEqual(importe_legible("1234.50"), "1.234,5")

    def test_template_pyg_sin_modificar_decimal(self):
        monto = Decimal("51660.750000")
        self.assertEqual(Template('{% load importes %}{{ monto|importe_pyg }} PYG').render(
            Context({"monto": monto})), "51.661 PYG")
        self.assertEqual(monto, Decimal("51660.750000"))


class ImportesLegiblesTests(SimpleTestCase):
    def test_importes_enteros_y_cero_sin_decimales_innecesarios(self):
        for valor, esperado in (("0.000000", "0"), ("51660.000000", "51.660"),
                                ("738000.000000", "738.000"),
                                ("2450000.000000", "2.450.000"),
                                (Decimal("123.000000"), "123")):
            with self.subTest(valor=valor):
                self.assertEqual(importe_legible(valor), esperado)

    def test_decimales_significativos_y_signo(self):
        for valor, esperado in (("1234.560000", "1.234,56"),
                                ("0.000001", "0,000001"),
                                ("-1234.500000", "-1.234,5"),
                                ("-0.000000", "0")):
            with self.subTest(valor=valor):
                self.assertEqual(importe_legible(valor), esperado)

    def test_totales_grandes_no_pierden_precision_ni_se_redondean(self):
        valor = Decimal("123456789012345678901234567890.123456")
        with localcontext() as contexto:
            contexto.prec = 6
            self.assertEqual(importe_legible(valor),
                             "123.456.789.012.345.678.901.234.567.890,123456")
        self.assertEqual(str(valor), "123456789012345678901234567890.123456")

    def test_no_disponible_no_se_convierte_a_cero_y_texto_se_escapa(self):
        self.assertEqual(importe_legible(None), "")
        plantilla = Template('{% load importes %}{{ valor|importe_legible }}')
        self.assertEqual(plantilla.render(Context({"valor": "<script>"})),
                         "&lt;script&gt;")
