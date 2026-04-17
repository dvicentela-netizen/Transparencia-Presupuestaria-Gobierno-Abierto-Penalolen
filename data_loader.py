"""
data_loader.py
==============
Carga, consolida y valida los balances de ejecución presupuestaria
(gastos e ingresos) desde archivos CSV mensuales.

Convención de nombres esperada:
    Balance_Gastos_Abril_2024.csv
    Balance_Ingresos_Enero_2026.csv

Columnas comunes (ambos tipos):
    FECHA_BALANCE, CODIGO_CUENTA,
    Título_Nombre, Subtítulo_Nombre, Ítem_Nombre,
    Asignación_Nombre, Denominación_Cuenta_Base,
    PRESUPUESTO_INICIAL, PRESUPUESTO_VIGENTE, SALDO_PRESUPUES.,
    DEVENGADO_PARCIAL, DEVENGADO_ACUMULADO

Columnas exclusivas de ingresos:
    PERCIBIDO_PARCIAL, PERCIBIDO_ACUMULADO,
    %_ACUMULADO, POR_PERCIBIR_A_LA_FECHA

Columnas exclusivas de gastos:
    OBLIGADO_PARCIAL, OBLIGADO_ACUMULADO, %_OBLIG_A_LA_FECHA,
    PAGADO_PARCIAL, PAGADO_ACUMULADO, POR_PAGAR_A_LA_FECHA
"""

import glob
import re
import logging
from pathlib import Path

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger(__name__)

# Mapa de nombres de mes en español → número
MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

# Columnas jerárquicas presentes en ambos tipos de balance
COLS_JERARQUIA = [
    "CODIGO_CUENTA",
    "Título_Nombre",
    "Subtítulo_Nombre",
    "Ítem_Nombre",
    "Asignación_Nombre",
    "Denominación_Cuenta_Base",
]

# Columnas numéricas comunes a ambos tipos
COLS_NUMERICAS_COMUNES = [
    "PRESUPUESTO_INICIAL",
    "PRESUPUESTO_VIGENTE",
    "SALDO_PRESUPUES.",
    "DEVENGADO_PARCIAL",
    "DEVENGADO_ACUMULADO",
]

COLS_NUMERICAS_INGRESOS = COLS_NUMERICAS_COMUNES + [
    "PERCIBIDO_PARCIAL",
    "PERCIBIDO_ACUMULADO",
    "POR_PERCIBIR_A_LA_FECHA",
]

COLS_NUMERICAS_GASTOS = COLS_NUMERICAS_COMUNES + [
    "OBLIGADO_PARCIAL",
    "OBLIGADO_ACUMULADO",
    "PAGADO_PARCIAL",
    "PAGADO_ACUMULADO",
    "POR_PAGAR_A_LA_FECHA",
]


# ---------------------------------------------------------------------------
# Parsing del nombre de archivo
# ---------------------------------------------------------------------------

def _parsear_nombre(ruta: Path) -> dict | None:
    """
    Extrae tipo_balance, mes y año desde el nombre del archivo.

    Patrón esperado: Balance_{Tipo}_{Mes}_{Año}.csv
    Ejemplo:         Balance_Gastos_Abril_2024.csv

    Retorna None si el nombre no coincide con el patrón.
    """
    nombre = ruta.stem  # sin extensión
    patron = re.compile(
        r"^Balance_(Gastos|Ingresos)_([A-Za-záéíóúñÁÉÍÓÚÑ]+)_(\d{4})$",
        re.IGNORECASE,
    )
    m = patron.match(nombre)
    if not m:
        log.warning(f"Archivo ignorado (nombre no reconocido): {ruta.name}")
        return None

    tipo = m.group(1).lower()          # "gastos" o "ingresos"
    mes_str = m.group(2).lower()       # "abril", "enero", etc.
    anio = int(m.group(3))

    mes_num = MESES.get(mes_str)
    if mes_num is None:
        log.warning(f"Mes no reconocido '{mes_str}' en {ruta.name}")
        return None

    return {"tipo_balance": tipo, "anio": anio, "mes_cierre": mes_num, "ruta": ruta}


# ---------------------------------------------------------------------------
# Lectura y enriquecimiento de un archivo individual
# ---------------------------------------------------------------------------

def _leer_archivo(meta: dict) -> pd.DataFrame:
    """
    Lee un CSV y añade las columnas de metadatos derivadas del nombre.
    Aplica tipado y limpieza básica.
    """
    df = pd.read_csv(meta["ruta"], dtype={"CODIGO_CUENTA": str})

    # Metadatos
    df["tipo_balance"] = meta["tipo_balance"]
    df["anio"] = meta["anio"]
    df["mes_cierre"] = meta["mes_cierre"]

    # Fecha de balance como datetime (viene como string "31/01/2026")
    df["FECHA_BALANCE"] = pd.to_datetime(
        df["FECHA_BALANCE"], dayfirst=True, errors="coerce"
    )

    # Tipado de columnas numéricas (algunos campos pueden venir con espacios o vacíos)
    cols_num = (
        COLS_NUMERICAS_INGRESOS
        if meta["tipo_balance"] == "ingresos"
        else COLS_NUMERICAS_GASTOS
    )
    for col in cols_num:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype("int64")

    # Limpieza de jerarquía: strip de espacios en columnas de texto
    for col in COLS_JERARQUIA:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    log.info(
        f"Leído: {meta['ruta'].name} → {len(df)} filas "
        f"({meta['tipo_balance']}, {meta['mes_cierre']:02d}/{meta['anio']})"
    )
    return df


# ---------------------------------------------------------------------------
# Validaciones
# ---------------------------------------------------------------------------

def _validar(df: pd.DataFrame, tipo: str) -> None:
    """
    Detecta y reporta anomalías en el DataFrame consolidado.
    No lanza excepciones; solo registra advertencias.
    """
    # Duplicados por cierre contable y cuenta
    dupes = df.duplicated(subset=["anio", "mes_cierre", "CODIGO_CUENTA"], keep=False)
    if dupes.any():
        n = dupes.sum()
        log.warning(
            f"[{tipo}] {n} filas duplicadas por (anio, mes_cierre, CODIGO_CUENTA). "
            "Puede haber archivos cargados dos veces."
        )

    # Meses esperados vs presentes (detecta huecos en la serie)
    cierres = (
        df[["anio", "mes_cierre"]]
        .drop_duplicates()
        .sort_values(["anio", "mes_cierre"])
    )
    anios = cierres["anio"].unique()
    for anio in anios:
        meses_presentes = set(
            cierres.loc[cierres["anio"] == anio, "mes_cierre"].tolist()
        )
        mes_max = max(meses_presentes)
        esperados = set(range(1, mes_max + 1))
        faltantes = esperados - meses_presentes
        if faltantes:
            meses_faltantes = sorted(faltantes)
            log.warning(
                f"[{tipo}] Año {anio}: faltan los cierres de los meses {meses_faltantes}"
            )

    log.info(f"[{tipo}] Validación completa. Cierres cargados:\n{cierres.to_string(index=False)}")


# ---------------------------------------------------------------------------
# Función principal — con caché de Streamlit
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Cargando datos presupuestarios…")
def cargar_datos(carpeta: str = "data") -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Escanea `carpeta`, carga todos los CSV con patrón Balance_*_*_*.csv
    y retorna dos DataFrames consolidados: (df_gastos, df_ingresos).

    Uso en Streamlit:
        df_gastos, df_ingresos = cargar_datos("data")

    Parámetros
    ----------
    carpeta : str
        Ruta relativa o absoluta a la carpeta que contiene los CSV.

    Retorna
    -------
    df_gastos : pd.DataFrame
        Todos los cierres de gastos concatenados, con columnas adicionales:
        tipo_balance, anio, mes_cierre, FECHA_BALANCE (datetime).

    df_ingresos : pd.DataFrame
        Ídem para ingresos.
    """
    patron = str(Path(carpeta) / "Balance_*.csv")
    archivos = sorted(glob.glob(patron))

    if not archivos:
        raise FileNotFoundError(
            f"No se encontraron archivos CSV en '{carpeta}'. "
            "Verifica la ruta y que los archivos sigan el patrón "
            "Balance_Tipo_Mes_Año.csv"
        )

    metas_gastos = []
    metas_ingresos = []

    for ruta_str in archivos:
        ruta = Path(ruta_str)
        meta = _parsear_nombre(ruta)
        if meta is None:
            continue
        if meta["tipo_balance"] == "gastos":
            metas_gastos.append(meta)
        else:
            metas_ingresos.append(meta)

    # Leer y concatenar cada tipo por separado
    df_gastos = pd.concat(
        [_leer_archivo(m) for m in metas_gastos], ignore_index=True
    ) if metas_gastos else pd.DataFrame()

    df_ingresos = pd.concat(
        [_leer_archivo(m) for m in metas_ingresos], ignore_index=True
    ) if metas_ingresos else pd.DataFrame()

    # Validar
    if not df_gastos.empty:
        _validar(df_gastos, "gastos")
    if not df_ingresos.empty:
        _validar(df_ingresos, "ingresos")

    return df_gastos, df_ingresos


# ---------------------------------------------------------------------------
# Helpers de consulta reutilizables por los módulos de visualización
# ---------------------------------------------------------------------------

def filtrar_por_anio(df: pd.DataFrame, anios: list[int]) -> pd.DataFrame:
    """Filtra el DataFrame a los años seleccionados."""
    return df[df["anio"].isin(anios)]


def filtrar_por_cierre(df: pd.DataFrame, anio: int, mes: int) -> pd.DataFrame:
    """Retorna las filas de un cierre mensual específico."""
    return df[(df["anio"] == anio) & (df["mes_cierre"] == mes)]


def serie_temporal_acumulada(
    df: pd.DataFrame,
    col_valor: str = "DEVENGADO_ACUMULADO",
    nivel: str = "Subtítulo_Nombre",
) -> pd.DataFrame:
    """
    Construye una serie temporal del valor acumulado por nivel jerárquico.

    Dado que DEVENGADO_ACUMULADO ya es acumulado desde enero,
    el valor de cada mes es directamente el punto de la serie —
    no se necesita cumsum().

    Retorna un DataFrame con columnas: anio, mes_cierre, {nivel}, {col_valor}
    útil para graficar líneas de evolución en Plotly.
    """
    return (
        df.groupby(["anio", "mes_cierre", nivel])[col_valor]
        .sum()
        .reset_index()
        .sort_values(["anio", "mes_cierre"])
    )


def resumen_jerarquico(
    df: pd.DataFrame,
    col_valor: str = "DEVENGADO_ACUMULADO",
    mes_cierre: int | None = None,
    anio: int | None = None,
) -> pd.DataFrame:
    """
    Agrega el valor por todos los niveles jerárquicos para un cierre dado.
    Si mes_cierre y anio son None, usa el cierre más reciente disponible.

    Retorna un DataFrame con la jerarquía completa lista para Treemap/Sunburst.
    """
    if anio is not None and mes_cierre is not None:
        df = filtrar_por_cierre(df, anio, mes_cierre)
    else:
        # Usar el cierre más reciente
        ultimo = df[["anio", "mes_cierre"]].drop_duplicates().sort_values(
            ["anio", "mes_cierre"]
        ).iloc[-1]
        df = filtrar_por_cierre(df, int(ultimo["anio"]), int(ultimo["mes_cierre"]))

    return (
        df.groupby(COLS_JERARQUIA)[col_valor]
        .sum()
        .reset_index()
    )


# ---------------------------------------------------------------------------
# Ejecución directa (diagnóstico sin Streamlit)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    carpeta = sys.argv[1] if len(sys.argv) > 1 else "data"
    print(f"\nCargando desde: {carpeta}\n")

    # Bypass del caché de Streamlit para ejecución directa
    df_g, df_i = cargar_datos.__wrapped__(carpeta)

    print(f"\n--- GASTOS ---")
    print(f"Filas totales : {len(df_g)}")
    print(f"Años          : {sorted(df_g['anio'].unique())}")
    print(f"Columnas      : {list(df_g.columns)}\n")

    print(f"--- INGRESOS ---")
    print(f"Filas totales : {len(df_i)}")
    print(f"Años          : {sorted(df_i['anio'].unique())}")
    print(f"Columnas      : {list(df_i.columns)}\n")
