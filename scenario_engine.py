"""
scenario_engine.py — Motor de proyección plurianual de escenarios
=================================================================
Proyecta el gasto presupuestario anual y mensual hasta 10 años,
permitiendo definir escenarios con distintas tasas de crecimiento
del presupuesto base.

Metodología:
  1. Presupuesto base: vigente del último cierre del año de referencia
  2. Crecimiento: tasa fija anual O tasas distintas por año (modo manual)
  3. Distribución mensual: % histórico de devengado parcial / ppto vigente
     (reutiliza la lógica de cashflow_engine)
  4. Hasta 3 escenarios simultáneos para comparación

Niveles de agregación disponibles: Subtítulo, Ítem, Asignación
"""

from __future__ import annotations
from dataclasses import dataclass, field
import pandas as pd
import numpy as np
from cashflow_engine import (
    _pct_mensual_por_cuenta,
    _agregar_pct_historico,
    NIVELES, MESES_ES, METODOS,
    SUPUESTO_HISTORICO, SUPUESTO_INTRA_EJERC, SUPUESTO_SIN_HISTORICO,
)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

MAX_ANIOS_PROYECCION = 10
MAX_ESCENARIOS       = 3

MODOS_CRECIMIENTO = [
    "Tasa fija anual",
    "Tasa distinta por año",
    "Monto absoluto por año",
]


# ---------------------------------------------------------------------------
# Dataclass de escenario
# ---------------------------------------------------------------------------

@dataclass
class Escenario:
    """Define un escenario de proyección plurianual."""
    nombre: str
    color: str                          # Color para el gráfico
    modo: str                           # Uno de MODOS_CRECIMIENTO
    tasa_fija: float = 0.0             # Solo si modo == "Tasa fija anual"
    tasas_por_anio: dict[int, float] = field(default_factory=dict)
    # {anio: tasa} si modo == "Tasa distinta por año"
    montos_por_anio: dict[int, float] = field(default_factory=dict)
    # {anio: ppto_total} si modo == "Monto absoluto por año"
    descripcion: str = ""


# ---------------------------------------------------------------------------
# Cálculo de presupuesto por año según escenario
# ---------------------------------------------------------------------------

def _ppto_anual_escenario(
    ppto_base: float,
    anio_base: int,
    anios_proyeccion: list[int],
    escenario: Escenario,
) -> dict[int, float]:
    """
    Calcula el presupuesto total proyectado para cada año del horizonte,
    según el modo del escenario.

    Retorna dict {anio: ppto_total}
    """
    resultado = {}

    for anio in anios_proyeccion:
        n = anio - anio_base  # años desde el base

        if escenario.modo == "Tasa fija anual":
            resultado[anio] = ppto_base * ((1 + escenario.tasa_fija) ** n)

        elif escenario.modo == "Tasa distinta por año":
            ppto = ppto_base
            for a in range(anio_base + 1, anio + 1):
                tasa = escenario.tasas_por_anio.get(a, 0.0)
                ppto *= (1 + tasa)
            resultado[anio] = ppto

        elif escenario.modo == "Monto absoluto por año":
            resultado[anio] = escenario.montos_por_anio.get(anio, ppto_base)

    return resultado


# ---------------------------------------------------------------------------
# Distribución mensual del presupuesto anual
# ---------------------------------------------------------------------------

def _distribuir_mensual(
    ppto_anual_por_cuenta: dict[str, float],
    pct_lookup: dict[tuple[str, int], float],
    pct_intra: dict[str, float],
) -> pd.DataFrame:
    """
    Distribuye el presupuesto anual de cada cuenta en los 12 meses
    usando los % históricos mensuales.

    Retorna DataFrame con columnas:
        cuenta, mes, mes_nombre, pct_usado, monto_mensual, supuesto
    """
    filas = []
    for cuenta, ppto in ppto_anual_por_cuenta.items():
        for mes in range(1, 13):
            pct = pct_lookup.get((cuenta, mes), None)

            if pct is not None:
                supuesto = SUPUESTO_HISTORICO
            elif cuenta in pct_intra:
                pct      = pct_intra[cuenta]
                supuesto = SUPUESTO_INTRA_EJERC
            else:
                pct      = 0.0
                supuesto = SUPUESTO_SIN_HISTORICO

            filas.append({
                "cuenta":       cuenta,
                "mes":          mes,
                "mes_nombre":   MESES_ES[mes],
                "pct_usado":    pct,
                "monto_mensual": pct * ppto,
                "ppto_anual":   ppto,
                "supuesto":     supuesto,
            })
    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------
# Motor principal de escenarios
# ---------------------------------------------------------------------------

def proyectar_escenario(
    df: pd.DataFrame,
    nivel: str,
    metodo: str,
    anios_historicos: list[int],
    anio_base: int,
    anios_proyeccion: list[int],
    escenario: Escenario,
    cuentas_filtro: list[str] | None = None,
    ajustes_pct_manuales: dict[tuple[str, int], float] | None = None,
) -> pd.DataFrame:
    """
    Proyecta el gasto mensual y anual para un escenario dado.

    Parámetros
    ----------
    df : DataFrame del balance de gastos
    nivel : clave de NIVELES
    metodo : método de agregación histórica
    anios_historicos : años usados como base para % mensual
    anio_base : año de referencia para presupuesto base
    anios_proyeccion : lista de años a proyectar (max 10)
    escenario : definición del escenario de crecimiento
    cuentas_filtro : lista de cuentas a incluir (None = todas)
    ajustes_pct_manuales : {(cuenta, mes): pct} overrides manuales

    Retorna
    -------
    DataFrame con columnas:
        escenario, cuenta, anio, mes, mes_nombre,
        ppto_anual, pct_usado, monto_mensual, supuesto
    """
    if ajustes_pct_manuales is None:
        ajustes_pct_manuales = {}

    col_nivel   = NIVELES[nivel]
    col_parcial = "DEVENGADO_PARCIAL"

    # --- % histórico mensual por cuenta ---
    pct_raw = _pct_mensual_por_cuenta(
        df, col_nivel, col_parcial, anios_historicos
    )
    pct_agg = _agregar_pct_historico(pct_raw, metodo)

    pct_lookup: dict[tuple[str, int], float] = {
        (r["cuenta"], r["mes_cierre"]): r["pct_esperado"]
        for _, r in pct_agg.iterrows()
    }

    # Aplicar ajustes manuales de % sobre el lookup
    for (cuenta, mes), pct_nuevo in ajustes_pct_manuales.items():
        pct_lookup[(cuenta, mes)] = pct_nuevo

    # % intra-ejercicio como fallback
    df_base_anio = df[df["anio"] == anio_base].copy()
    pct_intra: dict[str, float] = {}
    if not df_base_anio.empty:
        agg_intra = (
            df_base_anio.groupby(col_nivel)
            .agg(parcial=("DEVENGADO_PARCIAL", "sum"),
                 ppto=("PRESUPUESTO_VIGENTE", "sum"))
            .reset_index()
        )
        for _, r in agg_intra.iterrows():
            if r["ppto"] > 0:
                pct_intra[r[col_nivel]] = r["parcial"] / r["ppto"]

    # --- Presupuesto base por cuenta (último cierre del año base) ---
    df_ult = df_base_anio.copy()
    if not df_ult.empty:
        mes_max = df_ult["mes_cierre"].max()
        df_ult  = df_ult[df_ult["mes_cierre"] == mes_max]

    ppto_base_cuenta: dict[str, float] = {}
    if not df_ult.empty:
        ppto_base_cuenta = (
            df_ult.groupby(col_nivel)["PRESUPUESTO_VIGENTE"]
            .sum()
            .to_dict()
        )

    # Filtrar cuentas si aplica
    if cuentas_filtro:
        ppto_base_cuenta = {
            k: v for k, v in ppto_base_cuenta.items()
            if k in cuentas_filtro
        }

    # Presupuesto total base (suma de todas las cuentas)
    ppto_total_base = sum(ppto_base_cuenta.values())

    # --- Proyectar por año ---
    todos_anios = [anio_base] + anios_proyeccion
    ppto_anual_total = _ppto_anual_escenario(
        ppto_total_base, anio_base, todos_anios, escenario
    )

    filas_resultado = []

    for anio in todos_anios:
        ppto_total_anio = ppto_anual_total.get(anio, ppto_total_base)

        # Distribuir proporcionalmente entre cuentas
        if ppto_total_base > 0:
            ppto_cuenta_anio = {
                k: v / ppto_total_base * ppto_total_anio
                for k, v in ppto_base_cuenta.items()
            }
        else:
            ppto_cuenta_anio = {k: 0.0 for k in ppto_base_cuenta}

        # Distribuir mensualmente
        df_mes = _distribuir_mensual(
            ppto_cuenta_anio, pct_lookup, pct_intra
        )
        df_mes["anio"]      = anio
        df_mes["escenario"] = escenario.nombre
        df_mes["es_base"]   = (anio == anio_base)

        filas_resultado.append(df_mes)

    if not filas_resultado:
        return pd.DataFrame()

    df_final = pd.concat(filas_resultado, ignore_index=True)
    return df_final[[
        "escenario", "cuenta", "anio", "mes", "mes_nombre",
        "ppto_anual", "pct_usado", "monto_mensual", "supuesto", "es_base",
    ]]


# ---------------------------------------------------------------------------
# Resumen anual (para gráfico de líneas/barras)
# ---------------------------------------------------------------------------

def resumen_anual(df_proy: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega la proyección mensual al nivel anual por escenario y cuenta.
    Retorna: escenario, cuenta, anio, monto_anual, ppto_anual
    """
    return (
        df_proy
        .groupby(["escenario", "cuenta", "anio"])
        .agg(
            monto_anual=("monto_mensual", "sum"),
            ppto_anual= ("ppto_anual",    "first"),
        )
        .reset_index()
    )


def resumen_anual_total(df_proy: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega al nivel anual × escenario (suma de todas las cuentas).
    """
    return (
        df_proy
        .groupby(["escenario", "anio"])
        .agg(
            monto_anual=("monto_mensual", "sum"),
            ppto_anual= ("ppto_anual",    "sum"),
        )
        .reset_index()
    )


# ---------------------------------------------------------------------------
# Generación de reporte Markdown para escenarios
# ---------------------------------------------------------------------------

def generar_reporte_escenarios_md(
    escenarios: list[Escenario],
    df_proy_list: list[pd.DataFrame],
    nivel: str,
    metodo: str,
    anios_historicos: list[int],
    anio_base: int,
    anios_proyeccion: list[int],
    cuentas_filtro: list[str] | None,
    ajustes_pct_manuales: dict,
) -> str:
    """Genera reporte metodológico en Markdown para comparativa de escenarios."""

    lineas = [
        "# Reporte de proyección plurianual de gasto",
        "",
        "**Municipalidad de Peñalolén** — Portal de Transparencia Presupuestaria",
        "",
        "---",
        "",
        "## Parámetros generales",
        "",
        "| Parámetro | Valor |",
        "|-----------|-------|",
        f"| Nivel jerárquico | {nivel} |",
        f"| Método % mensual | {metodo} |",
        f"| Años históricos base | {', '.join(str(a) for a in sorted(anios_historicos))} |",
        f"| Año de referencia | {anio_base} |",
        f"| Horizonte de proyección | {anios_proyeccion[0]} – {anios_proyeccion[-1]} ({len(anios_proyeccion)} años) |",
        f"| Cuentas incluidas | {', '.join(cuentas_filtro) if cuentas_filtro else 'Todas'} |",
        f"| Ajustes manuales de % | {len(ajustes_pct_manuales)} |",
        "",
        "---",
        "",
        "## Escenarios definidos",
        "",
    ]

    for i, (esc, df_p) in enumerate(zip(escenarios, df_proy_list), 1):
        res = resumen_anual_total(df_p)
        lineas += [
            f"### Escenario {i}: {esc.nombre}",
            "",
            f"- **Modo de crecimiento:** {esc.modo}",
        ]
        if esc.modo == "Tasa fija anual":
            lineas.append(f"- **Tasa anual:** {esc.tasa_fija*100:+.2f}%")
        elif esc.modo == "Tasa distinta por año":
            tasas_str = ", ".join(
                f"{a}: {t*100:+.2f}%"
                for a, t in sorted(esc.tasas_por_anio.items())
            )
            lineas.append(f"- **Tasas por año:** {tasas_str}")
        elif esc.modo == "Monto absoluto por año":
            montos_str = ", ".join(
                f"{a}: ${m:,.0f}"
                for a, m in sorted(esc.montos_por_anio.items())
            )
            lineas.append(f"- **Montos por año:** {montos_str}")

        if esc.descripcion:
            lineas.append(f"- **Descripción:** {esc.descripcion}")

        lineas += ["", "**Gasto anual proyectado:**", ""]
        lineas.append("| Año | Presupuesto base | Gasto proyectado | Variación vs año base |")
        lineas.append("|-----|-----------------|------------------|----------------------|")

        ppto_base_ref = res[res["anio"] == anio_base]["ppto_anual"].sum() if anio_base in res["anio"].values else 0

        for _, row in res.sort_values("anio").iterrows():
            var = (row["monto_anual"] / ppto_base_ref - 1) * 100 if ppto_base_ref > 0 else 0
            lineas.append(
                f"| {int(row['anio'])} "
                f"| ${row['ppto_anual']:,.0f} "
                f"| ${row['monto_anual']:,.0f} "
                f"| {var:+.1f}% |"
            )
        lineas.append("")

    if ajustes_pct_manuales:
        lineas += [
            "---",
            "",
            f"## Ajustes manuales de % mensual ({len(ajustes_pct_manuales)} modificaciones)",
            "",
            "| Cuenta | Mes | % ajustado |",
            "|--------|-----|------------|",
        ]
        for (cuenta, mes), pct in sorted(ajustes_pct_manuales.items()):
            lineas.append(f"| {cuenta} | {MESES_ES[mes]} | {pct*100:.2f}% |")
        lineas.append("")

    lineas += [
        "---",
        "",
        "## Supuestos aceptados",
        "",
        "1. **Distribución mensual:** El % mensual de ejecución se calcula como "
        "`DEVENGADO_PARCIAL / PRESUPUESTO_VIGENTE` para cada cuenta y mes histórico, "
        f"agregado mediante {metodo.lower()} entre los años {', '.join(str(a) for a in sorted(anios_historicos))}.",
        "",
        "2. **Distribución del crecimiento entre cuentas:** El ajuste de presupuesto "
        "anual se distribuye proporcionalmente entre cuentas según su participación "
        f"relativa en el presupuesto vigente del año {anio_base}. "
        "Si la composición cambia (ej. nuevos cargos en planta), "
        "se recomienda ajustar los montos absolutos por cuenta manualmente.",
        "",
        "3. **Meses sin histórico:** Se usa el promedio intra-ejercicio del año "
        f"de referencia ({anio_base}) como sustituto.",
        "",
        "4. **Horizonte de incertidumbre:** Las proyecciones a más de 3 años tienen "
        "mayor incertidumbre por posibles cambios normativos, de dotación y de "
        "política presupuestaria. Se recomienda actualizar los escenarios anualmente.",
        "",
        "---",
        "",
        "## Nota metodológica general",
        "",
        "Esta proyección es una **estimación basada en comportamiento histórico y "
        "supuestos de crecimiento definidos por el usuario**. No constituye un "
        "compromiso de ejecución ni un presupuesto aprobado. Los montos se expresan "
        "en pesos chilenos (CLP) nominales, sin ajuste por inflación.",
        "",
        "---",
        "",
        "*Generado por el Portal de Transparencia Presupuestaria — "
        "Municipalidad de Peñalolén*",
    ]

    return "\n".join(lineas)


# ---------------------------------------------------------------------------
# Excel de escenarios
# ---------------------------------------------------------------------------

def generar_excel_escenarios(
    escenarios: list[Escenario],
    df_proy_list: list[pd.DataFrame],
    anio_base: int,
) -> bytes:
    """
    Excel con una hoja por escenario + hoja de comparativa anual + Léeme.
    """
    import io
    buffer = io.BytesIO()

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:

        # Hoja de comparativa anual entre escenarios
        frames_comp = []
        for esc, df_p in zip(escenarios, df_proy_list):
            res = resumen_anual_total(df_p)
            res["escenario"] = esc.nombre
            frames_comp.append(res)

        if frames_comp:
            df_comp = pd.concat(frames_comp)
            pivot_comp = df_comp.pivot_table(
                index="anio",
                columns="escenario",
                values="monto_anual",
                aggfunc="sum",
            ).reset_index()
            pivot_comp.columns.name = None
            pivot_comp.to_excel(writer, sheet_name="Comparativa anual", index=False)

        # Una hoja por escenario con detalle mensual
        for esc, df_p in zip(escenarios, df_proy_list):
            nombre_hoja = esc.nombre[:31]  # Excel limita a 31 chars
            df_export = df_p.copy()
            df_export["pct_usado_%"] = (df_export["pct_usado"] * 100).round(2)
            cols = [
                "cuenta", "anio", "mes", "mes_nombre",
                "ppto_anual", "pct_usado_%", "monto_mensual", "supuesto",
            ]
            df_export[cols].to_excel(writer, sheet_name=nombre_hoja, index=False)

        # Léeme
        leeme = pd.DataFrame([
            ("cuenta",       "Cuenta al nivel jerárquico seleccionado"),
            ("anio",         "Año proyectado"),
            ("mes",          "Número de mes (1-12)"),
            ("mes_nombre",   "Nombre del mes"),
            ("ppto_anual",   "Presupuesto anual base asignado a esta cuenta en este año (CLP)"),
            ("pct_usado_%",  "% del presupuesto anual que se ejecuta en este mes (histórico o ajustado)"),
            ("monto_mensual","Gasto mensual proyectado = pct_usado% × ppto_anual (CLP)"),
            ("supuesto",     "Fuente del %: histórico / intra-ejercicio / sin histórico / ajuste manual"),
        ], columns=["Columna", "Descripción"])
        leeme.to_excel(writer, sheet_name="Léeme", index=False)

        # Ajustar anchos
        for sheet_name in writer.sheets:
            ws = writer.sheets[sheet_name]
            for col_cells in ws.columns:
                max_len = max(
                    (len(str(c.value)) if c.value else 0 for c in col_cells),
                    default=0,
                )
                ws.column_dimensions[col_cells[0].column_letter].width = min(max_len + 4, 55)

    return buffer.getvalue()
