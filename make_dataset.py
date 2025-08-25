r"""
Generador de dataset sintético para el MVP.

Uso (PowerShell):
    python .\make_dataset.py --rows 150 --pct-missing-dates 0.05

Salida:
    .\data\mvp_dataset_ventas_light_150.csv
"""
import argparse
import os
from datetime import datetime, timedelta
import random
import numpy as np
import pandas as pd

PRODUCTS = [
    ("P200", "Teclado"),
    ("P201", "Mouse"),
    ("P202", "Monitor"),
    ("P203", "Notebook"),
    ("P204", "Impresora"),
    ("P205", "Parlantes"),
    ("P206", "Auriculares"),
    ("P207", "Dock"),
    ("P208", "Tablet"),
    ("P209", "Silla Gamer"),
    ("P230", "Hub USB"),
    ("P243", "Router"),
    ("P252", "Micrófono"),
]

REGIONES = ["Norte", "Sur", "Centro", "LATAM"]
CATEGORIES = ["Audio", "Cómputo", "Accesorios", "Periféricos", "Redes"]


def build_dataframe(n_rows: int, pct_missing_dates: float, seed: int | None = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    start = datetime(2020, 1, 1)
    end = datetime(2025, 9, 1)
    delta_days = (end - start).days

    rows = []
    for i in range(n_rows):
        order_id = f"OD{10000+i}"
        customer_id = f"C{rng.integers(1000, 1200)}"
        region = rng.choice(REGIONES)
        product_id, product_name = random.choice(PRODUCTS)
        category = rng.choice(CATEGORIES)
        unit_price = round(float(rng.uniform(100, 900)), 2)
        quantity = int(rng.integers(1, 15))
        discount = round(float(rng.choice([0, 0.05, 0.10, 0.20])), 2)
        revenue = round(unit_price * quantity * (1 - discount), 2)
        status = rng.choice(["Completado", "Pendiente", "Cancelado"])

        # fecha en ventana
        order_date = start + timedelta(days=int(rng.integers(0, delta_days)))
        # a veces guardo como string con tiempo, a veces solo fecha
        if rng.random() < 0.4:
            order_date_val = order_date.strftime("%Y-%m-%d %H:%M:%S")
        else:
            order_date_val = order_date.strftime("%Y-%m-%d")

        rows.append(
            dict(
                order_id=order_id,
                order_date=order_date_val,
                customer_id=customer_id,
                region=region,
                product_id=product_id,
                product_name=product_name,
                category=category,
                unit_price=unit_price,
                quantity=quantity,
                discount=discount,
                revenue=revenue,
                status=status,
            )
        )

    df = pd.DataFrame(rows)

    # introducir faltantes de fecha
    n_missing = int(round(n_rows * float(pct_missing_dates)))
    if n_missing > 0:
        idx = rng.choice(df.index.to_numpy(), size=n_missing, replace=False)
        df.loc[idx, "order_date"] = None

    return df


def main():
    ap = argparse.ArgumentParser(description="Genera dataset sintético de ventas para el MVP.")
    ap.add_argument("--rows", type=int, default=150, help="Cantidad de filas a generar.")
    ap.add_argument("--pct-missing-dates", type=float, default=0.05, help="Proporción de fechas vacías.")
    args = ap.parse_args()

    df = build_dataframe(args.rows, args.pct_missing_dates)

    os.makedirs("data", exist_ok=True)
    out_path = os.path.join("data", "mvp_dataset_ventas_light_150.csv")
    df.to_csv(out_path, index=False, encoding="utf-8")

    print(f"[OK] CSV generado: {os.path.abspath(out_path)}  ({len(df)} filas)")
    print(df.head(8))


if __name__ == "__main__":
    main()
