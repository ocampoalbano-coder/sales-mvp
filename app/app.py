# -*- coding: utf-8 -*-
import io
import os
import csv
from datetime import datetime, date, time, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
from fpdf import FPDF


# --------------------------
# Config & i18n
# --------------------------
st.set_page_config(page_title="Sales MVP – Web", layout="wide")

TR = {
    "en": {
        "title": "Sales MVP - Web",
        "lang": "Language / Idioma",
        "upload": "Upload your CSV/XLSX",
        "map": "Map the correct columns if names differ. Columns are shown exactly as in your file.",
        "date_col": "Date column",
        "cat_col": "Category column",
        "rev_col": "Revenue column",
        "run": "Run",
        "policy": "Policy for invalid dates",
        "drop": "Drop rows",
        "median": "Impute median (keep rows)",
        "const": "Impute constant date (keep rows)",
        "const_date": "Constant date (YYYY-MM-DD)",
        "kpis": "KPIs",
        "orders": "Orders",
        "tot_rev": "Total revenue",
        "avg_rev": "Average revenue",
        "dq": "Data Quality",
        "nat_before": "NaT dates (before)",
        "policy_used": "Policy",
        "imputed_value": "Imputed value",
        "rows_before_after": "Original rows / Final rows",
        "rev_recalc_rows": "Revenue recalculated (rows)",
        "dl_excel": "⬇️ Download Excel",
        "dl_pdf": "⬇️ Download PDF",
        "templates": "Download templates / Descargar plantillas",
        "dl_csv_en": "⬇️ Download English CSV",
        "dl_csv_es": "⬇️ Descargar CSV Español",
        "sep": "Separator",
        "enc": "Encoding",
        "auto": "Auto-detect (default)",
        "comma": "Comma ,",
        "semicolon": "Semicolon ;",
        "tab": "Tab \\t",
        "pipe": "Pipe |",
        "choose_cols": "Load a file to choose columns",
        "auth_title": "Access",
        "auth_desc": "This app is protected by a password.",
        "password": "Password",
        "auth_btn": "Enter",
        "auth_bad": "Invalid password.",
    },
    "es": {
        "title": "Sales MVP - Web",
        "lang": "Language / Idioma",
        "upload": "Sube tu CSV/XLSX",
        "map": "Mapea las columnas si difieren. Los nombres se muestran tal cual están en tu archivo.",
        "date_col": "Columna de fecha",
        "cat_col": "Columna de categoría",
        "rev_col": "Columna de ingresos",
        "run": "Ejecutar",
        "policy": "Política para fechas inválidas",
        "drop": "Eliminar filas",
        "median": "Imputar mediana (mantener filas)",
        "const": "Imputar fecha constante (mantener filas)",
        "const_date": "Fecha constante (YYYY-MM-DD)",
        "kpis": "KPIs",
        "orders": "Pedidos",
        "tot_rev": "Ingreso total",
        "avg_rev": "Ingreso promedio",
        "dq": "Calidad de Datos",
        "nat_before": "Fechas NaT (antes)",
        "policy_used": "Política",
        "imputed_value": "Valor imputado",
        "rows_before_after": "Filas originales / finales",
        "rev_recalc_rows": "Revenue recalculado (filas)",
        "dl_excel": "⬇️ Descargar Excel",
        "dl_pdf": "⬇️ Descargar PDF",
        "templates": "Download templates / Descargar plantillas",
        "dl_csv_en": "⬇️ Descargar CSV Inglés",
        "dl_csv_es": "⬇️ Descargar CSV Español",
        "sep": "Separador",
        "enc": "Codificación",
        "auto": "Auto-detectar (por defecto)",
        "comma": "Coma ,",
        "semicolon": "Punto y coma ;",
        "tab": "Tabulación \\t",
        "pipe": "Barra |",
        "choose_cols": "Carga un archivo para elegir columnas",
        "auth_title": "Acceso",
        "auth_desc": "Esta app está protegida con contraseña.",
        "password": "Contraseña",
        "auth_btn": "Ingresar",
        "auth_bad": "Contraseña inválida.",
    },
}

def tr(lang: str, key: str) -> str:
    return TR.get(lang, TR["en"]).get(key, key)


# --------------------------
# Auth (password mode)
# --------------------------
def _auth_gate() -> None:
    mode = st.secrets.get("LIC_MODE", "open").lower()
    if mode != "password":
        return

    hours = st.secrets.get("SESSION_HOURS", 0)
    try:
        hours = int(hours)
    except Exception:
        hours = 0

    if "AUTH_OK" in st.session_state:
        if hours <= 0:
            return
        if st.session_state.get("AUTH_UNTIL") and datetime.utcnow() < st.session_state["AUTH_UNTIL"]:
            return
        # expired
        st.session_state.clear()

    lang = st.session_state.get("ui_lang", "en")
    st.header(tr(lang, "auth_title"))
    st.info(tr(lang, "auth_desc"))
    pwd = st.text_input(tr(lang, "password"), type="password")
    if st.button(tr(lang, "auth_btn")):
        if pwd == st.secrets.get("ACCESS_PASSWORD", ""):
            st.session_state["AUTH_OK"] = True
            if hours > 0:
                st.session_state["AUTH_UNTIL"] = datetime.utcnow() + timedelta(hours=hours)
            st.rerun()
        else:
            st.error(tr(lang, "auth_bad"))
    st.stop()


# --------------------------
# Helpers
# --------------------------
def _sniff_sep_and_enc(raw_bytes: bytes):
    """Try to guess separator and encoding quickly."""
    # Encoding: try utf-8, then latin-1
    encs = ["utf-8", "latin-1"]
    enc_ok = None
    text = None
    for enc in encs:
        try:
            text = raw_bytes.decode(enc)
            enc_ok = enc
            break
        except Exception:
            continue
    if enc_ok is None:
        enc_ok = "utf-8"
        text = raw_bytes.decode(enc_ok, errors="ignore")

    # Separator sniff
    try:
        sample = text[:4096]
        dialect = csv.Sniffer().sniff(sample, delimiters=[",", ";", "\t", "|"])
        sep = dialect.delimiter
    except Exception:
        # fallback: guess by frequency
        candidates = {",": text.count(","), ";": text.count(";"), "\t": text.count("\t"), "|": text.count("|")}
        sep = max(candidates, key=candidates.get)

    return sep, enc_ok


def load_file(uploaded, sep_choice: str, enc_choice: str) -> pd.DataFrame:
    """Read CSV or Excel; support autodetect for CSV."""
    if uploaded is None:
        return pd.DataFrame()

    name = uploaded.name.lower()
    raw = uploaded.getvalue()

    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(raw))

    # CSV
    if sep_choice == "auto" or enc_choice == "auto":
        sep_auto, enc_auto = _sniff_sep_and_enc(raw)
    else:
        sep_auto, enc_auto = ",", "utf-8"

    sep = {"auto": sep_auto, ",": ",", ";": ";", "\\t": "\t", "|": "|"}[sep_choice]
    enc = enc_choice if enc_choice != "auto" else enc_auto

    # Try strict, then permissive
    try:
        return pd.read_csv(io.BytesIO(raw), sep=sep, encoding=enc)
    except Exception:
        return pd.read_csv(io.BytesIO(raw), sep=sep, encoding=enc, engine="python", on_bad_lines="skip")


def _excel_bytes(df_clean: pd.DataFrame, meta: dict) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        df_clean.to_excel(xw, index=False, sheet_name="clean_data")
        pd.DataFrame([meta]).T.rename(columns={0: "value"}).to_excel(xw, sheet_name="metrics")
    buf.seek(0)
    return buf.read()


def _safe_text(s: str) -> str:
    # Ensure text fits Helvetica if no Unicode font; replace unsupported chars
    return s.encode("latin-1", errors="replace").decode("latin-1")


def _pdf_bytes(metrics: dict, lang: str) -> bytes:
    # Try to use Unicode TTF if available
    font_path = None
    for candidate in ["app/fonts/DejaVuSans.ttf", "app/fonts/NotoSans-Regular.ttf"]:
        if Path(candidate).exists():
            font_path = candidate
            break

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.add_page()

    if font_path:
        pdf.add_font("DejaVu", "", font_path, uni=True)
        pdf.set_font("DejaVu", size=22)
        title = "Reporte de Ventas (MVP)" if lang == "es" else "Sales Report (MVP)"
        pdf.cell(0, 10, title, ln=1, align="C")
        pdf.set_font("DejaVu", size=12)
        gen = "Generado" if lang == "es" else "Generated"
        pdf.cell(0, 8, f"{gen}: {datetime.now():%Y-%m-%d %H:%M}", ln=1)
    else:
        pdf.set_font("Helvetica", size=22)
        title = "Reporte de Ventas (MVP)" if lang == "es" else "Sales Report (MVP)"
        pdf.cell(0, 10, _safe_text(title), ln=1, align="C")
        pdf.set_font("Helvetica", size=12)
        gen = "Generado" if lang == "es" else "Generated"
        pdf.cell(0, 8, _safe_text(f"{gen}: {datetime.now():%Y-%m-%d %H:%M}"), ln=1)

    # Body
    def line(txt: str):
        if font_path:
            pdf.cell(0, 8, txt, ln=1)
        else:
            pdf.cell(0, 8, _safe_text(txt), ln=1)

    h1 = "KPIs:" if lang == "es" else "KPIs:"
    pdf.set_font(pdf.font_family, size=14)
    line(h1)
    pdf.set_font(pdf.font_family, size=12)

    orders_lbl = "Pedidos" if lang == "es" else "Orders"
    total_lbl = "Ingreso total" if lang == "es" else "Total revenue"
    avg_lbl = "Ingreso promedio" if lang == "es" else "Average revenue"

    line(f"- {orders_lbl}: {metrics['orders']:,}")
    line(f"- {total_lbl}: {metrics['total_revenue']:,.2f}")
    line(f"- {avg_lbl}: {metrics['avg_revenue']:,.2f}")
    line("")

    h2 = "Calidad de Datos:" if lang == "es" else "Data Quality:"
    pdf.set_font(pdf.font_family, size=14)
    line(h2)
    pdf.set_font(pdf.font_family, size=12)

    nat_lbl = "Fechas NaT (antes)" if lang == "es" else "NaT dates (before)"
    pol_lbl = "Política" if lang == "es" else "Policy"
    imp_lbl = "Valor imputado" if lang == "es" else "Imputed value"
    rows_lbl = "Filas originales / finales" if lang == "es" else "Original rows / Final rows"
    rrc_lbl = "Revenue recalculado (filas)" if lang == "es" else "Revenue recalculated (rows)"

    line(f"- {nat_lbl}: {metrics['nat_before']}")
    line(f"- {pol_lbl}: {metrics['policy']}")
    if metrics.get("imputed_value"):
        line(f"- {imp_lbl}: {metrics['imputed_value']}")
    line(f"- {rows_lbl}: {metrics['rows_before']} / {metrics['rows_after']}")
    line(f"- {rrc_lbl}: {metrics['recalc_rows']}")

    out = pdf.output(dest="S")
    # fpdf2 suele devolver bytes; por si acaso convertimos bytearray/memoryview
    if isinstance(out, (bytearray, memoryview)):
        out = bytes(out)
    return out


# --------------------------
# Sidebar UI (lang, auth, upload, templates)
# --------------------------
with st.sidebar:
    # Language first so gate can use it
    ui_lang = st.selectbox(TR["en"]["lang"], ["English", "Español"], index=0)
    st.session_state["ui_lang"] = "es" if ui_lang.startswith("Espa") else "en"

_auth_gate()  # may stop the app

lang = st.session_state.get("ui_lang", "en")
st.title(tr(lang, "title"))

with st.sidebar:
    st.subheader(tr(lang, "upload"))

    sep_label = tr(lang, "sep")
    enc_label = tr(lang, "enc")
    sep_choice = st.selectbox(
        sep_label,
        [tr(lang, "auto"), ",", ";", "\\t", "|"],
        index=0,
        help="CSV only. Excel is detected automatically.",
    )
    sep_key = "auto" if sep_choice.startswith("Auto") or sep_choice.startswith("Auto-") else sep_choice

    enc_choice = st.selectbox(
        enc_label,
        [tr(lang, "auto"), "utf-8", "latin-1", "utf-16"],
        index=0,
        help="Encoding guess: utf-8 → latin-1 fallback.",
    )
    enc_key = "auto" if enc_choice.startswith("Auto") or enc_choice.startswith("Auto-") else enc_choice

    uploaded = st.file_uploader("CSV/XLSX", type=["csv", "xlsx", "xls"])

    # Templates (strings → no bytearray)
    with st.expander(tr(lang, "templates")):
        en_csv = (
            "ID,Registration_Date,Category,Monthly_Income,Status\n"
            "1,2024-07-10,Electronics,1200.50,Completed\n"
            "2,,Clothing,845.90,Pending\n"
            "3,2023-11-05,Home,560.00,Completed\n"
            "4,2022-01-17,Electronics,2200.00,Canceled\n"
            "5,2024-03-22,Clothing,1400.75,Completed\n"
            "6,2025-08-01,Home,980.00,Pending\n"
        )
        es_csv = (
            "ID;Fecha_Registro;Categoria;Ingreso_Mensual;Estado\n"
            "1;2024-07-10;Electrónica;1200.50;Completado\n"
            "2;;Ropa;845.90;Pendiente\n"
            "3;2023-11-05;Hogar;560.00;Completado\n"
            "4;2022-01-17;Electrónica;2200.00;Cancelado\n"
            "5;2024-03-22;Ropa;1400.75;Completado\n"
            "6;2025-08-01;Hogar;980.00;Pendiente\n"
        )
        st.download_button(tr(lang, "dl_csv_en"), data=en_csv, file_name="sample_en_web.csv", mime="text/csv")
        st.download_button(tr(lang, "dl_csv_es"), data=es_csv, file_name="sample_es_web.csv", mime="text/csv")


# --------------------------
# Main UI
# --------------------------
st.caption(tr(lang, "map"))

if uploaded is None:
    st.info(tr(lang, "choose_cols"))
    st.stop()

df_raw = load_file(uploaded, sep_key, enc_key)
cols = list(df_raw.columns)
if not cols:
    st.error("Empty file / Archivo vacío")
    st.stop()

c_date, c_cat, c_rev = st.columns(3)
with c_date:
    col_date = st.selectbox(tr(lang, "date_col"), options=cols, index=0)
with c_cat:
    col_cat = st.selectbox(tr(lang, "cat_col"), options=cols, index=min(1, len(cols)-1))
with c_rev:
    col_rev = st.selectbox(tr(lang, "rev_col"), options=cols, index=min(2, len(cols)-1))

# Policy controls (label non-empty to avoid Streamlit warning)
policy = st.radio(
    tr(lang, "policy"),
    options=["drop", "median", "const"],
    format_func=lambda x: {"drop": tr(lang, "drop"), "median": tr(lang, "median"), "const": tr(lang, "const")}[x],
    horizontal=True,
    index=1,
)
const_date = None
if policy == "const":
    d: date = st.date_input(tr(lang, "const_date"), value=date(2022, 1, 1))
    const_date = datetime.combine(d, time(12, 0, 0))

run = st.button(tr(lang, "run"), use_container_width=True)
if not run:
    st.stop()

# --------------------------
# Processing
# --------------------------
df = df_raw.copy()

# Parse date & revenue
dates = pd.to_datetime(df[col_date], errors="coerce", utc=False, infer_datetime_format=True)
nat_before = int(dates.isna().sum())

rev = pd.to_numeric(df[col_rev], errors="coerce").astype(float)
df["_date_"] = dates
df["_rev_"] = rev

# Apply policy
imputed_value = ""
if policy == "drop":
    df_after = df.loc[df["_date_"].notna()].copy()
elif policy == "median":
    med = pd.to_datetime(df["_date_"].dropna().median())
    imputed_value = med.strftime("%Y-%m-%d %H:%M:%S") if pd.notna(med) else ""
    df_after = df.copy()
    df_after["_date_"] = df_after["_date_"].fillna(med)
else:  # const
    if const_date is None:
        const_date = datetime(2022, 1, 1, 12, 0, 0)
    imputed_value = const_date.strftime("%Y-%m-%d %H:%M:%S")
    df_after = df.copy()
    df_after["_date_"] = df_after["_date_"].fillna(const_date)

rows_before = len(df)
rows_after = len(df_after)

# KPIs
orders = rows_after
total_rev = float(np.nan_to_num(df_after["_rev_"]).sum())
avg_rev = float(np.nan_to_num(df_after["_rev_"]).mean()) if orders > 0 else 0.0

# Output dataframe (clean)
out_cols = [col_date, col_cat, col_rev]
df_out = df_after[[col_date, col_cat, col_rev]].copy()
df_out.rename(columns={col_date: "Date", col_cat: "Category", col_rev: "Revenue"}, inplace=True)

# --------------------------
# UI Results
# --------------------------
st.subheader(tr(lang, "kpis"))
m1, m2, m3 = st.columns(3)
m1.metric(f"{tr(lang, 'orders')} / Pedidos", f"{orders:,}")
m2.metric(f"{tr(lang, 'tot_rev')} / Ingreso total", f"{total_rev:,.2f}")
m3.metric(f"{tr(lang, 'avg_rev')} / Ingreso promedio", f"{avg_rev:,.2f}")

st.subheader(tr(lang, "dq"))
st.write(
    f"- {tr(lang, 'nat_before')} / {TR['es']['nat_before']}: **{nat_before}**  \n"
    f"- {tr(lang, 'policy_used')} / {TR['es']['policy_used']}: **{tr(lang, policy)}**  \n"
    + (f"- {tr(lang, 'imputed_value')} / {TR['es']['imputed_value']}: **{imputed_value}**  \n" if imputed_value else "")
    + f"- {tr(lang, 'rows_before_after')} / {TR['es']['rows_before_after']}: **{rows_before} / {rows_after}**  \n"
    f"- {tr(lang, 'rev_recalc_rows')} / {TR['es']['rev_recalc_rows']}: **0**"
)

st.dataframe(df_out.head(200), use_container_width=True)

# --------------------------
# Downloads
# --------------------------
metrics = {
    "orders": orders,
    "total_revenue": total_rev,
    "avg_revenue": avg_rev,
    "nat_before": nat_before,
    "policy": tr(lang, policy),
    "imputed_value": imputed_value,
    "rows_before": rows_before,
    "rows_after": rows_after,
    "recalc_rows": 0,
}

excel_bytes = _excel_bytes(df_out, metrics)
pdf_bytes = _pdf_bytes(metrics, lang)

b1, b2 = st.columns(2)
b1.download_button(
    tr(lang, "dl_excel"),
    data=excel_bytes,
    file_name="report.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
)
b2.download_button(
    tr(lang, "dl_pdf"),
    data=pdf_bytes,  # bytes (no bytearray)
    file_name="report.pdf",
    mime="application/pdf",
    use_container_width=True,
)
