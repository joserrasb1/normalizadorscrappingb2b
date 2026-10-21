# -*- coding: utf-8 -*-
"""
app
---
Paquete del Normalizador de Datos para Scraping / BBDD B2B.

Módulos:
- rules        : diccionarios y patrones (fuente única de verdad)
- text_utils   : utilidades de texto (Title Case inteligente, limpieza)
- normalizers  : normalizadores por tipo de columna
- detection    : detección automática del tipo de cada columna
- tabular      : lectura/escritura de CSV, TSV y XLSX
- engine       : orquestador de la normalización de una tabla
- security     : límites, saneado de nombres y cabeceras seguras
- store        : almacén en memoria con caducidad (resultados de la demo)
"""

__version__ = "1.0.0-poc"
