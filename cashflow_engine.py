"""
cashflow_engine.py — Motor de proyección de flujo de caja
==========================================================
Calcula proyecciones mensuales de ejecución presupuestaria basadas
en comportamiento histórico, con soporte para ajuste manual de supuestos.

Metodología:
  Gastos:   % mensual = DEVENGADO_PARCIAL / PRESUPUESTO_VIGENTE
  Ingresos: % mensual = PERCIBIDO_PARCIAL / PRESUPUESTO_VIGENTE
  Proyección = % esperado × presupuesto vigente base

Casos especiales:
  - Valores negativos en parcial: se conservan (reversiones contables válidas)
  - Cuentas sin histórico en mes dado: se usa promedio de meses disponibles
    en el mismo ejercicio y se marca como "sin histórico directo"
  - Año siguiente: presupuesto base = vigente del último cierre,
    escalado opcionalmente por factor global
  - Cuentas nuevas sin histórico en ningún año anterior: monto=0,
    marcada como "sujeta a continuidad de programa"
"""

from __future__ import annotations
import warnings
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Literal

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

NIVELES = {
    "Subtítulo": "Subtítulo_Nombre",
    "Ítem":      "Ítem_Nombre",
    "Asignación":"Asignación_Nombre",
}

METODOS = ["Promedio simple", "Promedio ponderado", "Mediana"]

MESES_ES = {
    1:"Enero", 2:"Febrero", 3:"Marzo", 4:"Abril",
    5:"Mayo", 6:"Junio", 7:"Julio", 8:"Agosto",
    9:"Septiembre", 10:"Octubre", 11:"Noviembre", 12:"Diciembre",
}

TODOS_LOS_MESES = list(range(1, 13))

# Etiquetas de supuestos
SUPUESTO_HISTORICO      = "histórico"
SUPUESTO_INTRA_EJERC   = "promedio intra-ejercicio"
SUPUESTO_SIN_HISTORICO  = "sin histórico — sujeto a continuidad"
SUPUESTO_MANUAL         = "ajuste manual"


# ---------------------------------------------------------------------------
# Dataclass de resultado por cuenta-mes
# ---------------------------------------------------------------------------

@dataclass
class CeldaProyeccion:
    """Resultado de proyección para una cuenta en un mes dado."""
    cuenta: str                   # Nombre de la cuenta al nivel elegido
    anio: int
    mes: int
    es_real: bool                 # True = dato real, False = proyectado
    valor_real: float | None      # Monto real si es_real
    pct_historico: float | None   # % calculado del histórico (puede ser None)
    pct_usado: float              # % efectivamente usado (histórico o ajustado)
    ppto_base: float              # Presupuesto vigente base usado
    monto_proyectado: float       # pct_usado × ppto_base
    supuesto: str                 # Etiqueta de supuesto (ver constantes)
    pct_ajustado_por_usuario: bool = False
    pct_original: float | None = None  # % histórico antes del ajuste manual


# ---------------------------------------------------------------------------
# Funciones de cálculo del % histórico
# ---------------------------------------------------------------------------

def _pct_mensual_por_cuenta(
    df: pd.DataFrame,
    col_nivel: str,
    col_parcial: str,
    anios_historicos: list[int],
) -> pd.DataFrame:
    """
    Calcula el % de ejecución mensual por cuenta y año histórico.

    Retorna DataFrame con columnas:
        cuenta, anio, mes_cierre, pct_mes
    donde pct_mes = parcial / presupuesto_vigente (puede ser negativo).
    """
    df_hist = df[df["anio"].isin(anios_historicos)].copy()

    agg = (
        df_hist
        .groupby([col_nivel, "anio", "mes_cierre"])
        .agg(
            parcial=  (col_parcial,          "sum"),
            ppto_vig= ("PRESUPUESTO_VIGENTE", "sum"),
        )
        .reset_index()
        .rename(columns={col_nivel: "cuenta"})
    )

    # % mensual — conservar negativos (reversiones)
    agg["pct_mes"] = agg.apply(
        lambda r: r["parcial"] / r["ppto_vig"] if r["ppto_vig"] != 0 else 0.0,
        axis=1,
    )
    return agg


def _agregar_pct_historico(
    pct_df: pd.DataFrame,
    metodo: str,
    pesos: list[float] | None = None,
) -> pd.DataFrame:
    """
    Agrega el % histórico mensual entre años usando el método elegido.

    Retorna DataFrame con columnas: cuenta, mes_cierre, pct_esperado
    """
    anios = sorted(pct_df["anio"].unique())
    n_anios = len(anios)

    if metodo == "Promedio simple":
        result = (
            pct_df
            .groupby(["cuenta", "mes_cierre"])["pct_mes"]
            .mean()
            .reset_index()
            .rename(columns={"pct_mes": "pct_esperado"})
        )

    elif metodo == "Promedio ponderado":
        # Pesos decrecientes hacia el pasado; si no se proveen, usar 50/30/20
        if pesos is None or len(pesos) != n_anios:
            raw = [2 ** i for i in range(n_anios)]
            total = sum(raw)
            pesos = [w / total for w in raw]  # más reciente = mayor peso
        peso_map = {anio: w for anio, w in zip(anios, pesos)}
        pct_df = pct_df.copy()
        pct_df["peso"] = pct_df["anio"].map(peso_map)
        pct_df["pct_pond"] = pct_df["pct_mes"] * pct_df["peso"]
        num = pct_df.groupby(["cuenta", "mes_cierre"])["pct_pond"].sum()
        den = pct_df.groupby(["cuenta", "mes_cierre"])["peso"].sum()
        result = (num / den).reset_index().rename(columns={0: "pct_esperado"})
        result.columns = ["cuenta", "mes_cierre", "pct_esperado"]

    elif metodo == "Mediana":
        result = (
            pct_df
            .groupby(["cuenta", "mes_cierre"])["pct_mes"]
            .median()
            .reset_index()
            .rename(columns={"pct_mes": "pct_esperado"})
        )
    else:
        raise ValueError(f"Método no reconocido: {metodo}")

    return result


# ---------------------------------------------------------------------------
# Presupuesto base por cuenta
# ---------------------------------------------------------------------------

def _ppto_base_por_cuenta(
    df: pd.DataFrame,
    col_nivel: str,
    anio_curso: int,
    factor_anio_siguiente: float = 1.0,
) -> dict[str, float]:
    """
    Retorna el presupuesto vigente del último cierre del año en curso,
    agregado por cuenta al nivel elegido.

    Para el año siguiente, multiplica por factor_anio_siguiente.
    """
    df_curso = df[df["anio"] == anio_curso].copy()
    if df_curso.empty:
        return {}
    mes_max = df_curso["mes_cierre"].max()
    df_ult  = df_curso[df_curso["mes_cierre"] == mes_max]

    base = (
        df_ult
        .groupby(col_nivel)["PRESUPUESTO_VIGENTE"]
        .sum()
        .to_dict()
    )
    return base


# ---------------------------------------------------------------------------
# Motor principal de proyección
# ---------------------------------------------------------------------------

def proyectar(
    df: pd.DataFrame,
    tipo_balance: Literal["Gastos", "Ingresos"],
    nivel: str,
    metodo: str,
    anios_historicos: list[int],
    anio_curso: int,
    ajustes_manuales: dict[tuple[str, int, int], float] | None = None,
    factor_anio_siguiente: float = 1.0,
) -> list[CeldaProyeccion]:
    """
    Genera la proyección completa: año en curso (real + proyectado)
    y año siguiente (totalmente proyectado).

    Parámetros
    ----------
    df : DataFrame consolidado del tipo de balance (gastos o ingresos)
    tipo_balance : "Gastos" o "Ingresos"
    nivel : clave de NIVELES ("Subtítulo", "Ítem", "Asignación")
    metodo : uno de METODOS
    anios_historicos : lista de años a usar como base histórica
    anio_curso : año presupuestario en curso
    ajustes_manuales : dict {(cuenta, anio, mes): pct_ajustado}
    factor_anio_siguiente : escalar del presupuesto base para año siguiente
                            (1.0 = sin cambio, 1.05 = +5%, etc.)

    Retorna
    -------
    Lista de CeldaProyeccion ordenada por cuenta, anio, mes
    """
    if ajustes_manuales is None:
        ajustes_manuales = {}

    col_nivel   = NIVELES[nivel]
    col_parcial = "DEVENGADO_PARCIAL" if tipo_balance == "Gastos" else "PERCIBIDO_PARCIAL"
    anio_sig    = anio_curso + 1

    # 1. Datos reales del año en curso
    df_curso  = df[df["anio"] == anio_curso].copy()
    mes_actual = int(df_curso["mes_cierre"].max()) if not df_curso.empty else 0
    meses_reales = sorted(df_curso["mes_cierre"].unique()) if not df_curso.empty else []

    # Reales por cuenta y mes
    reales_df = pd.DataFrame()
    if not df_curso.empty:
        reales_df = (
            df_curso
            .groupby([col_nivel, "mes_cierre"])
            .agg(
                parcial=  (col_parcial,           "sum"),
                ppto_vig= ("PRESUPUESTO_VIGENTE",  "sum"),
            )
            .reset_index()
            .rename(columns={col_nivel: "cuenta"})
        )

    # 2. % histórico
    pct_raw = _pct_mensual_por_cuenta(df, col_nivel, col_parcial, anios_historicos)
    pct_agg = _agregar_pct_historico(pct_raw, metodo)

    # Lookup rápido: (cuenta, mes) → pct_esperado
    pct_lookup: dict[tuple[str, int], float] = {
        (r["cuenta"], r["mes_cierre"]): r["pct_esperado"]
        for _, r in pct_agg.iterrows()
    }

    # % promedio intra-ejercicio por cuenta (fallback para meses sin histórico)
    pct_intra: dict[str, float] = {}
    if not reales_df.empty:
        for cuenta, grp in reales_df.groupby("cuenta"):
            pptos = grp["ppto_vig"].sum()
            parcs = grp["parcial"].sum()
            pct_intra[cuenta] = parcs / pptos if pptos != 0 else 0.0

    # 3. Presupuesto base por cuenta
    ppto_base_curso = _ppto_base_por_cuenta(df, col_nivel, anio_curso)
    ppto_base_sig   = {
        k: v * factor_anio_siguiente
        for k, v in ppto_base_curso.items()
    }

    # Cuentas a proyectar: unión de cuentas con histórico y con ppto
    cuentas_curso = set(ppto_base_curso.keys())
    cuentas_hist  = set(pct_agg["cuenta"].unique())
    cuentas_todas = cuentas_curso | cuentas_hist

    resultados: list[CeldaProyeccion] = []

    for cuenta in sorted(cuentas_todas):
        ppto_c = ppto_base_curso.get(cuenta, 0.0)
        ppto_s = ppto_base_sig.get(cuenta, 0.0)

        # --- Año en curso ---
        for mes in TODOS_LOS_MESES:

            if mes in meses_reales:
                # Dato real disponible
                fila = reales_df[
                    (reales_df["cuenta"] == cuenta) &
                    (reales_df["mes_cierre"] == mes)
                ]
                if fila.empty:
                    parcial_real = 0.0
                    ppto_real    = ppto_c
                else:
                    parcial_real = float(fila["parcial"].iloc[0])
                    ppto_real    = float(fila["ppto_vig"].iloc[0])

                pct_real = parcial_real / ppto_real if ppto_real != 0 else 0.0

                resultados.append(CeldaProyeccion(
                    cuenta=cuenta, anio=anio_curso, mes=mes,
                    es_real=True,
                    valor_real=parcial_real,
                    pct_historico=pct_real,
                    pct_usado=pct_real,
                    ppto_base=ppto_real,
                    monto_proyectado=parcial_real,
                    supuesto=SUPUESTO_HISTORICO,
                ))

            else:
                # Mes futuro del año en curso → proyectar
                key_manual = (cuenta, anio_curso, mes)
                pct_hist   = pct_lookup.get((cuenta, mes), None)

                if key_manual in ajustes_manuales:
                    pct_usado   = ajustes_manuales[key_manual]
                    supuesto    = SUPUESTO_MANUAL
                    ajustado    = True
                    pct_orig    = pct_hist
                elif pct_hist is not None:
                    pct_usado   = pct_hist
                    supuesto    = SUPUESTO_HISTORICO
                    ajustado    = False
                    pct_orig    = None
                elif cuenta in pct_intra:
                    # Fallback: promedio intra-ejercicio del año en curso
                    pct_usado   = pct_intra[cuenta]
                    supuesto    = SUPUESTO_INTRA_EJERC
                    ajustado    = False
                    pct_orig    = None
                else:
                    pct_usado   = 0.0
                    supuesto    = SUPUESTO_SIN_HISTORICO
                    ajustado    = False
                    pct_orig    = None

                monto = pct_usado * ppto_c

                resultados.append(CeldaProyeccion(
                    cuenta=cuenta, anio=anio_curso, mes=mes,
                    es_real=False,
                    valor_real=None,
                    pct_historico=pct_hist,
                    pct_usado=pct_usado,
                    ppto_base=ppto_c,
                    monto_proyectado=monto,
                    supuesto=supuesto,
                    pct_ajustado_por_usuario=ajustado,
                    pct_original=pct_orig,
                ))

        # --- Año siguiente (totalmente proyectado) ---
        for mes in TODOS_LOS_MESES:
            key_manual = (cuenta, anio_sig, mes)
            pct_hist   = pct_lookup.get((cuenta, mes), None)

            if key_manual in ajustes_manuales:
                pct_usado = ajustes_manuales[key_manual]
                supuesto  = SUPUESTO_MANUAL
                ajustado  = True
                pct_orig  = pct_hist
            elif pct_hist is not None:
                pct_usado = pct_hist
                supuesto  = SUPUESTO_HISTORICO
                ajustado  = False
                pct_orig  = None
            elif cuenta in pct_intra:
                pct_usado = pct_intra[cuenta]
                supuesto  = SUPUESTO_INTRA_EJERC + " — sujeto a continuidad"
                ajustado  = False
                pct_orig  = None
            else:
                pct_usado = 0.0
                supuesto  = SUPUESTO_SIN_HISTORICO
                ajustado  = False
                pct_orig  = None

            monto = pct_usado * ppto_s

            resultados.append(CeldaProyeccion(
                cuenta=cuenta, anio=anio_sig, mes=mes,
                es_real=False,
                valor_real=None,
                pct_historico=pct_hist,
                pct_usado=pct_usado,
                ppto_base=ppto_s,
                monto_proyectado=monto,
                supuesto=supuesto,
                pct_ajustado_por_usuario=ajustado,
                pct_original=pct_orig,
            ))

    return resultados


# ---------------------------------------------------------------------------
# Conversión a DataFrame para visualización
# ---------------------------------------------------------------------------

def proyeccion_a_df(celdas: list[CeldaProyeccion]) -> pd.DataFrame:
    """Convierte la lista de CeldaProyeccion a DataFrame plano."""
    return pd.DataFrame([
        {
            "cuenta":              c.cuenta,
            "anio":                c.anio,
            "mes":                 c.mes,
            "mes_nombre":          MESES_ES[c.mes],
            "es_real":             c.es_real,
            "valor_real":          c.valor_real,
            "pct_historico":       c.pct_historico,
            "pct_usado":           c.pct_usado,
            "ppto_base":           c.ppto_base,
            "monto_proyectado":    c.monto_proyectado,
            "supuesto":            c.supuesto,
            "ajustado_usuario":    c.pct_ajustado_por_usuario,
            "pct_original":        c.pct_original,
        }
        for c in celdas
    ])


# ---------------------------------------------------------------------------
# Generación de tabla de supuestos (para mostrar en UI y exportar)
# ---------------------------------------------------------------------------

def tabla_supuestos(
    df_proy: pd.DataFrame,
    anio: int,
) -> pd.DataFrame:
    """
    Retorna tabla resumen de supuestos para un año dado:
    cuenta × mes con % histórico, % usado, supuesto y flag de ajuste.
    Útil para la sección de transparencia y para el reporte exportable.
    """
    sub = df_proy[df_proy["anio"] == anio].copy()
    pivot = sub.pivot_table(
        index="cuenta",
        columns="mes_nombre",
        values="pct_usado",
        aggfunc="mean",
    )
    # Reordenar columnas por mes
    meses_orden = [MESES_ES[m] for m in range(1, 13) if MESES_ES[m] in pivot.columns]
    return pivot[meses_orden].round(4)


# ---------------------------------------------------------------------------
# Generación del reporte Markdown
# ---------------------------------------------------------------------------

def generar_reporte_md(
    df_proy: pd.DataFrame,
    tipo_balance: str,
    nivel: str,
    metodo: str,
    anios_historicos: list[int],
    anio_curso: int,
    factor_anio_siguiente: float,
    ajustes_manuales: dict,
) -> str:
    """
    Genera el reporte metodológico en formato Markdown.
    Incluye: supuestos, método, años base, log de ajustes manuales,
    tabla de % usados y nota de cuentas sujetas a continuidad.
    """
    anio_sig = anio_curso + 1
    n_ajustes = len(ajustes_manuales)
    cuentas_sin_hist = df_proy[
        df_proy["supuesto"].str.contains("sin histórico", na=False)
    ]["cuenta"].unique().tolist()

    lineas = [
        f"# Reporte de proyección de flujo de caja",
        f"",
        f"**Municipalidad de Peñalolén** — Portal de Transparencia Presupuestaria",
        f"",
        f"---",
        f"",
        f"## Parámetros de la proyección",
        f"",
        f"| Parámetro | Valor |",
        f"|-----------|-------|",
        f"| Tipo de balance | {tipo_balance} |",
        f"| Nivel jerárquico | {nivel} |",
        f"| Método de cálculo | {metodo} |",
        f"| Años históricos base | {', '.join(str(a) for a in sorted(anios_historicos))} |",
        f"| Año en curso | {anio_curso} |",
        f"| Año proyectado siguiente | {anio_sig} |",
        f"| Factor presupuesto año siguiente | {factor_anio_siguiente:.4f} ({(factor_anio_siguiente-1)*100:+.2f}%) |",
        f"| Ajustes manuales aplicados | {n_ajustes} |",
        f"",
        f"---",
        f"",
        f"## Supuestos aceptados",
        f"",
        f"1. **Presupuesto base:** El presupuesto vigente usado para proyectar corresponde "
        f"al último cierre contable cargado del año {anio_curso}. "
        f"Para el año {anio_sig}, se aplica un factor de escala de {factor_anio_siguiente:.4f} "
        f"sobre ese presupuesto, distribuyendo el cambio proporcionalmente entre cuentas "
        f"según su participación relativa en el presupuesto vigente actual.",
        f"",
        f"2. **Método de proyección ({metodo}):** El porcentaje mensual esperado "
        f"se calcula como `parcial / presupuesto_vigente` para cada cuenta y mes, "
        f"agregando entre los años históricos mediante {metodo.lower()}.",
        f"",
        f"3. **Meses sin histórico directo:** Cuando una cuenta no tiene registro "
        f"para un mes específico en los años históricos, se usa el promedio de "
        f"ejecución mensual del mismo ejercicio en curso como sustituto. "
        f"Este supuesto se marca como **'promedio intra-ejercicio'**.",
        f"",
        f"4. **Valores negativos:** Los montos negativos en ejecución parcial "
        f"corresponden a reversiones contables y se conservan tal como fueron registrados.",
        f"",
        f"5. **Año siguiente:** La proyección del año {anio_sig} asume continuidad "
        f"de todas las líneas presupuestarias del año en curso. Las cuentas sin "
        f"histórico en años anteriores se marcan explícitamente como "
        f"**'sujetas a continuidad de programa'**, ya que pueden corresponder a "
        f"obras públicas o programas que finalizan con el ejercicio vigente.",
        f"",
    ]

    if n_ajustes > 0:
        lineas += [
            f"---",
            f"",
            f"## Log de ajustes manuales ({n_ajustes} modificaciones)",
            f"",
            f"| Cuenta | Año | Mes | % histórico original | % ajustado por usuario |",
            f"|--------|-----|-----|----------------------|------------------------|",
        ]
        for (cuenta, anio, mes), pct_nuevo in sorted(ajustes_manuales.items()):
            fila_orig = df_proy[
                (df_proy["cuenta"] == cuenta) &
                (df_proy["anio"]   == anio)   &
                (df_proy["mes"]    == mes)
            ]
            pct_orig = float(fila_orig["pct_original"].iloc[0]) if not fila_orig.empty and fila_orig["pct_original"].iloc[0] is not None else None
            pct_orig_str = f"{pct_orig*100:.2f}%" if pct_orig is not None else "sin histórico"
            lineas.append(
                f"| {cuenta} | {anio} | {MESES_ES[mes]} | {pct_orig_str} | {pct_nuevo*100:.2f}% |"
            )
        lineas.append("")

    if cuentas_sin_hist:
        lineas += [
            f"---",
            f"",
            f"## Cuentas sujetas a continuidad de programa",
            f"",
            f"Las siguientes cuentas no tienen registro en años históricos anteriores. "
            f"Su proyección para el año {anio_sig} asume continuidad presupuestaria, "
            f"lo que debe validarse antes de usar esta proyección para toma de decisiones:",
            f"",
        ]
        for c in sorted(cuentas_sin_hist):
            lineas.append(f"- {c}")
        lineas.append("")

    lineas += [
        f"---",
        f"",
        f"## Nota metodológica general",
        f"",
        f"Esta proyección es una **estimación basada en comportamiento histórico** "
        f"y no constituye un compromiso de ejecución. Los montos proyectados pueden "
        f"diferir de la ejecución real por factores como modificaciones presupuestarias, "
        f"cambios en prioridades institucionales, contingencias operativas o variaciones "
        f"en la recaudación. Se recomienda actualizar la proyección mensualmente "
        f"a medida que se cargan nuevos cierres contables.",
        f"",
        f"Todos los montos se expresan en pesos chilenos (CLP).",
        f"",
        f"---",
        f"",
        f"*Generado por el Portal de Transparencia Presupuestaria — "
        f"Municipalidad de Peñalolén*",
    ]

    return "\n".join(lineas)


# ---------------------------------------------------------------------------
# Generación de Excel de descarga
# ---------------------------------------------------------------------------

def generar_excel_proyeccion(
    df_proy: pd.DataFrame,
    tipo_balance: str,
    anio_curso: int,
) -> bytes:
    """
    Genera un Excel con tres hojas:
      - Proyección: datos completos por cuenta, año y mes
      - Supuestos_%: tabla de % usados (cuenta × mes)
      - Léeme: descripción de columnas
    """
    import io
    anio_sig = anio_curso + 1
    buffer   = io.BytesIO()

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:

        # Hoja 1: proyección completa
        df_export = df_proy.copy()
        df_export["pct_usado_%"]      = (df_export["pct_usado"] * 100).round(2)
        df_export["pct_historico_%"]  = (df_export["pct_historico"] * 100).round(2)
        df_export["pct_original_%"]   = (df_export["pct_original"] * 100).round(2)

        cols_orden = [
            "cuenta", "anio", "mes", "mes_nombre",
            "es_real", "valor_real", "monto_proyectado",
            "ppto_base", "pct_historico_%", "pct_usado_%",
            "pct_original_%", "ajustado_usuario", "supuesto",
        ]
        df_export[cols_orden].to_excel(writer, sheet_name="Proyección", index=False)

        # Hoja 2: % por cuenta × mes (año en curso)
        tab_curso = tabla_supuestos(df_proy, anio_curso)
        tab_sig   = tabla_supuestos(df_proy, anio_sig)
        tab_curso.to_excel(writer, sheet_name=f"% {anio_curso}")
        tab_sig.to_excel(writer,   sheet_name=f"% {anio_sig}")

        # Hoja 3: Léeme
        leeme = pd.DataFrame([
            ("cuenta",           "Nombre de la cuenta al nivel jerárquico seleccionado"),
            ("anio",             "Año presupuestario"),
            ("mes",              "Número del mes (1=enero, 12=diciembre)"),
            ("mes_nombre",       "Nombre del mes en español"),
            ("es_real",          "TRUE = dato real del cierre contable; FALSE = proyectado"),
            ("valor_real",       "Monto real ejecutado (solo si es_real=TRUE), en CLP"),
            ("monto_proyectado", "Monto proyectado = pct_usado × ppto_base, en CLP"),
            ("ppto_base",        "Presupuesto vigente base usado para la proyección, en CLP"),
            ("pct_historico_%",  "% histórico calculado del comportamiento anterior"),
            ("pct_usado_%",      "% efectivamente usado en la proyección (puede diferir del histórico si hubo ajuste manual)"),
            ("pct_original_%",   "% histórico antes del ajuste manual (solo si ajustado_usuario=TRUE)"),
            ("ajustado_usuario", "TRUE si el % fue modificado manualmente por el usuario"),
            ("supuesto",         "Etiqueta del supuesto aplicado: 'histórico', 'promedio intra-ejercicio', 'ajuste manual', 'sin histórico — sujeto a continuidad'"),
        ], columns=["Columna", "Descripción"])
        leeme.to_excel(writer, sheet_name="Léeme", index=False)

        # Ajustar anchos
        for sheet_name in writer.sheets:
            ws = writer.sheets[sheet_name]
            for col_cells in ws.columns:
                max_len = max(
                    (len(str(cell.value)) if cell.value else 0 for cell in col_cells),
                    default=0,
                )
                ws.column_dimensions[col_cells[0].column_letter].width = min(max_len + 4, 60)

    return buffer.getvalue()
