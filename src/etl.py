import os
import pandas as pd
from sqlalchemy import create_engine

# 1. Definición de Rutas (usamos 'data' o 'Data' según como renombraste tu carpeta)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DATA_PATH = os.path.join(BASE_DIR, "data", "raw", "comptage-velo-eco-counter.csv")
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")
DB_PATH = os.path.join(PROCESSED_DIR, "mobility_toulouse.db")

def ejecutar_etl():
    if not os.path.exists(RAW_DATA_PATH):
        # Intento fallback si la carpeta se llama Data con mayúscula
        alt_path = os.path.join(BASE_DIR, "Data", "Raw", "comptage-velo-eco-counter.csv")
        if os.path.exists(alt_path):
            path_to_use = alt_path
        else:
            print(f"❌ Error: No se encontró el archivo en {RAW_DATA_PATH}")
            return
    else:
        path_to_use = RAW_DATA_PATH

    print("🔄 [1/4] Leyendo dataset crudo...")
    try:
        df = pd.read_csv(path_to_use, sep=";", low_memory=False)
    except Exception:
        df = pd.read_csv(path_to_use, sep=",", low_memory=False)

    # 2. Limpieza y estandarización
    print("🧹 [2/4] Limpiando y transformando variables...")
    
    # Renombrar columnas a formato snake_case
    df = df.rename(columns={
        "Id": "id_sensor",
        "Date": "fecha_hora_raw",
        "Counts": "conteo",
        "Status": "estado",
        "Travel Mode": "modo_transporte",
        "Direction": "direccion_codigo",
        "Direction name": "nombre_direccion"
    })

    # Corrección de typos en nombres de calles/direcciones
    df["nombre_direccion"] = df["nombre_direccion"].str.replace("Ramontville", "Ramonville", regex=False)

    # Convertir a datetime y manejar zona horaria
    df["fecha_hora"] = pd.to_datetime(df["fecha_hora_raw"], errors="coerce")
    
    # Tratar nulos en conteos
    df["conteo"] = df["conteo"].fillna(0).astype(int)

    # 3. Construcción del Modelo Estrella (Star Schema)
    print("🏗️ [3/4] Generando Tablas del Modelo Estrella...")

    # A) Dimensión Sensores / Ubicaciones
    dim_sensores = df[["id_sensor", "nombre_direccion", "direccion_codigo"]].drop_duplicates(subset=["id_sensor"]).reset_index(drop=True)

    # B) Dimensión Tiempo
    fechas_unicas = df[["fecha_hora"]].drop_duplicates().dropna().reset_index(drop=True)
    
    dim_tiempo = pd.DataFrame()
    dim_tiempo["fecha_hora"] = fechas_unicas["fecha_hora"]
    dim_tiempo["anio"] = dim_tiempo["fecha_hora"].dt.year
    dim_tiempo["mes"] = dim_tiempo["fecha_hora"].dt.month
    dim_tiempo["nombre_mes"] = dim_tiempo["fecha_hora"].dt.strftime("%B")
    dim_tiempo["dia"] = dim_tiempo["fecha_hora"].dt.day
    dim_tiempo["hora"] = dim_tiempo["fecha_hora"].dt.hour
    dim_tiempo["dia_semana_num"] = dim_tiempo["fecha_hora"].dt.day_of_week  # 0=Lunes, 6=Domingo
    dim_tiempo["nombre_dia"] = dim_tiempo["fecha_hora"].dt.strftime("%A")
    dim_tiempo["es_fin_de_semana"] = dim_tiempo["dia_semana_num"].isin([5, 6]).astype(int)
    
    # Regla de negocio: Horario Pico Laboral (7-9 hs y 17-19 hs en días hábiles)
    es_hora_pico = dim_tiempo["hora"].isin([7, 8, 17, 18])
    es_dia_habil = dim_tiempo["es_fin_de_semana"] == 0
    dim_tiempo["es_horario_pico"] = (es_hora_pico & es_dia_habil).astype(int)

    # C) Tabla de Hechos (Fact Table)
    fact_comptages = df[["id_sensor", "fecha_hora", "conteo"]].copy()
    fact_comptages = fact_comptages.dropna(subset=["fecha_hora"])

    # 4. Almacenamiento en SQLite
    print("💾 [4/4] Almacenando en base de datos SQLite y exportando CSVs...")
    
    target_dir = os.path.dirname(DB_PATH)
    os.makedirs(target_dir, exist_ok=True)

    engine = create_engine(f"sqlite:///{DB_PATH}")

    fact_comptages.to_sql("fact_comptages", engine, if_exists="replace", index=False)
    dim_sensores.to_sql("dim_sensores", engine, if_exists="replace", index=False)
    dim_tiempo.to_sql("dim_tiempo", engine, if_exists="replace", index=False)

    # Exportar copia en CSV limpio a processed
    fact_comptages.to_csv(os.path.join(target_dir, "fact_comptages.csv"), index=False)
    dim_sensores.to_csv(os.path.join(target_dir, "dim_sensores.csv"), index=False)
    dim_tiempo.to_csv(os.path.join(target_dir, "dim_tiempo.csv"), index=False)

    print(f"\n🎉 ¡ETL finalizado con éxito!")
    print(f"   - Base de datos SQLite creada en: {DB_PATH}")
    print(f"   - Registros procesados en Fact Table: {len(fact_comptages)}")
    print(f"   - Sensores identificados: {len(dim_sensores)}")

if __name__ == "__main__":
    ejecutar_etl()