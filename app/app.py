# app/app.py
from __future__ import annotations

import io
import csv
from datetime import datetime
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st
from fpdf import FPDF


# ---------------------------- i18n ----------------------------

def _t(lang: str, key: str) -> str:
    T = {
        "en": {
            "app_title": "Sales MVP - Web",
            "sidebar_lang": "Language / Idioma",
            "upload": "Upload your CSV/XLSX",
            "drag": "Drag and drop file here",
            "limits": "Limit 200MB per file • CSV, XLSX",
            "separator": "Separator",
            "encoding": "Encoding",
            "policy": "Policy for invalid dates",
            "policy_keep": "Impute median (keep rows)",
            "policy_drop": "Drop rows with invalid dates",
            "policy_const": "Impute constant (keep rows)",
            "const_date": "Constant date (YYYY-MM-DD)",
            "map_help": "Map the correct columns if names differ.",
            "date_col": "Date column",
            "cat_col": "Category column",
            "rev_col": "Revenue column",
            "run": "Run",
            "kpis": "KPIs",
            "orders": "Orders",
            "total_rev": "Total revenue",
            "avg_rev": "Average revenue",
            "dq": "Data Quality",
            "nat_before": "NaT dates (before)",
            "policy_used": "Policy",
            "impute_value": "Imputed value",
            "rows": "Rows",
            "rows_final": "Final rows",
            "by_cat": "Summary by category",
            "download": "Downloads",
            "dl_excel": "Download Excel",
            "dl_pdf": "Download PDF",
            "pdf_title": "Sales MVP - Report",
            "pdf_generated": "Generated",
            "auto_detect": "Auto (detect)",
            "detected_sep": "Detected separator: ",
        },
        "es": {
            "app_title": "MVP Ventas - Web",
            "sidebar_lang": "Idioma / Language",
            "upload": "Sube tu CSV/XLSX",
            "drag": "Arrastra y suelta aquí",
            "limits": "Límite 200MB por archivo • CSV, XLSX",
            "separator": "Delimitador",
            "encoding": "Codificación",
            "policy": "Política para fechas inválidas",
            "policy_keep": "Imputar mediana (conservar filas)",
            "policy_drop": "Eliminar filas con fecha inválida",
            "policy_const": "Imputar constante (conservar filas)",
            "const_date": "Fecha constante (AAAA-MM-DD)",
            "map_help": "Mapea las columnas si los nombres difieren.",
            "date_col": "Columna de fecha",
            "cat_col": "Columna de categoría",
            "rev_col": "Columna de ingreso",
            "run": "Ejecutar",
            "kpis": "KPIs",
            "orders": "Pedidos",
            "total_rev": "Ingreso total",
            "avg_rev": "Ingreso promedio",
            "dq": "Calidad de Datos",
            "nat_before": "Fechas NaT (antes)",
            "policy_used": "Política",
            "impute_value": "Valor imputado",
            "rows": "Filas",
            "rows_final": "Filas finales",
            "by_cat": "Resumen por categoría",
            "download": "Descargas",
            "dl_excel": "Descargar Excel",
            "dl_pdf": "Descargar PDF",
            "pdf_title": "MVP Ventas - Reporte",
            "pdf_generated": "Generado",
            "auto_detect": "Auto (detectar)",
            "detected_sep": "Delimitador detectado: ",
        },
    }
    return T.get(lang, T["en"]).get(key, key)


# ---------------------------- Helpers ----------------------------

def _coerce_datetime(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce", utc=False)

def _coerce_numeric(s: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(s):
        return s
    s = s.astype(str)
    # intenta normalizar comas/puntos
    s = s.str.replace(r"[^\d\-,.\s]", "", regex=True)
    # preferir punto como decimal
    # si hay coma y no punto -> usa coma como decimal
    mask = s.str.contains(",") & ~s.str.contains(r"\.")
    s.loc[mask] = s.loc[mask].str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce")


def _detect_separator(sample_text: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(sample_text, delimiters=[",", ";", "\t", "|"])
        return dialect.delimiter
    except Exception:
        return ","


def _guess_index(cols: list[str], candidates: list[str]) -> int:
    lower = [c.lower() for c in cols]
    for cand in candidates:
        if cand.lower() in lower:
            return lower.index(cand.lower())
    return 0 if cols else 0


def _summary_by_category(df: pd.DataFrame, cat: str, rev: str) -> pd.DataFrame:
    g = (
        df.groupby(cat)[rev]
        .agg(["count", "sum", "mean"])
        .rename(columns={"count": "orders", "sum": "revenue_total", "mean": "revenue_avg"})
        .reset_index()
        .sort_values("revenue_total", ascending=False)
    )
    return g


def _export_excel_bytes(
    df_clean: pd.DataFrame,
    df_cat: pd.DataFrame,
    metrics: dict,
) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        df_clean.to_excel(xw, sheet_name="CleanData", index=False)
        df_cat.to_excel(xw, sheet_name="CategorySummary", index=False)
        pd.DataFrame(list(metrics.items()), columns=["metric", "value"]).to_excel(
            xw, sheet_name="Metrics", index=False
        )
    buf.seek(0)
    return buf.read()


def _export_pdf_bytes(metrics: dict, lang: str) -> bytes:
    # Evita caracteres Unicode no soportados por Helvetica: usa solo ASCII en textos
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.add_page()
    pdf.set_font("helvetica", "B", 20)
    pdf.cell(0, 12, _t(lang, "pdf_title"), ln=1, align="C")

    pdf.ln(4)
    pdf.set_font("helvetica", "", 12)
    pdf.cell(0, 8, f"{_t(lang,'pdf_generated')}: {datetime.now():%Y-%m-%d %H:%M}", ln=1)

    pdf.ln(2)
    pdf.set_font("helvetica", "B", 14)
    pdf.cell(0, 8, "KPIs", ln=1)

    pdf.set_font("helvetica", "", 12)
    pdf.cell(0, 7, f"- {_t(lang,'orders')}: {metrics.get('orders', 0)}", ln=1)
    pdf.cell(0, 7, f"- {_t(lang,'total_rev')}: {metrics.get('total_revenue_fmt','')}", ln=1)
    pdf.cell(0, 7, f"- {_t(lang,'avg_rev')}: {metrics.get('avg_revenue_fmt','')}", ln=1)

    pdf.ln(2)
    pdf.set_font("helvetica", "B", 14)
    pdf.cell(0, 8, _t(lang, "dq"), ln=1)

    pdf.set_font("helvetica", "", 12)
    pdf.cell(0, 7, f"- {_t(lang,'nat_before')}: {metrics.get('nat_before', 0)}", ln=1)
    pdf.cell(0, 7, f"- {_t(lang,'policy_used')}: {metrics.get('policy','')}", ln=1)
    if metrics.get("impute_value"):
        pdf.cell(0, 7, f"- {_t(lang,'impute_value')}: {metrics.get('impute_value')}", ln=1)
    pdf.cell(
        0,
        7,
        f"- {_t(lang,'rows')}: {metrics.get('rows_before',0)} / {_t(lang,'rows_final')}: {metrics.get('rows_final',0)}",
        ln=1,
    )

    # FPDF 2.x devuelve bytearray cuando dest="S"
    return bytes(pdf.output(dest="S"))


def _format_money(x: float) -> str:
    try:
        return f"{x:,.2f}"
    except Exception:
        return str(x)


# ---------------------------- UI ----------------------------

st.set_page_config(page_title="Sales MVP - Web", layout="wide")

# idioma (por defecto EN)
if "lang" not in st.session_state:
    st.session_state.lang = "en"
lang = st.sidebar.selectbox(
    _t(st.session_state.lang, "sidebar_lang"),
    options=[("en", "English"), ("es", "Español")],
    index=0 if st.session_state.lang == "en" else 1,
    format_func=lambda t: t[1],
)
st.session_state.lang = lang[0]
lang = st.session_state.lang

st.title(_t(lang, "app_title"))
st.caption(_t(lang, "map_help"))

# --- Sidebar: upload & options ---
st.sidebar.header(_t(lang, "upload"))
uploaded = st.sidebar.file_uploader(
    _t(lang, "drag"),
    type=["csv", "xlsx", "xls"],
    help=_t(lang, "limits"),
)

sep_choice = st.sidebar.selectbox(
    _t(lang, "separator"),
    options=[",", ";", "\t", "|", _t(lang, "auto_detect")],
    index=0,  # default comma
)
encoding = st.sidebar.selectbox(_t(lang, "encoding"), ["utf-8", "latin-1", "cp1252"], index=0)

policy_label = st.sidebar.selectbox(
    _t(lang, "policy"),
    options=[_t(lang, "policy_keep"), _t(lang, "policy_drop"), _t(lang, "policy_const")],
    index=0,
)
const_date = st.sidebar.text_input(_t(lang, "const_date"), value="2022-01-01")


# --- Load data ---
df: Optional[pd.DataFrame] = None
detected_sep: Optional[str] = None

if uploaded is not None:
    name = uploaded.name.lower()
    if name.endswith(".csv"):
        # autodetect separator if selected
        sep = sep_choice
        if sep_choice == _t(lang, "auto_detect"):
            sample = uploaded.getvalue()[:8192].decode(encoding, errors="ignore")
            detected_sep = _detect_separator(sample)
            sep = detected_sep
            st.sidebar.caption(_t(lang, "detected_sep") + repr(detected_sep))

        df = pd.read_csv(uploaded, sep=sep if isinstance(sep, str) else ",", encoding=encoding, dtype=str)
    else:
        df = pd.read_excel(uploaded, dtype=str)

# --- Column mapping ---
date_col = cat_col = rev_col = None
columns = df.columns.tolist() if df is not None else []

left, mid, right = st.columns(3)
with left:
    date_col = st.selectbox(
        _t(lang, "date_col"),
        options=columns if columns else [""],
        index=_guess_index(columns, ["order_date", "Fecha_Registro", "Registration_Date", "date"]),
        key="date_col",
    )
with mid:
    cat_col = st.selectbox(
        _t(lang, "cat_col"),
        options=columns if columns else [""],
        index=_guess_index(columns, ["category", "Categoria"]),
        key="cat_col",
    )
with right:
    rev_col = st.selectbox(
        _t(lang, "rev_col"),
        options=columns if columns else [""],
        index=_guess_index(columns, ["revenue", "Ingreso_Mensual", "Monthly_Income"]),
        key="rev_col",
    )

run = st.button(_t(lang, "run"), type="primary", use_container_width=True)

# ---------------------------- Pipeline ----------------------------
if run and df is not None and date_col and cat_col and rev_col:
    df_proc = df.copy()

    # Coercions
    # Fechas
    dt = _coerce_datetime(df_proc[date_col])
    nat_before = int(dt.isna().sum())

    policy = policy_label
    imputed_val = ""
    if policy == _t(lang, "policy_drop"):
        mask_valid = ~dt.isna()
        df_proc = df_proc.loc[mask_valid].reset_index(drop=True)
        dt = dt.loc[mask_valid].reset_index(drop=True)
    elif policy == _t(lang, "policy_const"):
        try:
            const_dt = pd.to_datetime(const_date, errors="coerce")
        except Exception:
            const_dt = pd.NaT
        dt = dt.fillna(const_dt)
        imputed_val = const_date
    else:
        # mediana
        median_dt = pd.to_datetime(dt.dropna().astype("int64").median())
        dt = dt.fillna(median_dt)
        imputed_val = str(pd.to_datetime(median_dt).date())

    df_proc[date_col] = dt

    # Numérico (revenue)
    df_proc[rev_col] = _coerce_numeric(df_proc[rev_col])

    # KPIs
    orders = int(len(df_proc))
    total_rev = float(np.nan_to_num(df_proc[rev_col]).sum())
    avg_rev = float(total_rev / orders) if orders > 0 else 0.0

    metrics = {
        "orders": orders,
        "total_revenue": total_rev,
        "total_revenue_fmt": _format_money(total_rev),
        "avg_revenue": avg_rev,
        "avg_revenue_fmt": _format_money(avg_rev),
        "nat_before": nat_before,
        "policy": policy,
        "impute_value": imputed_val,
        "rows_before": int(len(df)),
        "rows_final": int(len(df_proc)),
    }

    # UI blocks
    st.subheader(_t(lang, "kpis"))
    k1, k2, k3 = st.columns(3)
    k1.metric(_t(lang, "orders"), f"{orders:,}")
    k2.metric(_t(lang, "total_rev"), _format_money(total_rev))
    k3.metric(_t(lang, "avg_rev"), _format_money(avg_rev))

    st.subheader(_t(lang, "dq"))
    c1, c2, c3, c4 = st.columns(4)
    c1.write(f"**{_t(lang,'nat_before')}**: {nat_before:,}")
    c2.write(f"**{_t(lang,'policy_used')}**: {policy}")
    c3.write(f"**{_t(lang,'impute_value')}**: {imputed_val or '-'}")
    c4.write(f"**{_t(lang,'rows')}**: {len(df):,} / **{_t(lang,'rows_final')}**: {len(df_proc):,}")

    st.subheader("Clean data")
    st.dataframe(df_proc.head(200), use_container_width=True, height=300)

    st.subheader(_t(lang, "by_cat"))
    by_cat = _summary_by_category(df_proc, cat_col, rev_col)
    st.dataframe(by_cat, use_container_width=True, height=320)

    # Exports
    st.subheader(_t(lang, "download"))
    excel_bytes = _export_excel_bytes(df_proc, by_cat, metrics)
    pdf_bytes = _export_pdf_bytes(metrics, lang)

    d1, d2 = st.columns(2)
    d1.download_button(
        _t(lang, "dl_excel"),
        data=excel_bytes,
        file_name="report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
    d2.download_button(
        _t(lang, "dl_pdf"),
        data=pdf_bytes,
        file_name="report.pdf",
        mime="application/pdf",
        use_container_width=True,
    )
