"""
compliance_engine.py — Límites legales presupuestarios
=======================================================
Restricciones normativas aplicables al presupuesto de personal:

  Límite 1: Contrata ≤ 40% de Planta
  Límite 2: Honorarios (215-21-03-001) ≤ 10% de Planta

Aplica sobre: Presupuesto inicial, Presupuesto vigente, Devengado acumulado.

Fuente: Ley N° 18.834 (Estatuto Administrativo), Art. 9°
        Glosas anuales de la Ley de Presupuestos del Sector Público.
"""

from __future__ import annotations
from dataclasses import dataclass
import pandas as pd

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

ITEM_PLANTA    = "PERSONAL DE PLANTA"
ITEM_CONTRATA  = "PERSONAL A CONTRATA"
ITEM_HONOR_PAD = "OTRAS REMUNERACIONES"
ASIG_HONOR     = "HONORARIOS A LA SUMA ALZADA  PERSONAS NATURALES"
COD_HONOR      = "215-21-03-001"

LIMITE_CONTRATA = 0.40
LIMITE_HONOR    = 0.10

COLS_MEDICION = [
    "PRESUPUESTO_INICIAL",
    "PRESUPUESTO_VIGENTE",
    "DEVENGADO_ACUMULADO",
]


# ---------------------------------------------------------------------------
# Dataclass de resultado
# ---------------------------------------------------------------------------

@dataclass
class ResultadoLimite:
    anio: int
    mes_cierre: int
    limite_nombre: str
    limite_pct: float
    columna: str
    valor_planta: float
    valor_restringido: float
    maximo_permitido: float
    ratio_actual: float
    exceso: float
    vulnerado: bool


# ---------------------------------------------------------------------------
# Máscaras de identificación de cuentas
# ---------------------------------------------------------------------------

def _mask_planta(df: pd.DataFrame) -> pd.Series:
    return df["Ítem_Nombre"] == ITEM_PLANTA


def _mask_contrata(df: pd.DataFrame) -> pd.Series:
    return df["Ítem_Nombre"] == ITEM_CONTRATA


def _mask_honorarios(df: pd.DataFrame) -> pd.Series:
    if "CODIGO_CUENTA" in df.columns:
        por_codigo = df["CODIGO_CUENTA"].astype(str).str.startswith(COD_HONOR)
        if por_codigo.any():
            return por_codigo
    return (
        (df["Ítem_Nombre"] == ITEM_HONOR_PAD) &
        (df["Asignación_Nombre"].str.contains("HONORARIOS A LA SUMA ALZADA", na=False))
    )


# ---------------------------------------------------------------------------
# Diagnóstico histórico
# ---------------------------------------------------------------------------

def diagnosticar_historico(
    df: pd.DataFrame,
    cols: list[str] | None = None,
) -> list[ResultadoLimite]:
    """
    Calcula el cumplimiento de los límites legales para cada cierre mensual.
    """
    if cols is None:
        cols = COLS_MEDICION

    resultados = []
    cierres = (
        df[["anio", "mes_cierre"]]
        .drop_duplicates()
        .sort_values(["anio", "mes_cierre"])
    )

    for _, cierre in cierres.iterrows():
        anio = int(cierre["anio"])
        mes  = int(cierre["mes_cierre"])
        df_c = df[(df["anio"] == anio) & (df["mes_cierre"] == mes)]

        mask_p = _mask_planta(df_c)
        mask_c = _mask_contrata(df_c)
        mask_h = _mask_honorarios(df_c)

        for col in cols:
            if col not in df_c.columns:
                continue

            val_planta   = df_c.loc[mask_p, col].sum()
            val_contrata = df_c.loc[mask_c, col].sum()
            val_honor    = df_c.loc[mask_h, col].sum()

            if val_planta == 0:
                continue

            max_contrata = val_planta * LIMITE_CONTRATA
            resultados.append(ResultadoLimite(
                anio=anio, mes_cierre=mes,
                limite_nombre="Contrata / Planta",
                limite_pct=LIMITE_CONTRATA,
                columna=col,
                valor_planta=val_planta,
                valor_restringido=val_contrata,
                maximo_permitido=max_contrata,
                ratio_actual=val_contrata / val_planta,
                exceso=max(val_contrata - max_contrata, 0),
                vulnerado=val_contrata > max_contrata,
            ))

            max_honor = val_planta * LIMITE_HONOR
            resultados.append(ResultadoLimite(
                anio=anio, mes_cierre=mes,
                limite_nombre="Honorarios / Planta",
                limite_pct=LIMITE_HONOR,
                columna=col,
                valor_planta=val_planta,
                valor_restringido=val_honor,
                maximo_permitido=max_honor,
                ratio_actual=val_honor / val_planta,
                exceso=max(val_honor - max_honor, 0),
                vulnerado=val_honor > max_honor,
            ))

    return resultados


def historico_a_df(resultados: list[ResultadoLimite]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "anio":               r.anio,
            "mes_cierre":         r.mes_cierre,
            "limite":             r.limite_nombre,
            "columna":            r.columna,
            "valor_planta":       r.valor_planta,
            "valor_restringido":  r.valor_restringido,
            "maximo_permitido":   r.maximo_permitido,
            "ratio_actual_%":     r.ratio_actual * 100,
            "exceso":             r.exceso,
            "vulnerado":          r.vulnerado,
        }
        for r in resultados
    ])


# ---------------------------------------------------------------------------
# Techo legal para escenario A
# ---------------------------------------------------------------------------

def calcular_techo_legal(
    df: pd.DataFrame,
    anio_base: int,
    anios_proyeccion: list[int],
    ppto_planta_por_anio: dict[int, float] | None = None,
) -> dict[str, dict[int, float]]:
    """
    Calcula el presupuesto máximo permitido por norma para cada año.

    Retorna:
        {
          "PERSONAL DE PLANTA":  {anio: monto},
          "PERSONAL A CONTRATA": {anio: max_contrata},
          "HONORARIOS":          {anio: max_honor},
        }
    """
    df_base = df[df["anio"] == anio_base]
    if not df_base.empty:
        mes_max = df_base["mes_cierre"].max()
        df_ult  = df_base[df_base["mes_cierre"] == mes_max]
        ppto_planta_base = df_ult.loc[_mask_planta(df_ult), "PRESUPUESTO_VIGENTE"].sum()
    else:
        ppto_planta_base = 0.0

    todos_anios = [anio_base] + anios_proyeccion
    resultado: dict[str, dict[int, float]] = {
        ITEM_PLANTA:   {},
        ITEM_CONTRATA: {},
        "HONORARIOS":  {},
    }

    for anio in todos_anios:
        if ppto_planta_por_anio and anio in ppto_planta_por_anio:
            ppto_planta = ppto_planta_por_anio[anio]
        else:
            ppto_planta = ppto_planta_base

        resultado[ITEM_PLANTA][anio]   = ppto_planta
        resultado[ITEM_CONTRATA][anio] = ppto_planta * LIMITE_CONTRATA
        resultado["HONORARIOS"][anio]  = ppto_planta * LIMITE_HONOR

    return resultado


# ---------------------------------------------------------------------------
# Verificación de proyección contra límites
# ---------------------------------------------------------------------------

def verificar_proyeccion(
    df_proy: pd.DataFrame,
    techo: dict[str, dict[int, float]],
) -> pd.DataFrame:
    """
    Contrasta la proyección anual con los techos legales.

    df_proy debe ser la salida de resumen_anual_total(), con columnas:
        cuenta, anio, monto_anual

    Si se pasa un DataFrame con monto_mensual (salida directa de
    proyectar_escenario), lo agrega automáticamente por año.

    Retorna DataFrame con columnas:
        anio, cuenta, monto_proyectado, techo_legal, ratio_%, exceso, vulnerado
    """
    # Detección defensiva: si no tiene monto_anual, agregar desde monto_mensual
    if "monto_anual" not in df_proy.columns:
        if "monto_mensual" in df_proy.columns:
            df_proy = (
                df_proy
                .groupby(["cuenta", "anio"])["monto_mensual"]
                .sum()
                .reset_index()
                .rename(columns={"monto_mensual": "monto_anual"})
            )
        else:
            return pd.DataFrame()

    filas = []
    mapa_techo = {
        ITEM_CONTRATA:  ITEM_CONTRATA,
        ITEM_HONOR_PAD: "HONORARIOS",
    }

    for anio in sorted(df_proy["anio"].unique()):
        df_a = df_proy[df_proy["anio"] == anio]

        for cuenta_proy, clave_techo in mapa_techo.items():
            monto_proy = df_a[df_a["cuenta"] == cuenta_proy]["monto_anual"].sum()
            techo_val  = techo.get(clave_techo, {}).get(anio, None)
            if techo_val is None:
                continue
            exceso = max(monto_proy - techo_val, 0)
            filas.append({
                "anio":             anio,
                "cuenta":           cuenta_proy,
                "monto_proyectado": monto_proy,
                "techo_legal":      techo_val,
                "ratio_%":          monto_proy / techo_val * 100 if techo_val > 0 else 0,
                "exceso":           exceso,
                "vulnerado":        exceso > 0,
            })

    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------
# Resumen de vulneraciones históricas
# ---------------------------------------------------------------------------

def resumen_vulneraciones(df_hist: pd.DataFrame) -> pd.DataFrame:
    """Agrega el historial de vulneraciones por año, límite y columna."""
    return (
        df_hist
        .groupby(["anio", "limite", "columna"])
        .agg(
            meses_vulnerados=("vulnerado", "sum"),
            meses_totales=("vulnerado", "count"),
            ratio_max=("ratio_actual_%", "max"),
            ratio_min=("ratio_actual_%", "min"),
            exceso_max=("exceso", "max"),
        )
        .reset_index()
        .sort_values(["anio", "limite", "columna"])
    )
