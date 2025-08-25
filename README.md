# Mercury AI – MVP Ventas

Procesa CSV/Excel y genera un Excel limpio y un PDF.

## Requisitos
- Python 3.13+
- pip install flask jinja2 pandas numpy openpyxl

## Uso rápido
python .\make_dataset.py
python .\mvp_ventas.py .\data\mvp_dataset_ventas_light_150.csv -o .\reportes\reporte.xlsx

## Carpetas
data/ (entrada), reportes/ (salida), app/ (web + PDF)

## Problemas comunes
- FileNotFoundError ? verifica ruta del CSV en data/
- PDF no sale ? instalar/configurar motor PDF
