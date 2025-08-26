# app/app.py
# Sales MVP — Streamlit App (EN default, ES optional)
# - Bilingual UI (English default). Switch with the header select.
# - Column mapping (Date / Category / Revenue).
# - Date policy: drop | median | const.
# - Clean table, metrics, category summary.
# - Excel / PDF exports (Unicode-safe).
# - Works with CSVs in English or Spanish headers.

from __future__ import annotations
import os
import io
import sys
import math
from datetime import datetime
from typing import Dict, Any, Tuple

import pandas as pd
import numpy as np
import streamlit as st
from fpdf import FPDF


# ------------------------------
# Page config
# ------------------------------
st.set_page_config(
    page_title="Sales MVP",
    page_icon="📊",
    layout="wide",
)

# ------------------------------
# Translations (EN default)
# ------------------------------
TR: Dict[str, Dict[str, str]] = {
    "en": {
        "app_title": "Sales MVP — CSV Analyzer",
        "intro": "Upload a CSV, map columns, choose a date policy, and export Excel/PDF.",
        "lang_label": "Language",
        "uploader": "Upload CSV file",
        "adv_title": "Advanced",
        "delimiter": "Delimiter",
        "encoding": "Encoding",
        "col_map_title": "Column mapping",
        "col_date": "Date column",
        "col_category": "Category column",
        "col_revenue": "Revenue column",
        "date_policy": "Date policy",
        "policy_help": "How to handle invalid dates (NaT) after parsing the date column.",
        "policy_drop": "drop (remove rows with invalid dates)",
        "policy_median": "median (impute with median date)",
        "policy_const": "const (impute with a specific date)",
        "const_date": "Impute date",
        "process_btn": "Process dataset",
        "metrics_title": "Metrics",
        "metric_orders": "Orders",
        "metric_total_rev": "Total revenue",
        "metric_avg_rev": "Average revenue",
        "dq_title": "Data quality",
        "dq_nat": "Invalid dates (NaT)",
        "clean_title": "Clean data",
        "summary_title": "Summary by category",
        "download_title": "Downloads",
        "dl_excel": "Download Excel",
        "dl_pdf": "Download PDF",
        "sample_title": "Samples",
        "sample_en": "Download sample (English)",
        "sample_es": "Download sample (Spanish)",
        "excel_sheet_clean": "clean_data",
        "excel_sheet_summary": "summary_by_category",
        "excel_sheet_metrics": "metrics",
        "pdf_title": "Sales report – Summary",
        "pdf_orders": "Orders",
        "pdf_total_rev": "Total revenue",
        "pdf_avg_rev": "Average revenue",
        "pdf_invalid": "Invalid dates (NaT)",
        "no_data": "Load a CSV to continue.",
        "label_policy": "Date policy",
        "policy_note": "Default is 'median' to preserve rows.",
        "map_tip": "If your headers differ, pick the right ones below.",
        "policy_warning_label": "Date policy",  # label for accessibility
        "info_revenue_parse": "Revenue column was parsed to numeric (non-numeric set to NaN).",
    },
    "es": {
        "app_title": "MVP de Ventas — Analizador CSV",
        "intro": "Sube un CSV, mapea columnas, elige una política de fechas y exporta Excel/PDF.",
        "lang_label": "Idioma",
        "uploader": "Subir archivo CSV",
        "adv_title": "Avanzado",
        "delimiter": "Delimitador",
        "encoding": "Codificación",
        "col_map_title": "Mapeo de columnas",
        "col_date": "Columna de fecha",
        "col_category": "Columna de categoría",
        "col_revenue": "Columna de ingresos",
        "date_policy": "Política de fechas",
        "policy_help": "Cómo tratar fechas inválidas (NaT) tras parsear la columna de fecha.",
        "policy_drop": "drop (eliminar filas con fecha inválida)",
        "policy_median": "median (imputar con fecha mediana)",
        "policy_const": "const (imputar con fecha específica)",
        "const_date": "Fecha a imputar",
        "process_btn": "Procesar dataset",
        "metrics_title": "Métricas",
        "metric_orders": "Pedidos",
        "metric_total_rev": "Ingresos totales",
        "metric_avg_rev": "Ingresos promedio",
        "dq_title": "Calidad de datos",
        "dq_nat": "Fechas inválidas (NaT)",
        "clean_title": "Datos limpios",
        "summary_title": "Resumen por categoría",
        "download_title": "Descargas",
        "dl_excel": "Descargar Excel",
        "dl_pdf": "Descargar PDF",
        "sample_title": "Ejemplos",
        "sample_en": "Descargar ejemplo (Inglés)",
        "sample_es": "Descargar ejemplo (Español)",
        "excel_sheet_clean": "datos_limpios",
        "excel_sheet_summary": "resumen_por_categoria",
        "excel_sheet_metrics": "metricas",
        "pdf_title": "Reporte de ventas - Resumen",
        "pdf_orders": "Pedidos",
        "pdf_total_rev": "Ingresos totales",
        "pdf_avg_rev": "Ingresos promedio",
        "pdf_invalid": "Fechas inválidas (NaT)",
        "no_data": "Carga un CSV para continuar.",
        "label_policy": "Política de fechas",
        "policy_note": "Por defecto 'median' para conservar filas.",
        "map_tip": "Si tus encabezados difieren, elige los correctos abajo.",
        "policy_warning_label": "Política de fechas",
        "info_revenue_parse": "La columna de ingresos se convirtió a numérico (no numéricos quedaron en NaN).",
    },
}

def tr(lang: str, key: str) -> str:
    return TR.get(lang, TR["en"]).get(key, key)

# Default language = English
if "lang" not in st.session_state:
    st.session_state.lang = "en"

# Header bar with language selector
left, mid, right = st.columns([1,1,1])
with left:
    st.title(tr(st.session_state.lang, "app_title"))
with right:
    st.selectbox(
        tr(st.session_state.lang, "lang_label"),
        options=["en", "es"],
        index=0,  # English default
        key="lang",
    )

st.caption(tr(st.session_state.lang, "intro"))

# ------------------------------
# License gate (optional simple password)
# ------------------------------
if st.secrets.get("LIC_MODE", "").lower() == "password":
    pwd_ok = st.session_state.get("_pwd_ok", False)
    if not pwd_ok:
        with st.expander("Access", expanded=True):
            pwd = st.text_input("Password", type="password")
            if st.button("Enter"):
                if pwd and pwd == st.secrets.get("ACCESS_PASSWORD"):
                    st.session_state["_pwd_ok"] = True
                    st.rerun()
                else:
                    st.error("Invalid password")
        st.stop()

# ------------------------------
# Sidebar: upload + advanced
# ------------------------------
st.sidebar.header(tr(st.session_state.lang, "uploader"))
uploaded = st.sidebar.file_uploader(tr(st.session_state.lang, "uploader"), type=["csv"])

with st.sidebar.expander(tr(st.session_state.lang, "adv_title"), expanded=False):
    delim = st.selectbox(
        tr(st.session_state.lang, "delimiter"),
        options=[",", ";", "\t", "|"],
        index=0,
        key="delim",
    )
    enc = st.selectbox(
        tr(st.session_state.lang, "encoding"),
        options=["utf-8", "latin-1", "cp1252"],
        index=0,
        key="enc",
    )

# ------------------------------
# Try to read CSV
# ------------------------------
df_raw: pd.DataFrame | None = None
if uploaded is not None:
    try:
        df_raw = pd.read_csv(uploaded, sep=st.session_state.delim, encoding=st.session_state.enc, dtype=str)
    except UnicodeDecodeError:
        df_raw = pd.read_csv(uploaded, sep=st.session_state.delim, encoding="latin-1", dtype=str)
    except Exception as e:
        st.error(f"Failed to read CSV: {e}")

if df_raw is None:
    st.info(tr(st.session_state.lang, "no_data"))
    st.divider()
    # Sample downloads
    st.subheader(tr(st.session_state.lang, "sample_title"))
    col_a, col_b = st.columns(2)
    # English sample
    with io.StringIO() as s:
        sample_en = pd.DataFrame({
            "order_id": [f"OD{10000+i}" for i in range(8)],
            "order_date": pd.to_datetime(
                ["2024-01-06","2024-01-15","","2024-02-07","2024-03-01","","2024-05-22","2024-06-10"],
                errors="coerce"
            ).astype(str),
            "customer_id": ["C1001","C1002","C1003","C1004","C1005","C1006","C1007","C1008"],
            "region": ["North","LATAM","LATAM","South","Center","Center","North","South"],
            "product_id": ["P201","P202","P203","P204","P205","P206","P207","P208"],
            "product_name": ["Mouse","Keyboard","Headset","Printer","Router","Dock","Webcam","Tablet"],
            "category": ["Peripherals","Peripherals","Audio","Compute","Network","Audio","Peripherals","Compute"],
            "unit_price": ["120.5","89.0","230.0","650.0","510.0","320.0","95.0","399.9"],
            "quantity": ["3","2","5","1","7","2","4","1"],
            "discount": ["0.1","0.0","0.0","0.0","0.05","0.1","0.2","0.0"],
            "revenue": ["325.35","178.00","1150.00","650.00","3391.50","576.00","304.00","399.90"],
            "status": ["Completed","Cancelled","Completed","Completed","Completed","Pending","Completed","Pending"],
        })
        sample_en.to_csv(s, index=False)
        col_a.download_button(
            tr(st.session_state.lang, "sample_en"),
            data=s.getvalue().encode("utf-8"),
            file_name="sample_en.csv",
            mime="text/csv",
        )
    # Spanish sample
    with io.StringIO() as s:
        sample_es = pd.DataFrame({
            "ID": [f"OD{10000+i}" for i in range(8)],
            "Fecha_Registro": pd.to_datetime(
                ["2024-01-06","2024-01-15","","2024-02-07","2024-03-01","","2024-05-22","2024-06-10"],
                errors="coerce"
            ).astype(str),
            "Cliente": ["C1001","C1002","C1003","C1004","C1005","C1006","C1007","C1008"],
            "Region": ["Norte","LATAM","LATAM","Sur","Centro","Centro","Norte","Sur"],
            "Producto_ID": ["P201","P202","P203","P204","P205","P206","P207","P208"],
            "Producto": ["Mouse","Teclado","Auricular","Impresora","Router","Dock","Webcam","Tablet"],
            "Categoria": ["Periféricos","Periféricos","Audio","Cómputo","Redes","Audio","Periféricos","Cómputo"],
            "Precio_Unitario": ["120.5","89.0","230.0","650.0","510.0","320.0","95.0","399.9"],
            "Cantidad": ["3","2","5","1","7","2","4","1"],
            "Descuento": ["0.1","0.0","0.0","0.0","0.05","0.1","0.2","0.0"],
            "Ingreso_Mensual": ["325.35","178.00","1150.00","650.00","3391.50","576.00","304.00","399.90"],
            "Estado": ["Completado","Cancelado","Completado","Completado","Completado","Pendiente","Completado","Pendiente"],
        })
        sample_es.to_csv(s, index=False, sep=";")
        col_b.download_button(
            tr(st.session_state.lang, "sample_es"),
            data=s.getvalue().encode("utf-8"),
            file_name="sample_es.csv",
            mime="text/csv",
        )
    st.stop()

# ------------------------------
# Column mapping UI
# ------------------------------
st.subheader(tr(st.session_state.lang, "col_map_title"))
st.caption(tr(st.session_state.lang, "map_tip"))

cols = list(df_raw.columns)

# Heuristic defaults
date_guess = next((c for c in cols if c.lower() in ("order_date", "fecha_registro", "date")), cols[0])
cat_guess = next((c for c in cols if c.lower() in ("category", "categoria")), cols[min(1, len(cols)-1)])
rev_guess = next((c for c in cols if c.lower() in ("revenue", "ingreso_mensual", "income", "amount")), cols[min(2, len(cols)-1)])

c1, c2, c3 = st.columns(3)
with c1:
    col_date = st.selectbox(tr(st.session_state.lang, "col_date"), options=cols, index=cols.index(date_guess))
with c2:
    col_category = st.selectbox(tr(st.session_state.lang, "col_category"), options=cols, index=cols.index(cat_guess))
with c3:
    col_revenue = st.selectbox(tr(st.session_state.lang, "col_revenue"), options=cols, index=cols.index(rev_guess))

st.divider()

# ------------------------------
# Policy selection
# ------------------------------
st.caption(tr(st.session_state.lang, "policy_note"))
policy = st.radio(
    label=tr(st.session_state.lang, "policy_warning_label"),  # not empty for accessibility
    options=["drop", "median", "const"],
    index=1,  # median default
    horizontal=True,
    label_visibility="collapsed",
    help=tr(st.session_state.lang, "policy_help"),
)
const_date_str = None
if policy == "const":
    const_date_str = st.date_input(tr(st.session_state.lang, "const_date"), value=datetime(2023, 1, 1)).strftime("%Y-%m-%d")

# Process button
st.button(tr(st.session_state.lang, "process_btn"), type="primary")

# ------------------------------
# Cleaning / conversions
# ------------------------------
df = df_raw.copy()

# Parse date
df[col_date] = pd.to_datetime(df[col_date], errors="coerce")

# Revenue numeric
df[col_revenue] = (
    df[col_revenue]
    .astype(str)
    .str.replace(",", ".", regex=False)
    .str.replace(r"[^\d\.\-]", "", regex=True)
    .replace("", np.nan)
)
df[col_revenue] = pd.to_numeric(df[col_revenue], errors="coerce")
st.caption(tr(st.session_state.lang, "info_revenue_parse"))

# Handle invalid dates
invalid_mask = df[col_date].isna()
invalid_count = int(invalid_mask.sum())

if policy == "drop":
    df_after = df.loc[~invalid_mask].copy()
    imputed_value = None
elif policy == "median":
    # Median date among valid rows
    if invalid_count > 0 and (df[col_date].notna().any()):
        median_ts = df.loc[~invalid_mask, col_date].astype("int64").median()
        imputed_value = pd.to_datetime(median_ts)
        df_after = df.copy()
        df_after.loc[invalid_mask, col_date] = imputed_value
    else:
        df_after = df.copy()
        imputed_value = None
elif policy == "const":
    imputed_value = pd.to_datetime(const_date_str) if const_date_str else pd.to_datetime("2022-01-01")
    df_after = df.copy()
    df_after.loc[invalid_mask, col_date] = imputed_value
else:
    df_after = df.copy()
    imputed_value = None

# ------------------------------
# Metrics
# ------------------------------
orders = int(len(df_after))
total_revenue = float(df_after[col_revenue].sum(skipna=True)) if orders else 0.0
avg_revenue = float(df_after[col_revenue].mean(skipna=True)) if orders else 0.0

st.subheader(tr(st.session_state.lang, "metrics_title"))
m1, m2, m3, m4 = st.columns(4)
m1.metric(tr(st.session_state.lang, "metric_orders"), f"{orders:,}")
m2.metric(tr(st.session_state.lang, "metric_total_rev"), f"{total_revenue:,.2f}")
m3.metric(tr(st.session_state.lang, "metric_avg_rev"), f"{avg_revenue:,.2f}")
m4.metric(tr(st.session_state.lang, "dq_nat"), f"{invalid_count:,}")

# ------------------------------
# Clean data table
# ------------------------------
st.subheader(tr(st.session_state.lang, "clean_title"))
st.dataframe(df_after, use_container_width=True, height=400)

# ------------------------------
# Summary by category
# ------------------------------
st.subheader(tr(st.session_state.lang, "summary_title"))

def resumen_categoria(df_: pd.DataFrame, cat_col: str, rev_col: str) -> pd.DataFrame:
    g = df_.groupby(cat_col, dropna=False)[rev_col].agg(count="count", sum="sum", mean="mean")
    # rename on DataFrame (not Series)
    g = g.rename(columns={"count": "orders", "sum": "total_revenue", "mean": "avg_revenue"})
    g = g.reset_index().sort_values("total_revenue", ascending=False)
    return g

summary_df = resumen_categoria(df_after, col_category, col_revenue)
st.dataframe(summary_df, use_container_width=True, height=360)

# ------------------------------
# Exports
# ------------------------------
st.subheader(tr(st.session_state.lang, "download_title"))

def export_excel_bytes(df_clean: pd.DataFrame, summary: pd.DataFrame, lang: str) -> bytes:
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as xw:
        df_clean.to_excel(xw, index=False, sheet_name=tr(lang, "excel_sheet_clean"))
        summary.to_excel(xw, index=False, sheet_name=tr(lang, "excel_sheet_summary"))
        pd.DataFrame({
            "metric": [
                tr(lang, "metric_orders"),
                tr(lang, "metric_total_rev"),
                tr(lang, "metric_avg_rev"),
                tr(lang, "dq_nat"),
            ],
            "value": [orders, total_revenue, avg_revenue, invalid_count],
        }).to_excel(xw, index=False, sheet_name=tr(lang, "excel_sheet_metrics"))
    out.seek(0)
    return out.read()

def _load_unicode_font(pdf: FPDF) -> Tuple[bool, str]:
    """
    Try to load a Unicode TTF from ./app/fonts or ./fonts.
    Returns (ok, font_family)
    """
    candidates = [
        os.path.join(os.path.dirname(__file__), "fonts", "DejaVuSans.ttf"),
        os.path.join(os.path.dirname(__file__), "fonts", "NotoSans-Regular.ttf"),
        os.path.join("app", "fonts", "DejaVuSans.ttf"),
        os.path.join("app", "fonts", "NotoSans-Regular.ttf"),
        "DejaVuSans.ttf",
        "NotoSans-Regular.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                pdf.add_font("DejaVu", "", path, uni=True)
                pdf.add_font("DejaVu", "B", path, uni=True)
                return True, "DejaVu"
            except Exception:
                # try as Noto
                try:
                    pdf.add_font("Noto", "", path, uni=True)
                    pdf.add_font("Noto", "B", path, uni=True)
                    return True, "Noto"
                except Exception:
                    pass
    return False, "helvetica"

def sanitize_text(s: str) -> str:
    # Replace en dash, em dash, etc. to ASCII hyphen to avoid Helvetica issues
    if not isinstance(s, str):
        s = str(s)
    return s.replace("–", "-").replace("—", "-")

def export_pdf_bytes(lang: str) -> bytes:
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    ok_font, fam = _load_unicode_font(pdf)
    if ok_font:
        pdf.set_font(fam, "B", 16)
    else:
        pdf.set_font("helvetica", "B", 16)

    title = sanitize_text(tr(lang, "pdf_title"))
    pdf.cell(0, 10, title, ln=1, align="C")

    if ok_font:
        pdf.set_font(fam, "", 12)
    else:
        pdf.set_font("helvetica", "", 12)

    lines = [
        f"{tr(lang, 'pdf_orders')}: {orders:,}",
        f"{tr(lang, 'pdf_total_rev')}: {total_revenue:,.2f}",
        f"{tr(lang, 'pdf_avg_rev')}: {avg_revenue:,.2f}",
        f"{tr(lang, 'pdf_invalid')}: {invalid_count:,}",
    ]
    for line in lines:
        pdf.cell(0, 8, sanitize_text(line), ln=1)

    out = pdf.output(dest="S")
    # fpdf2>=2.7 returns bytearray here
    if isinstance(out, (bytes, bytearray)):
        return bytes(out)
    else:
        # Older versions might return str
        return out.encode("latin-1", "ignore")

# Buttons
ex_bytes = export_excel_bytes(df_after, summary_df, st.session_state.lang)
pdf_bytes = export_pdf_bytes(st.session_state.lang)
cA, cB = st.columns(2)
cA.download_button(
    tr(st.session_state.lang, "dl_excel"),
    data=ex_bytes,
    file_name="report.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
cB.download_button(
    tr(st.session_state.lang, "dl_pdf"),
    data=pdf_bytes,
    file_name="report.pdf",
    mime="application/pdf",
)
