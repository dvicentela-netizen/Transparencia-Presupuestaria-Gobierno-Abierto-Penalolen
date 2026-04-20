"""
pages/3_Detalle.py — Detalle y descarga de datos presupuestarios
=================================================================
Tabla interactiva con todos los registros del cierre seleccionado,
filtros en cascada por jerarquía presupuestaria, y descarga del
dataset completo del cierre en CSV o Excel.

Filosofía de descarga:
  El archivo exportado contiene el dataset completo del cierre
  seleccionado (sin filtros), para maximizar la reutilización
  ciudadana. Los filtros en pantalla son solo para exploración.

Columnas exportadas:
  Comunes:  FECHA_BALANCE, CODIGO_CUENTA, jerarquía (5 cols),
            PRESUPUESTO_INICIAL, PRESUPUESTO_VIGENTE, SALDO_PRESUPUES.,
            DEVENGADO_PARCIAL, DEVENGADO_ACUMULADO, tipo_balance, anio, mes_cierre
  Gastos:   + OBLIGADO_PARCIAL, OBLIGADO_ACUMULADO, %_OBLIG_A_LA_FECHA,
              PAGADO_PARCIAL, PAGADO_ACUMULADO, POR_PAGAR_A_LA_FECHA
  Ingresos: + PERCIBIDO_PARCIAL, PERCIBIDO_ACUMULADO,
              %_ACUMULADO, POR_PERCIBIR_A_LA_FECHA
"""

import io
import streamlit as st
import pandas as pd

from data_loader import cargar_datos

# ---------------------------------------------------------------------------
# Paleta institucional
# ---------------------------------------------------------------------------

COLOR_PRINCIPAL = "#0250C0"
COLOR_OSCURO    = "#222957"
COLOR_ACENTO    = "#FF8500"
COLOR_AUXILIAR  = "#3A5694"
COLOR_BLANCO    = "#FFFFFF"
COLOR_FONDO     = "#F5F7FC"
COLOR_BARRA     = "#D6E4F7"
COLOR_TEXTO     = "#1E1E1E"

# ---------------------------------------------------------------------------
# Configuración de página
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Detalle y Descarga · Peñalolén",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

st.markdown(f"""
<style>
[data-testid="stAppViewContainer"] {{
        background-color: #FFFFFF;
    }}
    [data-testid="stSidebar"] {{ background-color: {COLOR_OSCURO}; }}
    [data-testid="stSidebar"] * {{ color: {COLOR_BLANCO} !important; }}
    [data-testid="stSelectbox"] label p {{
        color: {COLOR_OSCURO} !important;
        font-weight: 600; 
    }}

    .header-strip {{
        background: linear-gradient(90deg, {COLOR_OSCURO} 0%, {COLOR_PRINCIPAL} 100%);
        border-radius: 10px; padding: 22px 32px 18px 32px; margin-bottom: 24px;
    }}
    .header-strip h1 {{
        font-size: 1.45rem; font-weight: 700; margin: 0 0 4px 0; color: {COLOR_BLANCO};
    }}
    .header-strip p {{ font-size: 0.88rem; margin: 0; opacity: 0.82; color: {COLOR_BLANCO}; }}

    .seccion {{
        font-size: 0.78rem; font-weight: 700; text-transform: uppercase;
        letter-spacing: 0.08em; color: {COLOR_AUXILIAR};
        border-bottom: 2px solid {COLOR_BARRA};
        padding-bottom: 5px; margin: 22px 0 14px 0;
    }}

    .descarga-box {{
        background: {COLOR_FONDO}; border: 1.5px solid #C9D6EE;
        border-radius: 10px; padding: 20px 24px; margin-bottom: 8px;
    }}
    .descarga-title {{
        font-size: 0.9rem; font-weight: 700; color: {COLOR_OSCURO}; margin-bottom: 6px;
    }}
    .descarga-sub {{
        font-size: 0.8rem; color: #555; margin-bottom: 14px; line-height: 1.5;
    }}

    .filtros-box {{
        background: {COLOR_OSCURO}; border: 1px solid #DDE4F0;
        border-radius: 10px; padding: 16px 20px; margin-bottom: 20px;
    }}

    .stat-pill {{
        display: inline-block; background: #E8F0FE; color: {COLOR_PRINCIPAL};
        font-size: 0.78rem; font-weight: 600; padding: 3px 10px;
        border-radius: 12px; margin-right: 6px; margin-bottom: 4px;
    }}
    .stat-pill.naranja {{ background: #FFF3E0; color: #8B4A00; }}
    .stat-pill.verde   {{ background: #E6F4EA; color: #1B6B30; }}

    .nota {{
        background: #EEF2FB; border-radius: 7px; padding: 11px 16px;
        font-size: 0.79rem; color: #333; line-height: 1.6; margin-top: 12px;
    }}
    .nota b {{ color: {COLOR_OSCURO}; }}

    .licencia-box {{
        background: #F0FBF4; border-left: 4px solid #1D9E75;
        border-radius: 7px; padding: 12px 16px;
        font-size: 0.80rem; color: #0A3D26; line-height: 1.6;
        margin-top: 4px;
    }}

    .footer {{
        text-align: center; font-size: 0.73rem; color: #888;
        margin-top: 36px; padding-top: 14px; border-top: 1px solid #DDE4F0;
    }}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MESES_ES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
    5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
}

NOMBRE_COLS_DISPLAY = {
    "FECHA_BALANCE":            "Fecha cierre",
    "CODIGO_CUENTA":            "Código cuenta",
    "Título_Nombre":            "Título",
    "Subtítulo_Nombre":         "Subtítulo",
    "Ítem_Nombre":              "Ítem",
    "Asignación_Nombre":        "Asignación",
    "Denominación_Cuenta_Base": "Denominación",
    "PRESUPUESTO_INICIAL":      "Ppto. inicial",
    "PRESUPUESTO_VIGENTE":      "Ppto. vigente",
    "SALDO_PRESUPUES.":         "Saldo presup.",
    "DEVENGADO_PARCIAL":        "Devengado parcial",
    "DEVENGADO_ACUMULADO":      "Devengado acum.",
    "OBLIGADO_PARCIAL":         "Obligado parcial",
    "OBLIGADO_ACUMULADO":       "Obligado acum.",
    "%_OBLIG_A_LA_FECHA":       "% obligado",
    "PAGADO_PARCIAL":           "Pagado parcial",
    "PAGADO_ACUMULADO":         "Pagado acum.",
    "POR_PAGAR_A_LA_FECHA":     "Por pagar",
    "PERCIBIDO_PARCIAL":        "Percibido parcial",
    "PERCIBIDO_ACUMULADO":      "Percibido acum.",
    "%_ACUMULADO":              "% acumulado",
    "POR_PERCIBIR_A_LA_FECHA":  "Por percibir",
}

COLS_JERARQUIA = [
    "Título_Nombre", "Subtítulo_Nombre", "Ítem_Nombre",
    "Asignación_Nombre", "Denominación_Cuenta_Base",
]


def fmt_millones(v: float) -> str:
    if abs(v) >= 1_000_000_000:
        return f"${v / 1_000_000_000:,.2f} MM"
    return f"${v / 1_000_000:,.1f} M"


def cierre_reciente(df: pd.DataFrame, anio: int) -> pd.DataFrame:
    sub = df[df["anio"] == anio]
    if sub.empty:
        return pd.DataFrame()
    return sub[sub["mes_cierre"] == sub["mes_cierre"].max()]


def nombre_archivo(tipo: str, anio: int, mes: int, ext: str) -> str:
    mes_str = MESES_ES.get(mes, str(mes))
    return f"Penalolen_Presupuesto_{tipo}_{mes_str}_{anio}.{ext}"


def df_a_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")


def df_a_excel(df_datos: pd.DataFrame, tipo: str, anio: int, mes: int) -> bytes:
    """
    Genera un Excel con dos hojas:
      - 'Datos': el dataset completo del cierre
      - 'Léeme': descripción de columnas y nota metodológica
    """
    buffer = io.BytesIO()
    mes_str = MESES_ES.get(mes, str(mes))

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:

        # Hoja 1: datos
        df_datos.to_excel(writer, sheet_name="Datos", index=False)

        # Hoja 2: léeme
        col_ejec = (
            "DEVENGADO_ACUMULADO" if tipo == "Gastos" else "PERCIBIDO_ACUMULADO"
        )
        ejec_lbl = (
            "Devengado acumulado" if tipo == "Gastos" else "Percibido acumulado"
        )
        descripcion_cols = [
            ("FECHA_BALANCE",            "Fecha del cierre contable mensual."),
            ("CODIGO_CUENTA",            "Código estructurado de la cuenta presupuestaria (formato 215-XX-XX-XXX-XXX-XXX)."),
            ("Título_Nombre",            "Nivel 1 de la jerarquía presupuestaria."),
            ("Subtítulo_Nombre",         "Nivel 2 de la jerarquía presupuestaria."),
            ("Ítem_Nombre",              "Nivel 3 de la jerarquía presupuestaria."),
            ("Asignación_Nombre",        "Nivel 4 de la jerarquía presupuestaria."),
            ("Denominación_Cuenta_Base", "Nivel 5 (más detallado) de la jerarquía presupuestaria."),
            ("PRESUPUESTO_INICIAL",      "Presupuesto aprobado al inicio del ejercicio."),
            ("PRESUPUESTO_VIGENTE",      "Presupuesto inicial más modificaciones presupuestarias aprobadas a la fecha."),
            ("SALDO_PRESUPUES.",         "Diferencia entre presupuesto vigente y lo ejecutado a la fecha."),
            ("DEVENGADO_PARCIAL",        "Monto devengado solo en el mes del cierre."),
            ("DEVENGADO_ACUMULADO",      "Suma del devengado desde el 1 de enero hasta el cierre del mes indicado."),
        ]
        if tipo == "Gastos":
            descripcion_cols += [
                ("OBLIGADO_PARCIAL",     "Monto comprometido (obligado) solo en el mes del cierre."),
                ("OBLIGADO_ACUMULADO",   "Suma del obligado desde el 1 de enero."),
                ("%_OBLIG_A_LA_FECHA",   "Porcentaje del presupuesto vigente que ha sido obligado a la fecha."),
                ("PAGADO_PARCIAL",       "Monto pagado solo en el mes del cierre."),
                ("PAGADO_ACUMULADO",     "Suma de pagos efectuados desde el 1 de enero."),
                ("POR_PAGAR_A_LA_FECHA", "Monto devengado que aún no ha sido pagado."),
            ]
        else:
            descripcion_cols += [
                ("PERCIBIDO_PARCIAL",      "Monto percibido (ingresado a caja) solo en el mes del cierre."),
                ("PERCIBIDO_ACUMULADO",    "Suma del percibido desde el 1 de enero."),
                ("%_ACUMULADO",            "Porcentaje del presupuesto vigente que ha sido percibido a la fecha."),
                ("POR_PERCIBIR_A_LA_FECHA","Monto devengado que aún no ha sido percibido."),
            ]
        descripcion_cols += [
            ("tipo_balance", "Indica si el registro corresponde a 'gastos' o 'ingresos'."),
            ("anio",         "Año presupuestario al que corresponde el cierre."),
            ("mes_cierre",   "Número del mes del cierre contable (1=enero, 12=diciembre)."),
        ]

        notas = [
            ("", ""),
            ("NOTA METODOLÓGICA", ""),
            ("Entidad",    "Municipalidad de Peñalolén"),
            ("Fuente",     "Sistema ERP contable municipal (datos oficiales)"),
            ("Período",    f"{mes_str} {anio}"),
            ("Tipo",       tipo),
            ("", ""),
            ("Ejecución presupuestaria",
             f"Una cuenta de gasto está 100% ejecutada cuando DEVENGADO_ACUMULADO = PRESUPUESTO_VIGENTE. "
             f"Una cuenta de ingreso está 100% ejecutada cuando PERCIBIDO_ACUMULADO = PRESUPUESTO_VIGENTE."),
            ("Sobrejecución",
             "Valores de ejecución >100% pueden ocurrir cuando un movimiento se registra "
             "antes de completarse la modificación presupuestaria correspondiente."),
            ("Moneda",     "Todos los montos están expresados en pesos chilenos (CLP)."),
            ("Licencia",   "Datos abiertos bajo licencia Creative Commons CC BY 4.0. "
                           "Puedes usar, compartir y adaptar con atribución a la Municipalidad de Peñalolén."),
        ]

        df_leeme = pd.DataFrame(
            [{"Columna": c, "Descripción": d} for c, d in descripcion_cols]
            + [{"Columna": c, "Descripción": d} for c, d in notas]
        )
        df_leeme.to_excel(writer, sheet_name="Léeme", index=False)

        # Autoajuste de anchos (hoja Datos)
        ws_datos = writer.sheets["Datos"]
        for col_cells in ws_datos.columns:
            max_len = max(
                len(str(cell.value)) if cell.value is not None else 0
                for cell in col_cells
            )
            ws_datos.column_dimensions[col_cells[0].column_letter].width = min(max_len + 4, 50)

        # Autoajuste (hoja Léeme)
        ws_leeme = writer.sheets["Léeme"]
        ws_leeme.column_dimensions["A"].width = 30
        ws_leeme.column_dimensions["B"].width = 90

    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Carga de datos
# ---------------------------------------------------------------------------

df_gastos, df_ingresos = cargar_datos("data")

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown(
        "<div style='padding:10px 0 18px 0'>"
        "<span style='font-size:1.1rem;font-weight:700;'>🏛️ Peñalolén</span><br>"
        "<span style='font-size:0.8rem;opacity:0.7;'>Transparencia Presupuestaria</span>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")

    tipo_sel = st.radio(
        "Tipo de balance",
        options=["Gastos", "Ingresos"],
        horizontal=True,
    )
    df_base = df_gastos if tipo_sel == "Gastos" else df_ingresos

    anios_disp = sorted(df_base["anio"].unique(), reverse=True)
    anio_sel   = st.selectbox("Año presupuestario", anios_disp, index=0)

    df_anio    = df_base[df_base["anio"] == anio_sel]
    meses_disp = sorted(df_anio["mes_cierre"].unique(), reverse=True)
    mes_opts   = {MESES_ES[m]: m for m in meses_disp}
    mes_lbl    = st.selectbox("Cierre mensual", list(mes_opts.keys()), index=0)
    mes_sel    = mes_opts[mes_lbl]

    st.markdown("---")
    st.markdown(
        "<span style='font-size:0.75rem;opacity:0.6;'>"
        "Información oficial extraída del ERP contable municipal. "
        "Actualización mensual.</span>",
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Datos del cierre seleccionado (completo, sin filtros — para descarga)
# ---------------------------------------------------------------------------

df_cierre = df_base[
    (df_base["anio"] == anio_sel) & (df_base["mes_cierre"] == mes_sel)
].copy()

if df_cierre.empty:
    st.warning(f"No hay datos disponibles para {tipo_sel} — {mes_lbl} {anio_sel}.")
    st.stop()

# Renombrar columnas para la tabla de display (no afecta la descarga)
cols_disponibles = [c for c in df_cierre.columns if c in NOMBRE_COLS_DISPLAY]
df_display = df_cierre[cols_disponibles].rename(columns=NOMBRE_COLS_DISPLAY)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.markdown(f"""
<div class="header-strip">
  <h1>🔍 Detalle y descarga — {tipo_sel}</h1>
  <p>Municipalidad de Peñalolén &nbsp;·&nbsp; Cierre {mes_lbl} {anio_sel}
     &nbsp;·&nbsp; {len(df_cierre):,} registros disponibles</p>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Sección de descarga (dataset completo del cierre)
# ---------------------------------------------------------------------------

st.markdown('<div class="seccion">Descarga de datos abiertos</div>', unsafe_allow_html=True)

st.markdown(f"""
<div class="descarga-box">
  <div class="descarga-title">Dataset completo — {tipo_sel} {mes_lbl} {anio_sel}</div>
  <div class="descarga-sub">
    El archivo descargable contiene <b>todos los registros del cierre contable</b>
    seleccionado, independientemente de los filtros aplicados en pantalla.
    El Excel incluye una hoja <b>Léeme</b> con la descripción de cada columna
    y la nota metodológica completa.
  </div>
</div>
""", unsafe_allow_html=True)

col_csv, col_xlsx = st.columns(2)

with col_csv:
    csv_bytes = df_a_csv(df_cierre)
    st.download_button(
        label="⬇ Descargar CSV",
        data=csv_bytes,
        file_name=nombre_archivo(tipo_sel, anio_sel, mes_sel, "csv"),
        mime="text/csv",
        use_container_width=True,
        help="Formato universal, compatible con Excel, Google Sheets, R, Python y cualquier software de análisis.",
    )
    st.markdown(
        "<div style='font-size:0.75rem;color:#555;margin-top:4px;'>"
        "UTF-8 con BOM · separador coma · ideal para reutilización</div>",
        unsafe_allow_html=True,
    )

with col_xlsx:
    xlsx_bytes = df_a_excel(df_cierre, tipo_sel, anio_sel, mes_sel)
    st.download_button(
        label="⬇ Descargar Excel",
        data=xlsx_bytes,
        file_name=nombre_archivo(tipo_sel, anio_sel, mes_sel, "xlsx"),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        help="Incluye hoja 'Léeme' con descripción de columnas y nota metodológica.",
    )
    st.markdown(
        "<div style='font-size:0.75rem;color:#555;margin-top:4px;'>"
        "Incluye hoja Léeme con descripción de columnas</div>",
        unsafe_allow_html=True,
    )

# Nota de licencia
st.markdown("""
<div class="licencia-box">
  Datos publicados bajo licencia
  <b>Creative Commons Atribución 4.0 Internacional (CC BY 4.0)</b>.
  Puedes usar, compartir, adaptar y redistribuir estos datos libremente,
  incluso con fines comerciales, siempre que se indique como fuente:
  <i>Municipalidad de Peñalolén — Portal de Transparencia Presupuestaria</i>.
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Filtros en cascada para exploración en pantalla
# ---------------------------------------------------------------------------

st.markdown('<div class="seccion">Exploración interactiva</div>', unsafe_allow_html=True)

with st.container():
    st.markdown('<div class="filtros-box">', unsafe_allow_html=True)

    f1, f2, f3 = st.columns(3)

    with f1:
        subtitulos  = ["Todos"] + sorted(df_cierre["Subtítulo_Nombre"].unique())
        sub_sel     = st.selectbox("Subtítulo", subtitulos, index=0)

    # Filtrar para ítem (depende de subtítulo)
    df_f1 = df_cierre if sub_sel == "Todos" else df_cierre[df_cierre["Subtítulo_Nombre"] == sub_sel]

    with f2:
        items   = ["Todos"] + sorted(df_f1["Ítem_Nombre"].unique())
        item_sel = st.selectbox("Ítem", items, index=0)

    # Filtrar para asignación (depende de ítem)
    df_f2 = df_f1 if item_sel == "Todos" else df_f1[df_f1["Ítem_Nombre"] == item_sel]

    with f3:
        asigs    = ["Todos"] + sorted(df_f2["Asignación_Nombre"].unique())
        asig_sel = st.selectbox("Asignación", asigs, index=0)

    st.markdown("</div>", unsafe_allow_html=True)

# Aplicar filtros
df_filtrado = df_f2.copy()
if asig_sel != "Todos":
    df_filtrado = df_filtrado[df_filtrado["Asignación_Nombre"] == asig_sel]

# ---------------------------------------------------------------------------
# Stats de la selección actual
# ---------------------------------------------------------------------------

col_ejec_num = "DEVENGADO_ACUMULADO" if tipo_sel == "Gastos" else "PERCIBIDO_ACUMULADO"
ejec_lbl     = "Devengado acum." if tipo_sel == "Gastos" else "Percibido acum."

ppto_sel  = df_filtrado["PRESUPUESTO_VIGENTE"].sum()
ejec_sel  = df_filtrado[col_ejec_num].sum() if col_ejec_num in df_filtrado.columns else 0
pct_sel   = ejec_sel / ppto_sel * 100 if ppto_sel > 0 else 0.0
n_filas   = len(df_filtrado)
n_total   = len(df_cierre)

color_pct = (
    "#1B6B30" if pct_sel <= 100 and pct_sel >= 70
    else "#8B4A00" if pct_sel >= 40
    else "#8B1A1A" if pct_sel > 100
    else "#1A3A7A"
)

str_ppto = fmt_millones(ppto_sel).replace("$", "&#36;")
str_ejec = fmt_millones(ejec_sel).replace("$", "&#36;")

st.markdown(
    f'<span class="stat-pill">{n_filas:,} de {n_total:,} registros</span>'
    f'<span class="stat-pill">Ppto. vigente: {str_ppto}</span>'
    f'<span class="stat-pill">{ejec_lbl}: {str_ejec}</span>'
    f'<span class="stat-pill" style="background:#E8F0FE;color:{color_pct};">'
    f'Ejecución: {pct_sel:.1f}%</span>',
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Tabla de detalle filtrada
# ---------------------------------------------------------------------------

# Columnas a mostrar en pantalla (renombradas, sin metadatos internos)
COLS_TABLA = [
    "FECHA_BALANCE", "CODIGO_CUENTA",
    "Subtítulo_Nombre", "Ítem_Nombre", "Asignación_Nombre", "Denominación_Cuenta_Base",
    "PRESUPUESTO_VIGENTE", "DEVENGADO_PARCIAL", "DEVENGADO_ACUMULADO",
]
if tipo_sel == "Gastos":
    COLS_TABLA += ["PAGADO_ACUMULADO", "POR_PAGAR_A_LA_FECHA"]
else:
    COLS_TABLA += ["PERCIBIDO_ACUMULADO", "POR_PERCIBIR_A_LA_FECHA"]

cols_presentes = [c for c in COLS_TABLA if c in df_filtrado.columns]
df_tabla = df_filtrado[cols_presentes].rename(columns=NOMBRE_COLS_DISPLAY)

# Configuración de columnas para st.dataframe
col_config = {
    NOMBRE_COLS_DISPLAY.get("CODIGO_CUENTA", "Código cuenta"):
        st.column_config.TextColumn("Código cuenta", width="medium"),
    NOMBRE_COLS_DISPLAY.get("Subtítulo_Nombre", "Subtítulo"):
        st.column_config.TextColumn("Subtítulo", width="large"),
    NOMBRE_COLS_DISPLAY.get("Ítem_Nombre", "Ítem"):
        st.column_config.TextColumn("Ítem", width="large"),
    NOMBRE_COLS_DISPLAY.get("Asignación_Nombre", "Asignación"):
        st.column_config.TextColumn("Asignación", width="large"),
    NOMBRE_COLS_DISPLAY.get("Denominación_Cuenta_Base", "Denominación"):
        st.column_config.TextColumn("Denominación", width="large"),
}
# Columnas numéricas con formato de moneda
for col_orig in [
    "PRESUPUESTO_VIGENTE", "DEVENGADO_PARCIAL", "DEVENGADO_ACUMULADO",
    "PAGADO_ACUMULADO", "POR_PAGAR_A_LA_FECHA",
    "PERCIBIDO_ACUMULADO", "POR_PERCIBIR_A_LA_FECHA",
]:
    nombre_display = NOMBRE_COLS_DISPLAY.get(col_orig, col_orig)
    if nombre_display in df_tabla.columns:
        col_config[nombre_display] = st.column_config.NumberColumn(
            nombre_display,
            format="$ %,d",
            width="medium",
        )

st.dataframe(
    df_tabla,
    use_container_width=True,
    hide_index=True,
    height=420,
    column_config=col_config,
)

# ---------------------------------------------------------------------------
# Nota metodológica
# ---------------------------------------------------------------------------

st.markdown(f"""
<div class="nota">
  <b>Nota metodológica</b> &nbsp;·&nbsp;
  La tabla de exploración muestra los registros del cierre contable de
  <b>{mes_lbl} {anio_sel}</b> filtrados según la selección jerárquica.
  El archivo descargable contiene el dataset completo sin filtros,
  para facilitar la reutilización y el análisis independiente de los datos.
  <b>Devengado parcial</b>: monto registrado solo en el mes del cierre.
  <b>Devengado acumulado</b>: suma desde el 1 de enero.
  Una cuenta de <b>gasto</b> está 100% ejecutada cuando el devengado acumulado
  iguala el presupuesto vigente; una cuenta de <b>ingreso</b> está 100% ejecutada
  cuando el percibido acumulado iguala el presupuesto vigente.
  Montos en pesos chilenos (CLP).
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.markdown("""
<div class="footer">
  Municipalidad de Peñalolén &nbsp;·&nbsp; Portal de Transparencia Presupuestaria
  &nbsp;·&nbsp; Datos abiertos bajo licencia CC BY 4.0
</div>
""", unsafe_allow_html=True)
