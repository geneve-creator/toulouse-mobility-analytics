import os
import pandas as pd
from sqlalchemy import create_engine

# -----------------------------------------------------------------------------
# 1. Path Definitions & Configuration
# -----------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DATA_PATH = os.path.join(BASE_DIR, "data", "raw", "comptage-velo-eco-counter.csv")
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")
DB_PATH = os.path.join(PROCESSED_DIR, "mobility_toulouse.db")


def run_etl():
    """Executes the ETL pipeline for Toulouse bicycle traffic data.

    Extracts raw CSV data, cleans and standardizes variables, builds a Star
    Schema model (Fact and Dimension tables), and exports the output to both
    SQLite database and processed CSV files.
    """
    # Verify raw file presence with fallback check
    if not os.path.exists(RAW_DATA_PATH):
        alt_path = os.path.join(BASE_DIR, "Data", "Raw", "comptage-velo-eco-counter.csv")
        if os.path.exists(alt_path):
            path_to_use = alt_path
        else:
            print(f"❌ Error: Raw dataset not found at {RAW_DATA_PATH}")
            return
    else:
        path_to_use = RAW_DATA_PATH

    print("🔄 [1/4] Extracting raw dataset...")
    try:
        df = pd.read_csv(path_to_use, sep=";", low_memory=False)
    except Exception:
        df = pd.read_csv(path_to_use, sep=",", low_memory=False)

    # -------------------------------------------------------------------------
    # 2. Data Cleaning & Transformation
    # -------------------------------------------------------------------------
    print("🧹 [2/4] Cleaning and standardizing variables...")

    # Standardize column names to snake_case
    df = df.rename(
        columns={
            "Id": "id_sensor",
            "Date": "fecha_hora_raw",
            "Counts": "conteo",
            "Status": "estado",
            "Travel Mode": "modo_transporte",
            "Direction": "direccion_codigo",
            "Direction name": "nombre_direccion",
        }
    )

    # Fix known typos in direction/street names
    df["nombre_direccion"] = df["nombre_direccion"].str.replace(
        "Ramontville", "Ramonville", regex=False
    )

    # Parse datetimes and handle missing count values
    df["fecha_hora"] = pd.to_datetime(df["fecha_hora_raw"], errors="coerce")
    df["conteo"] = df["conteo"].fillna(0).astype(int)

    # -------------------------------------------------------------------------
    # 3. Star Schema Construction
    # -------------------------------------------------------------------------
    print("🏗️ [3/4] Building Star Schema tables...")

    # A) Sensor Dimension Table
    dim_sensores = (
        df[["id_sensor", "nombre_direccion", "direccion_codigo"]]
        .drop_duplicates(subset=["id_sensor"])
        .reset_index(drop=True)
    )

    # B) Time Dimension Table
    fechas_unicas = df[["fecha_hora"]].drop_duplicates().dropna().reset_index(drop=True)

    dim_tiempo = pd.DataFrame()
    dim_tiempo["fecha_hora"] = fechas_unicas["fecha_hora"]
    dim_tiempo["anio"] = dim_tiempo["fecha_hora"].dt.year
    dim_tiempo["mes"] = dim_tiempo["fecha_hora"].dt.month
    dim_tiempo["nombre_mes"] = dim_tiempo["fecha_hora"].dt.strftime("%B")
    dim_tiempo["dia"] = dim_tiempo["fecha_hora"].dt.day
    dim_tiempo["hora"] = dim_tiempo["fecha_hora"].dt.hour
    dim_tiempo["dia_semana_num"] = dim_tiempo["fecha_hora"].dt.day_of_week  # 0=Monday, 6=Sunday
    dim_tiempo["nombre_dia"] = dim_tiempo["fecha_hora"].dt.strftime("%A")
    dim_tiempo["es_fin_de_semana"] = dim_tiempo["dia_semana_num"].isin([5, 6]).astype(int)

    # Business Logic: Rush Hour (7-9 AM & 5-7 PM on weekdays)
    is_rush_hour = dim_tiempo["hora"].isin([7, 8, 17, 18])
    is_weekday = dim_tiempo["es_fin_de_semana"] == 0
    dim_tiempo["es_horario_pico"] = (is_rush_hour & is_weekday).astype(int)

    # C) Fact Table
    fact_comptages = df[["id_sensor", "fecha_hora", "conteo"]].copy()
    fact_comptages = fact_comptages.dropna(subset=["fecha_hora"])

    # -------------------------------------------------------------------------
    # 4. Data Storage & Export
    # -------------------------------------------------------------------------
    print("💾 [4/4] Storing in SQLite database and exporting CSV files...")

    target_dir = os.path.dirname(DB_PATH)
    os.makedirs(target_dir, exist_ok=True)

    engine = create_engine(f"sqlite:///{DB_PATH}")

    # Load tables into SQLite
    fact_comptages.to_sql("fact_comptages", engine, if_exists="replace", index=False)
    dim_sensores.to_sql("dim_sensores", engine, if_exists="replace", index=False)
    dim_tiempo.to_sql("dim_tiempo", engine, if_exists="replace", index=False)

    # Export clean CSV backups
    fact_comptages.to_csv(os.path.join(target_dir, "fact_comptages.csv"), index=False)
    dim_sensores.to_csv(os.path.join(target_dir, "dim_sensores.csv"), index=False)
    dim_tiempo.to_csv(os.path.join(target_dir, "dim_tiempo.csv"), index=False)

    print("\n🎉 ETL pipeline executed successfully!")
    print(f"   - SQLite Database created at: {DB_PATH}")
    print(f"   - Fact Table records processed: {len(fact_comptages):,}")
    print(f"   - Unique sensors identified: {len(dim_sensores)}")


if __name__ == "__main__":
    run_etl()