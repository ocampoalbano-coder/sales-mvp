r"""
Pipeline MVP: CSV/Excel -> Excel con varias hojas + PDF de KPIs.

Funciona tanto con el dataset sintético (columnas estándar)
como con datasets reales mapeando nombres de columnas.

Ejemplos (PowerShell):

  # Dataset sintético
  python -W default .\mvp_ventas.py ".\data\mvp_dataset_ventas_light_150.csv" `
    -o ".\reportes\reporte.xlsx" `
    --pdf-out ".\reportes\salida.pdf" `
    --delimiter "," --encoding "utf-8" `
    --col-categoria category `
    --drop-nat-dates

  # Dataset real (separador ';') mapeando columnas
  python -W default .\mvp_ventas.py ".\data\dataset_real.csv" `
    -o ".\reportes\reporte_real.xlsx" `
    --pdf-out ".\reportes\salida_real.pdf" `
    --delimiter ";" --encoding "utf-8" `
    --col-fecha "Fecha_Registro" `
    --col-categoria "Categoria" `
    --col-revenue "Ingreso_Mensual" `
    --impute-date median
"""
from __future__ import annotations
import argparse
import os
from datetime import datetime
import pandas as pd
import numpy as np
from fpdf import FPDF, XPos, YPos


# ---------- Utilidades ----------

def _ensure_dir(path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)


def _to_datetime_safe(s: pd.Series) -> pd.Series:
    """Parseo robusto a datetime (sin infer_datetime_format)."""
    return pd.to_datetime(s, errors="coerce", utc=False)


def _to_numeric_safe(s: pd.Series) -> pd.Series:
    if s.dtype.kind in "iufc":  # ya es numérico
        return s
    return pd.to_numeric(s.astype(str).str.replace(",", ".", regex=False), errors="coerce")


def _pick(df: pd.DataFrame, *names: str | None) -> str | None:
    """Devuelve el primer nombre que exista como columna del df (o None)."""
    for n in names:
        if n and n in df.columns:
            return n
    return None


# ---------- Carga, limpieza de fecha, métricas ----------

def cargar_csv(input_csv: str, delimiter: str, encoding: str) -> pd.DataFrame:
    df = pd.read_csv(input_csv, delimiter=delimiter, encoding=encoding, dtype=str)
    print(f"[OK] CSV cargado ({len(df)} filas, {df.shape[1]} columnas).")
    return df


def aplicar_politica_fecha(
    df: pd.DataFrame,
    col_fecha: str,
    drop_nat: bool,
    impute_mode: str | None,
    impute_const: str | None,
) -> tuple[pd.DataFrame, dict, pd.DataFrame | None]:
    """Devuelve (df_limpio, metrics_date, invalid_dates_df)."""
    metrics_date: dict[str, object] = {}

    if col_fecha not in df.columns:
        raise ValueError(f"No existe la columna de fecha '{col_fecha}' en el dataset.")

    df = df.copy()
    fecha_parsed = _to_datetime_safe(df[col_fecha])
    nat_before = int(fecha_parsed.isna().sum())
    metrics_date["nat_before"] = nat_before
    invalid_dates_df = df.loc[fecha_parsed.isna()].copy() if nat_before > 0 else None

    df[col_fecha] = fecha_parsed

    policy = "NONE"
    impute_value_used = None

    if drop_nat and nat_before > 0:
        policy = "DROP"
        df = df.loc[~df[col_fecha].isna()].copy()

    elif impute_mode:
        policy = f"IMPUTE({impute_mode})"
        if impute_mode == "median":
            # Mediana como timestamp (si no hay válidas -> queda None)
            valid = df.loc[~df[col_fecha].isna(), col_fecha]
            if not valid.empty:
                # Mediana: convertir a int64 (ns) para calcular y volver a datetime
                med = pd.to_datetime(valid).astype("int64").median()
                impute_value_used = pd.to_datetime(med)
                df.loc[df[col_fecha].isna(), col_fecha] = impute_value_used
        elif impute_mode == "mean":
            valid = df.loc[~df[col_fecha].isna(), col_fecha]
            if not valid.empty:
                mean = pd.to_datetime(valid).astype("int64").mean()
                impute_value_used = pd.to_datetime(mean)
                df.loc[df[col_fecha].isna(), col_fecha] = impute_value_used
        elif impute_mode == "const":
            if not impute_const:
                raise ValueError("Debes indicar --impute-const YYYY-MM-DD cuando usas --impute-date const.")
            impute_value_used = pd.to_datetime(impute_const, errors="coerce")
            df.loc[df[col_fecha].isna(), col_fecha] = impute_value_used
        else:
            raise ValueError("impute-mode inválido. Usa: median | mean | const")

    metrics_date["policy"] = policy
    metrics_date["impute_value_used"] = impute_value_used

    return df, metrics_date, invalid_dates_df


# ---------- Exportaciones ----------

def exportar_excel(
    df_limpio: pd.DataFrame,
    output_path: str,
    metrics: dict,
    invalid_dates_df: pd.DataFrame | None,
    col_region: str | None = None,
    col_categoria: str | None = None,
    col_revenue: str | None = None,
) -> None:
    """
    Exporta:
      - datos_limpios
      - ResumenCategoria (si hay categoría)
      - ResumenRegion (si hay región) o ResumenGlobal
      - TopProductos (si existen product_id/product_name)
      - FechasInvalidas (si hubo)
      - Metrics
    """
    _ensure_dir(output_path)

    # Elegimos nombres reales según existan
    rev_col = _pick(df_limpio, col_revenue, "revenue", "Ingreso_Mensual")
    cat_col = _pick(df_limpio, col_categoria, "category", "Categoria")
    reg_col = _pick(df_limpio, col_region, "region", "Region")

    # Aseguro revenue numérico para agregaciones
    if rev_col:
        df_limpio[rev_col] = _to_numeric_safe(df_limpio[rev_col])

    with pd.ExcelWriter(output_path, engine="openpyxl") as xw:
        # 1) data limpia
        df_limpio.to_excel(xw, sheet_name="datos_limpios", index=False)

        # 2) fechas inválidas
        if invalid_dates_df is not None and not invalid_dates_df.empty:
            invalid_dates_df.to_excel(xw, sheet_name="FechasInvalidas", index=False)

        # 3) resumen por categoría
        if cat_col and rev_col:
            grp = df_limpio.groupby(cat_col, dropna=False)
            res = grp.agg(revenue_total=(rev_col, "sum"), ingreso_promedio=(rev_col, "mean"))
            res = res.join(grp.size().rename("pedidos"))
            res = res.reset_index()[[cat_col, "pedidos", "revenue_total", "ingreso_promedio"]]
            res.to_excel(xw, sheet_name="ResumenCategoria", index=False)

        # 4) resumen por región o global
        if rev_col:
            if reg_col:
                grp = df_limpio.groupby(reg_col, dropna=False)
                resr = grp.agg(revenue_total=(rev_col, "sum"), ingreso_promedio=(rev_col, "mean"))
                resr = resr.join(grp.size().rename("pedidos"))
                resr = resr.reset_index()[[reg_col, "pedidos", "revenue_total", "ingreso_promedio"]]
                resr.to_excel(xw, sheet_name="ResumenRegion", index=False)
            else:
                resumen_global = pd.DataFrame(
                    {
                        "pedidos": [len(df_limpio)],
                        "revenue_total": [df_limpio[rev_col].sum()],
                        "ingreso_promedio": [df_limpio[rev_col].mean()],
                    }
                )
                resumen_global.to_excel(xw, sheet_name="ResumenGlobal", index=False)

        # 5) top productos (si existen)
        if {"product_id", "product_name"}.issubset(df_limpio.columns) and rev_col:
            grp = df_limpio.groupby(["product_id", "product_name"], dropna=False)
            agg = {"revenue_total": (rev_col, "sum")}
            if "quantity" in df_limpio.columns:
                df_limpio["quantity"] = _to_numeric_safe(df_limpio["quantity"])
                agg["quantity_total"] = ("quantity", "sum")
            top = grp.agg(**agg)
            top = top.join(grp.size().rename("pedidos"))
            cols = ["pedidos", "revenue_total"] + (["quantity_total"] if "quantity_total" in top.columns else [])
            top = top.reset_index().sort_values("revenue_total", ascending=False).head(50)
            # reordenar columnas si existe quantity_total
            final_cols = ["product_id", "product_name"] + cols
            top[final_cols].to_excel(xw, sheet_name="TopProductos", index=False)

        # 6) métricas
        pd.DataFrame([{"metric": k, "value": v} for k, v in metrics.items()]).to_excel(
            xw, sheet_name="Metrics", index=False
        )

    print(f"[OK] Reporte Excel generado: {output_path}")


def exportar_pdf(df: pd.DataFrame, pdf_path: str, metrics: dict, col_revenue: str | None) -> None:
    _ensure_dir(pdf_path)

    # Revenue total / promedio (si se mapeó)
    total = 0.0
    prom = 0.0
    if col_revenue and col_revenue in df.columns:
        v = _to_numeric_safe(df[col_revenue])
        total = float(v.sum())
        prom = float(v.mean())

    pedidos = len(df)
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M")

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    pdf.set_font("helvetica", "B", 20)
    pdf.cell(0, 12, "Reporte de Ventas (MVP)", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("helvetica", "", 11)
    pdf.cell(0, 8, f"Generado: {ahora}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("helvetica", "B", 13)
    pdf.cell(0, 8, "KPIs:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("helvetica", "", 11)
    pdf.cell(0, 6, f"- Pedidos: {pedidos}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 6, f"- Ingreso total: {total:,.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 6, f"- Ingreso promedio: {prom:,.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("helvetica", "B", 13)
    pdf.cell(0, 8, "Calidad de Datos:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("helvetica", "", 11)
    pdf.cell(0, 6, f"- Fechas NaT (antes): {metrics.get('nat_before', 0)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 6, f"- Política: {metrics.get('policy')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if metrics.get("impute_value_used") is not None:
        pdf.cell(0, 6, f"- Valor imputado: {metrics.get('impute_value_used')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(
        0,
        6,
        f"- Filas originales: {metrics.get('rows_original')} / finales: {metrics.get('rows_final')}",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.cell(
        0,
        6,
        f"- Revenue recalculado (filas): {metrics.get('revenue_recalc', 0)}",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )

    pdf.output(pdf_path)
    print(f"[OK] PDF generado: {pdf_path}")


# ---------- CLI ----------

def main():
    ap = argparse.ArgumentParser(description="MVP: procesa CSV/Excel y exporta Excel + PDF.")
    ap.add_argument("input_csv", type=str, help="Ruta del CSV/Excel a procesar.")
    ap.add_argument("-o", "--output-xlsx", required=True, help="Ruta de salida Excel.")
    ap.add_argument("--pdf-out", required=True, help="Ruta de salida PDF.")

    ap.add_argument("--delimiter", default=",", help="Delimitador CSV (',' ';' '\\t' '|').")
    ap.add_argument("--encoding", default="utf-8", help="Encoding del archivo.")

    # mapeo de nombres de columnas (opcional)
    ap.add_argument("--col-fecha", default="order_date", help="Columna de fecha.")
    ap.add_argument("--col-categoria", default="category", help="Columna de categoría.")
    ap.add_argument("--col-region", default="region", help="Columna de región (opcional).")
    ap.add_argument("--col-revenue", default=None, help="Columna de revenue/importe (si no es 'revenue').")

    # políticas de fecha
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--drop-nat-dates", action="store_true", help="Eliminar filas con fecha NaT.")
    g.add_argument("--impute-date", choices=["median", "mean", "const"], help="Imputar fechas.")
    ap.add_argument("--impute-const", default=None, help="Valor constante YYYY-MM-DD si --impute-date const.")

    args = ap.parse_args()

    # carga
    df = cargar_csv(args.input_csv, args.delimiter, args.encoding)
    metrics: dict[str, object] = {"rows_original": len(df)}

    # política de fecha
    df_after, m_date, invalid_dates_df = aplicar_politica_fecha(
        df,
        col_fecha=args.col_fecha,
        drop_nat=args.drop_nat_dates,
        impute_mode=args.impute_date,
        impute_const=args.impute_const,
    )
    metrics.update(m_date)

    # revenue recalc si existen columnas unit_price + quantity (+discount)
    rev_col = _pick(df_after, args.col_revenue, "revenue", "Ingreso_Mensual")
    if {"unit_price", "quantity"}.issubset(df_after.columns):
        up = _to_numeric_safe(df_after["unit_price"])
        qty = _to_numeric_safe(df_after["quantity"])
        disc = _to_numeric_safe(df_after["discount"]) if "discount" in df_after.columns else 0.0
        revenue_calc = up * qty * (1 - disc)
        if rev_col is None:
            df_after["revenue"] = revenue_calc
            rev_col = "revenue"
            metrics["revenue_recalc"] = int(len(df_after))
        else:
            # ajusto sólo cuando está vacío / no numérico
            current = _to_numeric_safe(df_after[rev_col])
            mask = current.isna()
            df_after.loc[mask, rev_col] = revenue_calc.loc[mask]
            metrics["revenue_recalc"] = int(mask.sum())
    else:
        metrics["revenue_recalc"] = 0

    metrics["rows_final"] = len(df_after)

    # exportaciones
    exportar_excel(
        df_limpio=df_after,
        output_path=args.output_xlsx,
        metrics=metrics,
        invalid_dates_df=invalid_dates_df,
        col_region=args.col_region,
        col_categoria=args.col_categoria,
        col_revenue=rev_col,
    )
    exportar_pdf(df_after, args.pdf_out, metrics, col_revenue=rev_col)


if __name__ == "__main__":
    main()
