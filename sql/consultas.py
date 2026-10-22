import os
import pandas as pd
from sqlalchemy import create_engine

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "processed", "mobility_toulouse.db")

def ejecutar_consultas():
    if not os.path.exists(DB_PATH):
        print("❌ No se encontró la base de datos. Ejecutá primero src/etl.py")
        return

    engine = create_engine(f"sqlite:///{DB_PATH}")

    print("=== 1. TOP 5 SENSORES CON MÁS TRÁFICO TOTAL ===")
    q1 = """
    SELECT 
        COALESCE(NULLIF(s.nombre_direccion, 'UNDEFINED'), 'Sin Especificar') AS direccion,
        SUM(f.conteo) AS total_bicicletas,
        COUNT(f.fecha_hora) AS horas_registradas
    FROM fact_comptages f
    JOIN dim_sensores s ON f.id_sensor = s.id_sensor
    GROUP BY direccion
    ORDER BY total_bicicletas DESC
    LIMIT 5;
    """
    print(pd.read_sql(q1, engine).to_string(index=False))

    print("\n=== 2. DISTRIBUCIÓN DE TRÁFICO POR HORA DEL DÍA (DÍAS HÁBILES) ===")
    q2 = """
    SELECT 
        t.hora,
        SUM(f.conteo) AS total_bicicletas,
        ROUND(AVG(f.conteo), 1) AS promedio_bicis_hora
    FROM fact_comptages f
    JOIN dim_tiempo t ON f.fecha_hora = t.fecha_hora
    WHERE t.es_fin_de_semana = 0
    GROUP BY t.hora
    ORDER BY t.hora ASC;
    """
    print(pd.read_sql(q2, engine).to_string(index=False))

    print("\n=== 3. RANKING DE DIRECCIONES EN HORARIO PICO TARDE (18 A 19 HS) [WINDOW FUNCTION] ===")
    q3 = """
    WITH TráficoPico AS (
        SELECT 
            COALESCE(NULLIF(s.nombre_direccion, 'UNDEFINED'), 'Sin Especificar') AS direccion,
            SUM(f.conteo) AS total_bicis,
            RANK() OVER (ORDER BY SUM(f.conteo) DESC) as ranking
        FROM fact_comptages f
        JOIN dim_sensores s ON f.id_sensor = s.id_sensor
        JOIN dim_tiempo t ON f.fecha_hora = t.fecha_hora
        WHERE t.hora IN (18, 19) AND t.es_fin_de_semana = 0
        GROUP BY direccion
    )
    SELECT ranking, direccion, total_bicis
    FROM TráficoPico
    WHERE ranking <= 5;
    """
    print(pd.read_sql(q3, engine).to_string(index=False))

if __name__ == "__main__":
    ejecutar_consultas()