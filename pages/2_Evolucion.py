"""
pages/2_Evolucion.py — Evolución temporal de la ejecución presupuestaria
=========================================================================
Compara la ejecución mes a mes entre distintos años presupuestarios.

Estructura del gráfico:
  - Eje X: mes del año (enero–diciembre)
  - Eje Y: métrica seleccionada (acumulada desde enero)
  - Una línea por año disponible en los datos
  - Filtro opcional por subtítulo (o total consolidado)

Métricas disponibles:
  Gastos:   Devengado acumulado · Pagado acumulado · Presupuesto vigente
  Ingresos: Devengado acumulado · Percibido acumulado · Presupuesto vigente

Nota sobre Presupuesto vigente:
  Su valor cambia mes a mes según las modificaciones presupuestarias aprobadas.
  Graficarlo en la serie temporal permite ver cuándo ocurrieron esas modificaciones.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

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

# Colores para líneas por año (hasta 6 años comparables)
COLORES_ANIO = [
    "#0250C0",  # azul principal — año más reciente
    "#FF8500",  # naranja
    "#7240C2",  # violeta
    "#65930D",  # verde
    "#BC092C",  # rojo
    "#A37129",  # ocre
]

# Color especial para la línea de presupuesto vigente
COLOR_PPTO = "#B7B7B7"

# ---------------------------------------------------------------------------
# Configuración de página
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Evolución Temporal · Peñalolén",
    page_icon="📈",
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

    .header-strip {{
        background: linear-gradient(90deg, {COLOR_OSCURO} 0%, {COLOR_PRINCIPAL} 100%);
        border-radius: 10px; padding: 22px 32px 18px 32px; margin-bottom: 24px;
    }}
    .header-strip h1 {{
        font-size: 1.45rem; font-weight: 700; margin: 0 0 4px 0; color: {COLOR_BLANCO};
    }}
    .header-strip p {{ font-size: 0.88rem; margin: 0; opacity: 0.82; color: {COLOR_BLANCO}; }}

    .control-bar {{
        background: {COLOR_FONDO}; border: 1px solid #DDE4F0;
        border-radius: 10px; padding: 16px 20px; margin-bottom: 20px;
    }}

    .seccion {{
        font-size: 0.78rem; font-weight: 700; text-transform: uppercase;
        letter-spacing: 0.08em; color: {COLOR_AUXILIAR};
        border-bottom: 2px solid {COLOR_BARRA};
        padding-bottom: 5px; margin: 22px 0 14px 0;
    }}

    .kpi-mini {{
        background: {COLOR_FONDO}; border-left: 4px solid {COLOR_PRINCIPAL};
        border-radius: 7px; padding: 12px 16px; margin-bottom: 2px;
    }}
    .kpi-mini.acento {{ border-left-color: {COLOR_ACENTO}; }}
    .kpi-mini.gris   {{ border-left-color: {COLOR_PPTO}; }}
    .kpi-mini-label {{
        font-size: 0.72rem; font-weight: 600; text-transform: uppercase;
        letter-spacing: 0.06em; color: {COLOR_AUXILIAR}; margin-bottom: 2px;
    }}
    .kpi-mini-value {{ font-size: 1.25rem; font-weight: 700; color: {COLOR_OSCURO}; }}
    .kpi-mini-sub   {{ font-size: 0.75rem; color: #555; margin-top: 2px; }}

    .badge {{
        display: inline-block; font-size: 0.73rem; font-weight: 600;
        padding: 1px 8px; border-radius: 10px; margin-top: 4px;
    }}
    .badge-ok   {{ background: #E6F4EA; color: #1B6B30; }}
    .badge-warn {{ background: #FFF3E0; color: #8B4A00; }}
    .badge-info {{ background: #E8F0FE; color: #1A3A7A; }}
    .badge-over {{ background: #FDECEA; color: #8B1A1A; }}

    .aviso-ppto {{
        background: #FFFBEA; border-left: 4px solid #FFC107;
        border-radius: 7px; padding: 10px 14px;
        font-size: 0.80rem; color: #5A4000; line-height: 1.55;
        margin-bottom: 8px;
    }}

    .nota {{
        background: #EEF2FB; border-radius: 7px; padding: 11px 16px;
        font-size: 0.79rem; color: #333; line-height: 1.6; margin-top: 12px;
    }}
    .nota b {{ color: {COLOR_OSCURO}; }}

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
    1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr",
    5: "May", 6: "Jun", 7: "Jul", 8: "Ago",
    9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic",
}
MESES_ES_LARGO = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
    5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
}


def fmt_millones(v: float) -> str:
    if abs(v) >= 1_000_000_000:
        return f"${v / 1_000_000_000:,.2f} MM"
    return f"${v / 1_000_000:,.1f} M"


def badge_html(pct: float, label: str = "ejecutado") -> str:
    txt = f"{pct:.1f}% {label}"
    if pct > 100:
        cls = "badge-over"
    elif pct >= 70:
        cls = "badge-ok"
    elif pct >= 40:
        cls = "badge-warn"
    else:
        cls = "badge-info"
    return f'<span class="badge {cls}">{txt}</span>'


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

    # Años disponibles para este tipo de balance
    anios_disp = sorted(df_base["anio"].unique(), reverse=True)
    anios_sel = st.multiselect(
        "Años a comparar",
        options=anios_disp,
        default=anios_disp[:min(3, len(anios_disp))],
        help="Selecciona uno o más años para superponer en el gráfico.",
    )

    st.markdown("---")
    st.markdown(
        "<span style='font-size:0.75rem;opacity:0.6;'>"
        "Información oficial extraída del ERP contable municipal. "
        "Actualización mensual.</span>",
        unsafe_allow_html=True,
    )

if not anios_sel:
    st.warning("Selecciona al menos un año en el panel lateral.")
    st.stop()

# ---------------------------------------------------------------------------
# Métricas disponibles según tipo de balance
# ---------------------------------------------------------------------------

METRICAS_GASTOS = {
    "Devengado acumulado":  "DEVENGADO_ACUMULADO",
    "Pagado acumulado":     "PAGADO_ACUMULADO",
    "Presupuesto vigente":  "PRESUPUESTO_VIGENTE",
}
METRICAS_INGRESOS = {
    "Devengado acumulado":  "DEVENGADO_ACUMULADO",
    "Percibido acumulado":  "PERCIBIDO_ACUMULADO",
    "Presupuesto vigente":  "PRESUPUESTO_VIGENTE",
}
metricas_disp = METRICAS_GASTOS if tipo_sel == "Gastos" else METRICAS_INGRESOS

# ---------------------------------------------------------------------------
# Subtítulos disponibles (unión de todos los años seleccionados)
# ---------------------------------------------------------------------------

df_filtrado = df_base[df_base["anio"].isin(anios_sel)]
subtitulos  = sorted(df_filtrado["Subtítulo_Nombre"].unique())
OPCION_TODOS = "— Total consolidado —"
opciones_sub = [OPCION_TODOS] + [s.title() for s in subtitulos]

# ---------------------------------------------------------------------------
# Controles del gráfico
# ---------------------------------------------------------------------------

with st.container():
    st.markdown('<div class="control-bar">', unsafe_allow_html=True)
    c1, c2 = st.columns([1, 1])
    with c1:
        metrica_lbl = st.selectbox(
            "Métrica",
            options=list(metricas_disp.keys()),
            index=0,
            help=(
                "Presupuesto vigente varía mes a mes según modificaciones presupuestarias — "
                "útil para visualizar cuándo se aprobaron cambios al presupuesto."
            ),
        )
    with c2:
        sub_sel_lbl = st.selectbox(
            "Filtrar por subtítulo",
            options=opciones_sub,
            index=0,
            help="Selecciona un subtítulo o visualiza el total consolidado.",
        )
    st.markdown("</div>", unsafe_allow_html=True)

col_metrica = metricas_disp[metrica_lbl]
es_ppto     = col_metrica == "PRESUPUESTO_VIGENTE"
sub_filtro  = None if sub_sel_lbl == OPCION_TODOS else sub_sel_lbl.upper()

# ---------------------------------------------------------------------------
# Header (después de conocer los controles)
# ---------------------------------------------------------------------------

sub_titulo_header = "Total consolidado" if sub_filtro is None else sub_sel_lbl
st.markdown(f"""
<div class="header-strip">
  <h1>📈 Evolución temporal — {tipo_sel}</h1>
  <p>Municipalidad de Peñalolén &nbsp;·&nbsp; {sub_titulo_header}
     &nbsp;·&nbsp; Comparativa {" · ".join(str(a) for a in sorted(anios_sel))}</p>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Aviso contextual cuando se grafica presupuesto vigente
# ---------------------------------------------------------------------------

if es_ppto:
    st.markdown("""
    <div class="aviso-ppto">
      <b>¿Por qué el presupuesto vigente cambia mes a mes?</b><br>
      El presupuesto vigente refleja el presupuesto inicial más todas las modificaciones
      presupuestarias aprobadas durante el ejercicio. Cada vez que el Concejo Municipal
      aprueba una reasignación o suplemento, ese valor se actualiza en el cierre mensual
      siguiente. Los saltos en la línea indican el momento exacto en que ocurrió una
      modificación.
    </div>
    """, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Construcción de la serie temporal
# ---------------------------------------------------------------------------

def serie_por_anio(
    df: pd.DataFrame,
    anio: int,
    col: str,
    subtitulo: str | None,
) -> pd.DataFrame:
    """
    Retorna un DataFrame con columnas [mes_cierre, valor] para un año y métrica dados.
    Si subtitulo es None, agrega todos los subtítulos.
    """
    sub = df[df["anio"] == anio].copy()
    if subtitulo:
        sub = sub[sub["Subtítulo_Nombre"] == subtitulo]
    if sub.empty or col not in sub.columns:
        return pd.DataFrame(columns=["mes_cierre", "valor"])
    return (
        sub.groupby("mes_cierre")[col]
        .sum()
        .reset_index()
        .rename(columns={col: "valor"})
        .sort_values("mes_cierre")
    )

# ---------------------------------------------------------------------------
# Figura Plotly
# ---------------------------------------------------------------------------

fig = go.Figure()

# Una línea por año seleccionado
for idx, anio in enumerate(sorted(anios_sel)):
    color_linea = COLORES_ANIO[idx % len(COLORES_ANIO)]
    # Si es presupuesto vigente, usar gris neutro para todos los años
    # y diferenciar por dash pattern para mayor legibilidad
    if es_ppto:
        color_linea = COLOR_PPTO
        dash_patterns = ["solid", "dash", "dot", "dashdot", "longdash", "longdashdot"]
        dash = dash_patterns[idx % len(dash_patterns)]
    else:
        dash = "solid"

    serie = serie_por_anio(df_base, anio, col_metrica, sub_filtro)

    if serie.empty:
        continue

    # Etiquetas del eje X como nombres de mes
    x_labels = [MESES_ES.get(m, str(m)) for m in serie["mes_cierre"]]
    y_vals    = serie["valor"].tolist()

    # Tooltip enriquecido
    hover_texts = [
        f"<b>{anio} — {MESES_ES_LARGO.get(m, m)}</b><br>"
        f"{metrica_lbl}: {fmt_millones(v)}"
        for m, v in zip(serie["mes_cierre"], y_vals)
    ]

    fig.add_trace(go.Scatter(
        x=x_labels,
        y=y_vals,
        mode="lines+markers",
        name=str(anio),
        line=dict(color=color_linea, width=2.5, dash=dash),
        marker=dict(size=7, color=color_linea, symbol="circle"),
        hovertemplate="%{customdata}<extra></extra>",
        customdata=hover_texts,
    ))

# Línea de referencia horizontal: último valor de presupuesto vigente
# del año más reciente (solo cuando la métrica NO es ppto. vigente)
if not es_ppto and len(anios_sel) > 0:
    anio_ref = max(anios_sel)
    serie_ppto = serie_por_anio(df_base, anio_ref, "PRESUPUESTO_VIGENTE", sub_filtro)
    if not serie_ppto.empty:
        ppto_ultimo = serie_ppto.iloc[-1]["valor"]
        mes_ultimo  = MESES_ES.get(int(serie_ppto.iloc[-1]["mes_cierre"]), "")
        fig.add_hline(
            y=ppto_ultimo,
            line_dash="dot",
            line_color=COLOR_PPTO,
            line_width=1.5,
            annotation_text=f"Ppto. vigente {anio_ref} ({mes_ultimo}): {fmt_millones(ppto_ultimo)}",
            annotation_position="top right",
            annotation_font_size=11,
            annotation_font_color=COLOR_AUXILIAR,
        )

fig.update_layout(
    height=480,
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="sans-serif", size=12, color=COLOR_TEXTO),
    margin=dict(t=20, l=10, r=10, b=10),
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="left",
        x=0,
        title_text="Año",
        title_font=dict(color=COLOR_OSCURO),    # <-- Añadido: Color del título "Año"
        font=dict(size=12, color=COLOR_TEXTO),  # <-- Añadido: Color de los números de los años
    ),
    xaxis=dict(
        title="Mes",
        title_font=dict(color=COLOR_OSCURO, size=13), # <-- Añadido: Fuerza el color del título "Mes"
        color=COLOR_OSCURO,
        showgrid=True,
        gridcolor="#EEF2FB",
        gridwidth=1,
        zeroline=False,
        tickfont=dict(size=11, color=COLOR_OSCURO),
    ),
    yaxis=dict(
        title=metrica_lbl + " (CLP)",
        title_font=dict(color=COLOR_OSCURO, size=13), # <-- Añadido: Fuerza el color del título Y
        color=COLOR_OSCURO,
        showgrid=True,
        gridcolor="#EEF2FB",
        gridwidth=1,
        zeroline=False,
        tickfont=dict(size=11, color=COLOR_OSCURO),
        tickformat="$,.0f",
    ),
    hovermode="x unified",
    hoverlabel=dict(
        bgcolor=COLOR_OSCURO,
        font_color=COLOR_BLANCO,
        font_size=12,
        bordercolor=COLOR_PRINCIPAL,
    ),
)

# ---------------------------------------------------------------------------
# KPIs de contexto: comparativa del último cierre disponible por año
# ---------------------------------------------------------------------------

st.markdown('<div class="seccion">Último cierre disponible por año</div>', unsafe_allow_html=True)

# Columna de ejecución presupuestaria (denominador = ppto. vigente)
col_ejec = (
    "DEVENGADO_ACUMULADO" if tipo_sel == "Gastos" else "PERCIBIDO_ACUMULADO"
)
ejec_lbl = (
    "Devengado acumulado" if tipo_sel == "Gastos" else "Percibido acumulado"
)

kpi_cols = st.columns(len(anios_sel))

for idx, anio in enumerate(sorted(anios_sel)):
    sub_df = df_base[df_base["anio"] == anio]
    if sub_filtro:
        sub_df = sub_df[sub_df["Subtítulo_Nombre"] == sub_filtro]
    if sub_df.empty:
        continue

    mes_max  = sub_df["mes_cierre"].max()
    df_ult   = sub_df[sub_df["mes_cierre"] == mes_max]
    ppto_v   = df_ult["PRESUPUESTO_VIGENTE"].sum()
    ejec_v   = df_ult[col_ejec].sum() if col_ejec in df_ult.columns else 0
    pct      = ejec_v / ppto_v * 100 if ppto_v > 0 else 0.0
    mes_lbl  = MESES_ES_LARGO.get(int(mes_max), "—")
    color_borde = COLORES_ANIO[idx % len(COLORES_ANIO)]
    kpi_clase   = "acento" if idx % 2 == 1 else ""

    with kpi_cols[idx]:
        st.markdown(f"""
        <div class="kpi-mini" style="border-left-color:{color_borde}">
          <div class="kpi-mini-label">{anio} — cierre {mes_lbl}</div>
          <div class="kpi-mini-value">{fmt_millones(ejec_v)}</div>
          <div class="kpi-mini-sub">
            {ejec_lbl}<br>
            Ppto. vigente: {fmt_millones(ppto_v)}
          </div>
          {badge_html(pct, "ejecutado")}
        </div>
        """, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Gráfico
# ---------------------------------------------------------------------------

st.markdown(
    f'<div class="seccion">'
    f'{metrica_lbl} acumulado por mes'
    f'{"  —  " + sub_sel_lbl if sub_sel_lbl != OPCION_TODOS else "  —  Total consolidado"}'
    f'</div>',
    unsafe_allow_html=True,
)

if all(
    serie_por_anio(df_base, a, col_metrica, sub_filtro).empty
    for a in anios_sel
):
    st.info("No hay datos para la combinación seleccionada.")
else:
    st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# Tabla comparativa: valor por mes y año (pivot)
# ---------------------------------------------------------------------------

st.markdown('<div class="seccion">Tabla comparativa por mes</div>', unsafe_allow_html=True)

filas = []
for anio in sorted(anios_sel):
    serie = serie_por_anio(df_base, anio, col_metrica, sub_filtro)
    for _, row in serie.iterrows():
        filas.append({
            "Año": anio,
            "Mes": MESES_ES_LARGO.get(int(row["mes_cierre"]), str(row["mes_cierre"])),
            "mes_num": int(row["mes_cierre"]),
            metrica_lbl: row["valor"],
        })

if filas:
    df_tabla = pd.DataFrame(filas)
    df_pivot = (
        df_tabla
        .pivot_table(index=["mes_num", "Mes"], columns="Año", values=metrica_lbl, aggfunc="sum")
        .reset_index()
        .sort_values("mes_num")
        .drop(columns="mes_num")
    )
    df_pivot.columns.name = None

    # Formatear montos
    for col in df_pivot.columns:
        if col != "Mes":
            df_pivot[col] = df_pivot[col].apply(
                lambda v: fmt_millones(v) if pd.notna(v) else "—"
            )

    st.dataframe(
        df_pivot,
        use_container_width=True,
        hide_index=True,
        column_config={"Mes": st.column_config.TextColumn(width="medium")},
    )

# ---------------------------------------------------------------------------
# Nota metodológica
# ---------------------------------------------------------------------------

nota_metrica = {
    "Devengado acumulado": (
        "El <b>devengado acumulado</b> suma todos los compromisos presupuestarios "
        "reconocidos desde el 1 de enero. Es el indicador principal de ejecución del gasto."
    ),
    "Pagado acumulado": (
        "El <b>pagado acumulado</b> refleja los montos efectivamente transferidos "
        "a proveedores o beneficiarios. Siempre es menor o igual al devengado acumulado."
    ),
    "Percibido acumulado": (
        "El <b>percibido acumulado</b> refleja los ingresos efectivamente ingresados "
        "a las arcas municipales. Es el indicador principal de ejecución de ingresos."
    ),
    "Presupuesto vigente": (
        "El <b>presupuesto vigente</b> corresponde al presupuesto inicial más todas las "
        "modificaciones aprobadas durante el ejercicio. Los cambios en su valor a lo largo "
        "del año indican el momento en que el Concejo Municipal aprobó reasignaciones o "
        "suplementos presupuestarios."
    ),
}.get(metrica_lbl, "")

st.markdown(f"""
<div class="nota">
  <b>Nota metodológica</b> &nbsp;·&nbsp;
  {nota_metrica}
  Cada línea del gráfico representa un año presupuestario y muestra la evolución
  mes a mes del valor acumulado desde enero.
  La línea punteada gris (cuando aplica) marca el presupuesto vigente del cierre
  más reciente del año más reciente seleccionado, como referencia del techo presupuestario.
  Los montos se expresan en pesos chilenos (CLP).
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.markdown("""
<div class="footer">
  Municipalidad de Peñalolén &nbsp;·&nbsp; Portal de Transparencia Presupuestaria
  &nbsp;·&nbsp; Datos actualizados mensualmente desde el sistema ERP contable oficial
</div>
""", unsafe_allow_html=True)
