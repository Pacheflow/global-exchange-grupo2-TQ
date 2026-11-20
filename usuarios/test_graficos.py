"""Regresión de etiquetas y porcentajes independientes del render de canvas."""
from django.test import SimpleTestCase
from usuarios.graficos import presentar_graficos


class GraficosTests(SimpleTestCase):
    def reporte(self, **cambios):
        data = dict(agrupacion="mes", periodos=[dict(inicio="2027-01-01", desde="2027-01-01", hasta="2027-01-02", ganancia="100.000000", operaciones_sin_conversion=0)],
                    totales=dict(compras=2, ventas=1, operaciones=3),
                    distribucion=[dict(divisa="USD", ganancia="100.000000"), dict(divisa="EUR", ganancia="0.000000")])
        data.update(cambios)
        return data

    def test_mes_con_anio_y_rango_parcial(self):
        serie, dona = presentar_graficos(self.reporte(), divisa="")
        self.assertEqual(serie[0]["etiqueta"], "Enero 2027")
        self.assertEqual(serie[0]["hasta"], "2027-01-02")
        self.assertEqual(dona["categorias"], [dict(categoria="USD", ganancia_pyg="100.000000", porcentaje="100.00")])

    def test_dias_y_porcentajes_de_conteos(self):
        serie, dona = presentar_graficos(self.reporte(agrupacion="dia"), divisa="USD")
        self.assertEqual(serie[0]["etiqueta"], "01/01/2027")
        self.assertEqual([p["porcentaje"] for p in dona["categorias"]], ["66.67", "33.33"])

    def test_sin_datos_no_divide_por_cero(self):
        _, dona = presentar_graficos(self.reporte(totales=dict(compras=0, ventas=0, operaciones=0)), divisa="USD")
        self.assertEqual([p["porcentaje"] for p in dona["categorias"]], ["0.00", "0.00"])
