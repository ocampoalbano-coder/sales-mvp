# app/core/procesamiento.py
from __future__ import annotations
import csv
from typing import Dict, Tuple, Optional, List
import numpy as np
import pandas as pd

# ---------- Detección de CSV (delimitador/encoding/fechas) ----------

def _sniff_delimiter(sample: bytes) -> Optional[str]:
    try:
        dialect = csv.Sniffer().sniff(sample.decode("utf-8", errors="ignore"), delimiters=[",",";","|","\t"])
        return dialect.delimiter
    except Exception:
        return None

def _detect_encoding(sample: bytes) -> str:
    try:
        sample.decode("utf-8")
        return "utf-8"
    except Exception:
        return "latin-1"

def cargar_csv(stream, delimiter: Optional[str]=None) -> Tuple[pd.DataFrame, Dict[str,str]]:
    """Carga un CSV con autodetección de delimitador/encoding y reintento dayfirst."""
    head = stream.read(65536)
    stream.seek(0)
    encoding = _detect_encoding(head)
    delim = delimiter or _sniff_delimiter(head) or ","

    df = pd.read_csv(stream, sep=delim, encoding=encoding)  # intento base
    df = _parsear_fechas_heuristico(df, dayfirst=False)
    if _porcentaje_nat_fechas(df) > 0.4:
        stream.seek(0)
        df = pd.read_csv(stream, sep=delim, encoding=encoding)
        df = _parsear_fechas_heuristico(df, dayfirst=True)

    meta = {"delimiter": delim, "encoding": encoding}
    return df, meta

def _porcentaje_nat_fechas(df: pd.DataFrame) -> float:
    fechas = [c for c in df.columns if "fecha" in c.lower()]
    if not fechas:
        return 0.0
    total = nat = 0
    for c in fechas:
        s = pd.to_datetime(df[c], errors="coerce")
        total += len(s)
        nat += s.isna().sum()
    return nat / total if total else 0.0

def _parsear_fechas_heuristico(df: pd.DataFrame, dayfirst: bool) -> pd.DataFrame:
    for c in df.columns:
        lc = c.lower()
        if any(k in lc for k in ["fecha", "date", "registro"]):
            df[c] = pd.to_datetime(df[c], errors="coerce", dayfirst=dayfirst)
    return df

# ------------------- Limpieza / Validaciones / Orden -------------------

def limpiar_y_validar(df: pd.DataFrame):
    df = df.copy()
    # Normaliza encabezados
    df.columns = [c.strip().replace(" ", "_").replace("\t"," ").replace("\n"," ") for c in df.columns]
    # Tipos convenientes
    for c in ["ID","Edad","Ingreso_Mensual","Puntaje"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    if "Suscripcion_Activa" in df.columns:
        # Mapea strings comunes a boolean
        m = {"true": True, "1": True, "t": True, "yes": True, "y": True, "si": True, "sí": True,
             "false": False, "0": False, "f": False, "no": False}
        df["Suscripcion_Activa"] = (
            df["Suscripcion_Activa"].astype(str).str.strip().str.lower().map(m).astype("boolean")
        )

    # Validaciones
    val = {"duplicados_por_id": "OK", "edades_fuera": "OK", "ingresos_invalidos": "OK", "filas_nan": "OK"}
    if "ID" in df.columns:
        dup = df[df["ID"].duplicated(keep=False)]
        if not dup.empty: val["duplicados_por_id"] = dup
    if "Edad" in df.columns:
        bad = df[(df["Edad"] < 0) | (df["Edad"] > 120)]
        if not bad.empty: val["edades_fuera"] = bad
    if "Ingreso_Mensual" in df.columns:
        inv = df[(df["Ingreso_Mensual"].isna()) | (df["Ingreso_Mensual"] <= 0)]
        if not inv.empty: val["ingresos_invalidos"] = inv
    nan_rows = df[df.isna().any(axis=1)].head(50)
    if not nan_rows.empty:
        val["filas_nan"] = nan_rows

    # Limpieza simple
    df.dropna(how="all", inplace=True)
    df.drop_duplicates(inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df, val

def _orden_bool_true_first(s: pd.Series) -> pd.Series:
    order = s.astype("boolean")
    return (~order.fillna(False)).astype(int)  # True->0, False->1, NaN->1

def ordenar_datos(df: pd.DataFrame, col_categoria: Optional[str]=None) -> pd.DataFrame:
    df = df.copy()
    cat_col = col_categoria if col_categoria and col_categoria in df.columns else ("Categoria" if "Categoria" in df.columns else None)

    sort_cols: List[str] = []
    ascending: List[bool] = []

    if cat_col:
        df["__s0"] = df[cat_col].astype("string")
        sort_cols.append("__s0"); ascending.append(True)

    if "Suscripcion_Activa" in df.columns:
        df["__s1"] = _orden_bool_true_first(df["Suscripcion_Activa"])
        sort_cols.append("__s1"); ascending.append(True)

    if "Puntaje" in df.columns:
        df["__s2"] = -pd.to_numeric(df["Puntaje"], errors="coerce")
        sort_cols.append("__s2"); ascending.append(True)

    if "Ingreso_Mensual" in df.columns:
        df["__s3"] = -pd.to_numeric(df["Ingreso_Mensual"], errors="coerce")
        sort_cols.append("__s3"); ascending.append(True)

    if "Fecha_Registro" in df.columns:
        df["__s4"] = pd.to_datetime(df["Fecha_Registro"], errors="coerce")
        sort_cols.append("__s4"); ascending.append(True)

    if sort_cols:
        df = df.sort_values(by=sort_cols, ascending=ascending, na_position="last")
        df.drop(columns=sort_cols, inplace=True)

    return df.reset_index(drop=True)

def describir_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    try:
        desc = df.describe(include="all", datetime_is_numeric=True).T
    except TypeError:
        desc = df.describe(include="all").T
    desc.rename(columns={"25%":"p25","50%":"p50","75%":"p75"}, inplace=True)

    # Fechas: min/mediana/max/antigüedad media
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            s = pd.to_datetime(df[c], errors="coerce")
            if s.notna().any():
                desc.loc[c,"min_fecha"] = s.min()
                desc.loc[c,"mediana_fecha"] = s.median()
                desc.loc[c,"max_fecha"] = s.max()
                desc.loc[c,"antiguedad_media_dias"] = float((pd.Timestamp.now() - s).dt.days.mean())

    # IQR y CV numéricas
    for c in df.select_dtypes(include=["number"]).columns:
        s = pd.to_numeric(df[c], errors="coerce")
        q75, q25 = s.quantile(0.75), s.quantile(0.25)
        mean, std = s.mean(), s.std()
        desc.loc[c,"iqr"] = q75 - q25
        desc.loc[c,"cv"] = (std/mean) if mean not in (0, None, np.nan) else np.nan

    desc = desc.reset_index().rename(columns={"index":"columna"})
    return desc

def agrupar_por_categoria(df: pd.DataFrame, col_categoria: Optional[str]=None) -> pd.DataFrame:
    cat_col = col_categoria if col_categoria and col_categoria in df.columns else ("Categoria" if "Categoria" in df.columns else None)
    if not cat_col:
        return pd.DataFrame({"nota": ["No se especificó columna de categoría válida."]})

    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
    agg = {c:["sum","mean","median"] for c in numeric_cols}
    g = df.groupby(cat_col, dropna=False)
    out = g.agg(agg) if agg else g.size().to_frame("conteo")
    if agg:
        out.columns = ["_".join([c, stat]) for c, stat in out.columns]
        out.insert(0, "conteo", g.size().values)

    # porcentaje
    total = int(out["conteo"].sum())
    out["porcentaje"] = out["conteo"] / (total if total else 1)

    # Fila TOTAL
    total_row = out.sum(numeric_only=True).to_frame().T
    total_row.index = ["TOTAL"]
    out = pd.concat([out.sort_values("conteo", ascending=False), total_row], axis=0)

    return out.reset_index().rename(columns={cat_col:"Categoria"})
