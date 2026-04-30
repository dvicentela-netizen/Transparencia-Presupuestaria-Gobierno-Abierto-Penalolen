"""
pages/4_Caja.py — Proyección de flujo de caja
==============================================
Proyecta la ejecución presupuestaria mensual para los meses futuros
del año en curso y el ejercicio siguiente completo, basándose en
el comportamiento histórico de ejecución parcial mensual.

Metodología:
  Gastos:   % mensual = DEVENGADO_PARCIAL / PRESUPUESTO_VIGENTE
  Ingresos: % mensual = PERCIBIDO_PARCIAL / PRESUPUESTO_VIGENTE
  Proyección = % esperado × presupuesto vigente último cierre

Organización (st.tabs):
  Tab 1 — Año en curso: real + proyectado
  Tab 2 — Año siguiente: proyección completa
  Tab 3 — Supuestos y transparencia
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from data_loader import cargar_datos
from cashflow_engine import (
    proyectar, proyeccion_a_df, generar_reporte_md, generar_excel_proyeccion,
    tabla_supuestos, METODOS, NIVELES, MESES_ES,
    SUPUESTO_HISTORICO, SUPUESTO_INTRA_EJERC,
    SUPUESTO_SIN_HISTORICO, SUPUESTO_MANUAL,
)

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
COLOR_REAL      = "#0250C0"   # línea de datos reales
COLOR_PROY      = "#FF8500"   # área proyectada
COLOR_PPTO      = "#B7B7B7"   # línea presupuesto vigente

# Color por supuesto (para tabla)
COLOR_SUPUESTO = {
    SUPUESTO_HISTORICO:    "#E6F4EA",   # verde claro
    SUPUESTO_INTRA_EJERC:  "#FFF3E0",   # naranja claro
    SUPUESTO_SIN_HISTORICO:"#FDECEA",   # rojo claro
    SUPUESTO_MANUAL:       "#E8F0FE",   # azul claro
}

# ---------------------------------------------------------------------------
# Configuración de página
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Flujo de Caja Proyectado · Peñalolén",
    page_icon="💰",
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
    
st.markdown(f"""
<style>
    [data-testid="stAppViewContainer"] {{
        background-color: #FFFFFF;
    }}
    
   
    [data-testid="stSidebar"] {{ 
        background-color: {COLOR_OSCURO}; 
    }}
    
   
    [data-testid="stSidebar"] p, 
    [data-testid="stSidebar"] label {{ 
        color: {COLOR_BLANCO} !important; 
    }}
    
   
    [data-testid="stSidebar"] div[data-baseweb="select"] * {{
        color: {COLOR_TEXTO} !important;
    }}
    
    
    [data-testid="stSidebar"] span[data-baseweb="tag"] {{
        background-color: {COLOR_ACENTO} !important;
        color: {COLOR_BLANCO} !important;
        border: none;
    }}
    .header-strip {{
        background: linear-gradient(90deg, {COLOR_OSCURO} 0%, {COLOR_PRINCIPAL} 100%);
        border-radius: 10px; padding: 22px 32px 18px 32px; margin-bottom: 24px;
    }}
    .header-strip h1 {{ font-size:1.45rem; font-weight:700; margin:0 0 4px 0; color:{COLOR_BLANCO}; }}
    .header-strip p  {{ font-size:0.88rem; margin:0; opacity:0.82; color:{COLOR_BLANCO}; }}

    .seccion {{
        font-size:0.78rem; font-weight:700; text-transform:uppercase;
        letter-spacing:0.08em; color:{COLOR_AUXILIAR};
        border-bottom:2px solid {COLOR_BARRA};
        padding-bottom:5px; margin:22px 0 14px 0;
    }}
    .kpi-mini {{
        background:{COLOR_FONDO}; border-left:4px solid {COLOR_PRINCIPAL};
        border-radius:7px; padding:12px 16px; margin-bottom:2px;
    }}
    .kpi-mini.acento {{ border-left-color:{COLOR_ACENTO}; }}
    .kpi-mini.gris   {{ border-left-color:{COLOR_PPTO}; }}
    .kpi-mini-label {{
        font-size:0.72rem; font-weight:600; text-transform:uppercase;
        letter-spacing:0.06em; color:{COLOR_AUXILIAR}; margin-bottom:2px;
    }}
    .kpi-mini-value  {{ font-size:1.25rem; font-weight:700; color:{COLOR_OSCURO}; }}
    .kpi-mini-sub    {{ font-size:0.75rem; color:#555; margin-top:2px; }}

    .supuesto-pill {{
        display:inline-block; font-size:0.71rem; font-weight:600;
        padding:1px 8px; border-radius:10px; margin:1px;
    }}
    .aviso-box {{
        background:#FFFBEA; border-left:4px solid #FFC107;
        border-radius:7px; padding:10px 14px;
        font-size:0.80rem; color:#5A4000; line-height:1.55;
        margin-bottom:12px;
    }}
    .nota {{
        background:#EEF2FB; border-radius:7px; padding:11px 16px;
        font-size:0.79rem; color:#333; line-height:1.6; margin-top:12px;
    }}
    .nota b {{ color:{COLOR_OSCURO}; }}
    .footer {{
        text-align:center; font-size:0.73rem; color:#888;
        margin-top:36px; padding-top:14px; border-top:1px solid #DDE4F0;
    }}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fmt_millones(v: float) -> str:
    if v is None:
        return "—"
    v = float(v)
    if abs(v) >= 1_000_000_000:
        return f"${v/1_000_000_000:,.2f} MM"
    return f"${v/1_000_000:,.1f} M"

def fmt_pct(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return f"{float(v)*100:.1f}%"

def color_supuesto(s: str) -> str:
    for k, c in COLOR_SUPUESTO.items():
        if k in s:
            return c
    return "#F5F5F5"

# ---------------------------------------------------------------------------
# Carga de datos
# ---------------------------------------------------------------------------

df_gastos, df_ingresos = cargar_datos("data")

# ---------------------------------------------------------------------------
# Sidebar — configuración de la proyección
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

    tipo_sel = st.radio("Tipo de balance", ["Gastos", "Ingresos"], horizontal=True)
    df_base  = df_gastos if tipo_sel == "Gastos" else df_ingresos

    anios_disp   = sorted(df_base["anio"].unique(), reverse=True)
    anio_curso   = st.selectbox("Año en curso", anios_disp, index=0)
    anios_hist_disp = [a for a in anios_disp if a < anio_curso]

    if not anios_hist_disp:
        st.warning("No hay años históricos anteriores disponibles.")
        st.stop()

    anios_historicos = st.multiselect(
        "Años históricos base",
        options=anios_hist_disp,
        default=anios_hist_disp[:min(3, len(anios_hist_disp))],
        help="Años usados para calcular el % esperado mensual.",
    )
    if not anios_historicos:
        st.warning("Selecciona al menos un año histórico.")
        st.stop()

    nivel_sel = st.selectbox("Nivel jerárquico", list(NIVELES.keys()), index=0)
    metodo    = st.selectbox("Método de cálculo", METODOS, index=0,
                             help="Promedio ponderado da más peso a los años más recientes.")

    st.markdown("---")
    st.markdown("**Filtro de cuenta (opcional)**")
    col_nivel_col = NIVELES[nivel_sel]
    cuentas_disp  = sorted(df_base[df_base["anio"] == anio_curso][col_nivel_col].unique())
    cuenta_filtro = st.selectbox(
        "Cuenta", ["— Todas —"] + cuentas_disp, index=0,
    )

    st.markdown("---")
    st.markdown("**Año siguiente — presupuesto base**")
    anio_sig = anio_curso + 1
    usar_factor = st.checkbox("Ajustar presupuesto año siguiente", value=False)
    if usar_factor:
        factor_pct = st.slider(
            f"Variación respecto al {anio_curso} (%)",
            min_value=-30.0, max_value=50.0, value=0.0, step=0.5,
            format="%.1f%%",
            help="Se aplica proporcionalmente a todas las cuentas.",
        )
        factor = 1 + factor_pct / 100
    else:
        factor = 1.0

    st.markdown("---")
    st.markdown(
        "<span style='font-size:0.75rem;opacity:0.6;'>"
        "Proyección basada en comportamiento histórico. "
        "No constituye compromiso de ejecución.</span>",
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.markdown(f"""
<div class="header-strip">
  <h1>💰 Proyección de flujo de caja — {tipo_sel}</h1>
  <p>Municipalidad de Peñalolén &nbsp;·&nbsp;
     Año en curso: {anio_curso} &nbsp;·&nbsp;
     Proyección hasta: {anio_sig} &nbsp;·&nbsp;
     Base histórica: {', '.join(str(a) for a in sorted(anios_historicos))}
  </p>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Calcular proyección
# ---------------------------------------------------------------------------

if "ajustes_manuales" not in st.session_state:
    st.session_state.ajustes_manuales = {}

# Clave de caché: si cambian los parámetros, recalcular
cache_key = (tipo_sel, nivel_sel, metodo, tuple(sorted(anios_historicos)), anio_curso, factor)
if st.session_state.get("_cache_key") != cache_key:
    celdas = proyectar(
        df=df_base,
        tipo_balance=tipo_sel,
        nivel=nivel_sel,
        metodo=metodo,
        anios_historicos=anios_historicos,
        anio_curso=anio_curso,
        ajustes_manuales=st.session_state.ajustes_manuales,
        factor_anio_siguiente=factor,
    )
    st.session_state["_df_proy"]   = proyeccion_a_df(celdas)
    st.session_state["_cache_key"] = cache_key

df_proy = st.session_state["_df_proy"]

# Aplicar ajustes manuales si los hay (sin recalcular todo)
if st.session_state.ajustes_manuales:
    for (cuenta, anio, mes), pct_nuevo in st.session_state.ajustes_manuales.items():
        mask = (
            (df_proy["cuenta"] == cuenta) &
            (df_proy["anio"]   == anio)   &
            (df_proy["mes"]    == mes)
        )
        df_proy.loc[mask, "pct_original"]        = df_proy.loc[mask, "pct_usado"]
        df_proy.loc[mask, "pct_usado"]            = pct_nuevo
        df_proy.loc[mask, "monto_proyectado"]     = pct_nuevo * df_proy.loc[mask, "ppto_base"]
        df_proy.loc[mask, "ajustado_usuario"]     = True
        df_proy.loc[mask, "supuesto"]             = SUPUESTO_MANUAL

# Filtrar por cuenta si aplica
if cuenta_filtro != "— Todas —":
    df_vis = df_proy[df_proy["cuenta"] == cuenta_filtro].copy()
else:
    df_vis = df_proy.copy()

# Título de cuenta para gráficos
titulo_cuenta = cuenta_filtro if cuenta_filtro != "— Todas —" else "Total consolidado"

# ---------------------------------------------------------------------------
# Construir serie temporal para gráficos
# ---------------------------------------------------------------------------

def serie_mensual(df: pd.DataFrame, anio: int) -> pd.DataFrame:
    """Agrega monto proyectado por mes para un año dado."""
    return (
        df[df["anio"] == anio]
        .groupby(["mes", "mes_nombre", "es_real"])
        .agg(monto=("monto_proyectado", "sum"), ppto=("ppto_base", "sum"))
        .reset_index()
        .sort_values("mes")
    )

def fig_proyeccion(df_anio: pd.DataFrame, anio: int, titulo: str) -> go.Figure:
    """Gráfico de línea con área sombreada para meses proyectados."""
    reales = df_anio[df_anio["es_real"]].sort_values("mes")
    proy   = df_anio[~df_anio["es_real"]].sort_values("mes")

    fig = go.Figure()

    # Área sombreada proyectada
    if not proy.empty:
        fig.add_trace(go.Scatter(
            x=[MESES_ES[m] for m in proy["mes"]],
            y=proy["monto"].tolist(),
            fill="tozeroy",
            fillcolor=f"rgba(255,133,0,0.15)",
            line=dict(color=COLOR_PROY, width=2.5, dash="dash"),
            mode="lines+markers",
            marker=dict(size=7, color=COLOR_PROY, symbol="diamond"),
            name="Proyectado",
            hovertemplate=(
                "<b>%{x}</b><br>"
                "Proyectado: %{y:$,.0f}"
                "<extra></extra>"
            ),
        ))

    # Línea real
    if not reales.empty:
        fig.add_trace(go.Scatter(
            x=[MESES_ES[m] for m in reales["mes"]],
            y=reales["monto"].tolist(),
            fill="tozeroy",
            fillcolor=f"rgba(2,80,192,0.12)",
            line=dict(color=COLOR_REAL, width=2.5),
            mode="lines+markers",
            marker=dict(size=7, color=COLOR_REAL),
            name="Real",
            hovertemplate=(
                "<b>%{x}</b><br>"
                "Real: %{y:$,.0f}"
                "<extra></extra>"
            ),
        ))

    # Línea de presupuesto vigente promedio como referencia
    ppto_prom = df_anio["ppto"].mean()
    fig.add_hline(
        y=ppto_prom,
        line_dash="dot", line_color=COLOR_PPTO, line_width=1.5,
        annotation_text=f"Ppto. vigente promedio: {fmt_millones(ppto_prom)}",
        annotation_position="top right",
        annotation_font_size=11,
        annotation_font_color=COLOR_AUXILIAR,
    )

    fig.update_layout(
        title=dict(text=f"{titulo} — {anio}", font_size=14, x=0),
        height=400,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="sans-serif", size=12, color=COLOR_TEXTO),
        margin=dict(t=40, l=10, r=10, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        xaxis=dict(showgrid=True, gridcolor="#EEF2FB", zeroline=False),
        yaxis=dict(showgrid=True, gridcolor="#EEF2FB", zeroline=False,
                   tickformat="$,.0f"),
        hovermode="x unified",
        hoverlabel=dict(bgcolor=COLOR_OSCURO, font_color=COLOR_BLANCO,
                        font_size=12, bordercolor=COLOR_PRINCIPAL),
    )
    return fig

# ---------------------------------------------------------------------------
# Tabla de supuestos con edición inline
# ---------------------------------------------------------------------------

def tabla_ajustable(df_sub: pd.DataFrame, anio: int, key_prefix: str) -> None:
    """
    Muestra tabla de % por cuenta × mes con campo de ajuste manual.
    Los cambios se guardan en st.session_state.ajustes_manuales.
    """
    df_anio = df_sub[df_sub["anio"] == anio].copy()
    cuentas = sorted(df_anio["cuenta"].unique())
    meses_anio = sorted(df_anio["mes"].unique())

    # Leyenda de supuestos
    st.markdown(
        " ".join([
            f'<span class="supuesto-pill" style="background:{c};color:#333;">{s}</span>'
            for s, c in [
                ("Histórico", COLOR_SUPUESTO[SUPUESTO_HISTORICO]),
                ("Intra-ejercicio", COLOR_SUPUESTO[SUPUESTO_INTRA_EJERC]),
                ("Sin histórico", COLOR_SUPUESTO[SUPUESTO_SIN_HISTORICO]),
                ("Ajuste manual", COLOR_SUPUESTO[SUPUESTO_MANUAL]),
            ]
        ]),
        unsafe_allow_html=True,
    )
    st.markdown("<div style='margin-bottom:8px'></div>", unsafe_allow_html=True)

    # Encabezado de tabla
    cols_header = st.columns([3] + [1] * len(meses_anio))
    cols_header[0].markdown("**Cuenta**")
    for i, mes in enumerate(meses_anio):
        cols_header[i+1].markdown(f"**{MESES_ES[mes][:3]}**")

    for cuenta in cuentas:
        df_c = df_anio[df_anio["cuenta"] == cuenta]
        cols = st.columns([3] + [1] * len(meses_anio))
        nombre_corto = cuenta.title()
        if len(nombre_corto) > 38:
            nombre_corto = nombre_corto[:36] + "…"
        cols[0].markdown(
            f"<span style='font-size:0.78rem;'>{nombre_corto}</span>",
            unsafe_allow_html=True,
        )
        for i, mes in enumerate(meses_anio):
            fila = df_c[df_c["mes"] == mes]
            if fila.empty:
                cols[i+1].markdown("—")
                continue
            pct   = float(fila["pct_usado"].iloc[0])
            supue = fila["supuesto"].iloc[0]
            es_r  = bool(fila["es_real"].iloc[0])
            bg    = color_supuesto(supue)

            if es_r:
                cols[i+1].markdown(
                    f"<span style='background:{bg};padding:1px 4px;"
                    f"border-radius:4px;font-size:0.75rem;'>{pct*100:.1f}%</span>",
                    unsafe_allow_html=True,
                )
            else:
                nuevo = cols[i+1].number_input(
                    label="",
                    value=round(pct * 100, 2),
                    min_value=-100.0,
                    max_value=300.0,
                    step=0.1,
                    format="%.1f",
                    key=f"{key_prefix}_{cuenta}_{anio}_{mes}",
                    label_visibility="collapsed",
                )
                if abs(nuevo/100 - pct) > 0.0001:
                    st.session_state.ajustes_manuales[(cuenta, anio, mes)] = nuevo / 100

# ---------------------------------------------------------------------------
# KPIs resumen
# ---------------------------------------------------------------------------

def kpis_resumen(df_sub: pd.DataFrame, anio: int, kpi_clase: str = "") -> None:
    real_tot  = df_sub[df_sub["es_real"] & (df_sub["anio"] == anio)]["monto_proyectado"].sum()
    proy_tot  = df_sub[~df_sub["es_real"] & (df_sub["anio"] == anio)]["monto_proyectado"].sum()
    anual_tot = real_tot + proy_tot
    ppto_base = df_sub[df_sub["anio"] == anio]["ppto_base"].mean()
    n_ajustes = df_sub[
        df_sub["ajustado_usuario"] & (df_sub["anio"] == anio)
    ].shape[0]

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(f"""
        <div class="kpi-mini {kpi_clase}">
          <div class="kpi-mini-label">Ejecución real acumulada</div>
          <div class="kpi-mini-value">{fmt_millones(real_tot)}</div>
          <div class="kpi-mini-sub">meses con cierre disponible</div>
        </div>""", unsafe_allow_html=True)
    with k2:
        st.markdown(f"""
        <div class="kpi-mini {kpi_clase}">
          <div class="kpi-mini-label">Proyección meses restantes</div>
          <div class="kpi-mini-value">{fmt_millones(proy_tot)}</div>
          <div class="kpi-mini-sub">basada en % histórico</div>
        </div>""", unsafe_allow_html=True)
    with k3:
        st.markdown(f"""
        <div class="kpi-mini {kpi_clase}">
          <div class="kpi-mini-label">Total proyectado anual</div>
          <div class="kpi-mini-value">{fmt_millones(anual_tot)}</div>
          <div class="kpi-mini-sub">real + proyectado</div>
        </div>""", unsafe_allow_html=True)
    with k4:
        st.markdown(f"""
        <div class="kpi-mini {'acento' if n_ajustes > 0 else kpi_clase}">
          <div class="kpi-mini-label">Ajustes manuales</div>
          <div class="kpi-mini-value">{n_ajustes}</div>
          <div class="kpi-mini-sub">supuestos modificados</div>
        </div>""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Pestañas principales
# ---------------------------------------------------------------------------

tab1, tab2, tab3 = st.tabs([
    f"📅 Año en curso ({anio_curso})",
    f"🔮 Año siguiente ({anio_sig})",
    "🔍 Supuestos y transparencia",
])

# ============================================================
# TAB 1 — Año en curso
# ============================================================
with tab1:
    st.markdown(f'<div class="seccion">Resumen — {anio_curso}</div>', unsafe_allow_html=True)
    kpis_resumen(df_vis, anio_curso)

    st.markdown(f'<div class="seccion">Evolución mensual — {titulo_cuenta}</div>', unsafe_allow_html=True)
    serie1 = serie_mensual(df_vis, anio_curso)
    if not serie1.empty:
        st.plotly_chart(fig_proyeccion(serie1, anio_curso, tipo_sel), use_container_width=True)
    else:
        st.info("Sin datos para el año en curso con los filtros seleccionados.")

    st.markdown(f'<div class="seccion">% de ejecución mensual por cuenta — ajustable</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="aviso-box">
    Los porcentajes mostrados corresponden al % histórico calculado.
    Puedes modificar cualquier valor proyectado (celdas editables) para ajustar
    la proyección. Los cambios quedan registrados como <b>ajuste manual</b>
    y se reflejan en el gráfico y el reporte exportable.
    </div>
    """, unsafe_allow_html=True)

    df_tab1 = df_vis if cuenta_filtro == "— Todas —" else df_vis
    tabla_ajustable(df_tab1, anio_curso, key_prefix="tab1")

# ============================================================
# TAB 2 — Año siguiente
# ============================================================
with tab2:
    st.markdown(f'<div class="seccion">Supuesto de presupuesto — {anio_sig}</div>', unsafe_allow_html=True)

    ppto_curso_total = df_vis[df_vis["anio"] == anio_curso]["ppto_base"].mean()
    ppto_sig_total   = ppto_curso_total * factor if ppto_curso_total else 0

    if factor != 1.0:
        st.markdown(f"""
        <div class="aviso-box">
        <b>Supuesto de presupuesto {anio_sig}:</b>
        Se aplica un factor de <b>{factor:.4f} ({(factor-1)*100:+.2f}%)</b>
        sobre el presupuesto vigente del último cierre de {anio_curso}.
        Este ajuste se distribuye proporcionalmente entre todas las cuentas
        según su participación relativa en el presupuesto actual.
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="aviso-box">
        <b>Supuesto de presupuesto {anio_sig}:</b>
        Se usa el presupuesto vigente del último cierre de {anio_curso} sin modificación
        (factor = 1.0). Para ajustar, activa la opción en el panel lateral.
        </div>
        """, unsafe_allow_html=True)

    st.markdown(f'<div class="seccion">Resumen — {anio_sig}</div>', unsafe_allow_html=True)
    kpis_resumen(df_vis, anio_sig, "acento")

    st.markdown(f'<div class="seccion">Proyección mensual completa — {titulo_cuenta}</div>', unsafe_allow_html=True)
    serie2 = serie_mensual(df_vis, anio_sig)
    if not serie2.empty:
        st.plotly_chart(fig_proyeccion(serie2, anio_sig, tipo_sel), use_container_width=True)
    else:
        st.info("Sin datos para proyectar el año siguiente.")

    st.markdown(f'<div class="seccion">% de ejecución mensual por cuenta — ajustable</div>', unsafe_allow_html=True)

    # Advertencia de continuidad para cuentas sin histórico
    cuentas_sin_hist = df_vis[
        df_vis["supuesto"].str.contains("continuidad", na=False) &
        (df_vis["anio"] == anio_sig)
    ]["cuenta"].unique()
    if len(cuentas_sin_hist) > 0:
        st.markdown(f"""
        <div class="aviso-box">
        <b>⚠ {len(cuentas_sin_hist)} cuenta(s) sujeta(s) a continuidad de programa:</b>
        No tienen registro en años históricos anteriores y pueden corresponder a obras
        públicas o programas que finalizan con el ejercicio {anio_curso}.
        Su proyección para {anio_sig} debe validarse antes de usarse en toma de decisiones.
        </div>
        """, unsafe_allow_html=True)

    tabla_ajustable(df_vis, anio_sig, key_prefix="tab2")

# ============================================================
# TAB 3 — Supuestos y transparencia
# ============================================================
with tab3:
    st.markdown('<div class="seccion">Parámetros de la proyección</div>', unsafe_allow_html=True)

    col_p1, col_p2 = st.columns(2)
    with col_p1:
        st.markdown(f"""
        | Parámetro | Valor |
        |-----------|-------|
        | Tipo de balance | {tipo_sel} |
        | Nivel jerárquico | {nivel_sel} |
        | Método de cálculo | {metodo} |
        | Años históricos base | {', '.join(str(a) for a in sorted(anios_historicos))} |
        | Año en curso | {anio_curso} |
        | Año proyectado | {anio_sig} |
        | Factor ppto. año siguiente | {factor:.4f} ({(factor-1)*100:+.2f}%) |
        """)
    with col_p2:
        n_aj = len(st.session_state.ajustes_manuales)
        n_sin_hist = int(df_proy["supuesto"].str.contains("sin histórico", na=False).sum())
        n_intra    = int(df_proy["supuesto"].str.contains("intra-ejercicio", na=False).sum())
        st.markdown(f"""
        | Indicador | Valor |
        |-----------|-------|
        | Total celdas proyectadas | {len(df_proy[~df_proy.es_real]):,} |
        | Ajustes manuales aplicados | {n_aj} |
        | Celdas con supuesto intra-ejercicio | {n_intra} |
        | Celdas sin histórico | {n_sin_hist} |
        """)

    if st.session_state.ajustes_manuales:
        st.markdown('<div class="seccion">Log de ajustes manuales</div>', unsafe_allow_html=True)
        log_rows = []
        for (cuenta, anio, mes), pct_nuevo in sorted(st.session_state.ajustes_manuales.items()):
            fila = df_proy[
                (df_proy["cuenta"] == cuenta) &
                (df_proy["anio"]   == anio)   &
                (df_proy["mes"]    == mes)
            ]
            pct_orig = fila["pct_original"].iloc[0] if not fila.empty else None
            log_rows.append({
                "Cuenta":        cuenta,
                "Año":           anio,
                "Mes":           MESES_ES[mes],
                "% original":    fmt_pct(pct_orig),
                "% ajustado":    fmt_pct(pct_nuevo),
                "Δ puntos pct.": f"{(pct_nuevo - (pct_orig or 0))*100:+.2f}pp",
            })
        st.dataframe(pd.DataFrame(log_rows), use_container_width=True, hide_index=True)

        if st.button("🔄 Restablecer todos los ajustes"):
            st.session_state.ajustes_manuales = {}
            st.session_state.pop("_cache_key", None)
            st.rerun()

    st.markdown('<div class="seccion">Descripción de supuestos</div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="nota">
    <b>Histórico:</b> El % mensual se calculó directamente del comportamiento registrado
    en los años históricos seleccionados, usando {metodo.lower()}.<br><br>
    <b>Promedio intra-ejercicio:</b> La cuenta no tiene registro para ese mes en años anteriores.
    Se usó el promedio de ejecución mensual del mismo año en curso como sustituto.<br><br>
    <b>Sin histórico — sujeto a continuidad:</b> La cuenta no tiene datos en ningún año
    histórico anterior. Puede corresponder a una obra pública o programa que finaliza
    con el ejercicio {anio_curso}. Su proyección para {anio_sig} debe validarse.<br><br>
    <b>Ajuste manual:</b> El usuario modificó el % proyectado. El valor original queda
    registrado en el log de ajustes para trazabilidad.
    </div>
    """, unsafe_allow_html=True)

    # ---------------------------------------------------------------------------
    # Exportación
    # ---------------------------------------------------------------------------
    st.markdown('<div class="seccion">Exportar proyección</div>', unsafe_allow_html=True)

    col_dl1, col_dl2 = st.columns(2)

    with col_dl1:
        # Excel
        try:
            excel_bytes = generar_excel_proyeccion(df_vis, tipo_sel, anio_curso)
            st.download_button(
                label="⬇ Descargar Excel",
                data=excel_bytes,
                file_name=f"Penalolen_Proyeccion_{tipo_sel}_{anio_curso}_{anio_sig}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                help="Incluye datos reales, proyectados, % usados y hoja Léeme.",
            )
        except Exception as e:
            st.error(f"Error generando Excel: {e}")

    with col_dl2:
        # Reporte Markdown
        md_content = generar_reporte_md(
            df_proy=df_vis,
            tipo_balance=tipo_sel,
            nivel=nivel_sel,
            metodo=metodo,
            anios_historicos=anios_historicos,
            anio_curso=anio_curso,
            factor_anio_siguiente=factor,
            ajustes_manuales=st.session_state.ajustes_manuales,
        )
        st.download_button(
            label="⬇ Descargar reporte (.md)",
            data=md_content.encode("utf-8"),
            file_name=f"Penalolen_Reporte_Proyeccion_{tipo_sel}_{anio_curso}.md",
            mime="text/markdown",
            use_container_width=True,
            help="Reporte metodológico con supuestos, log de ajustes y nota de continuidad.",
        )

    st.markdown("""
    <div class="nota">
    <b>Sobre los archivos exportables:</b>
    El <b>Excel</b> contiene la proyección completa fila por fila, con columnas de % histórico,
    % usado, supuesto aplicado y flag de ajuste manual. Incluye hojas de resumen por año
    y una hoja Léeme con descripción de columnas.
    El <b>reporte Markdown</b> (.md) incluye los parámetros de la proyección, la descripción
    de cada supuesto, el log de ajustes manuales, las cuentas sujetas a continuidad
    y la nota metodológica general. Puede abrirse con cualquier editor de texto
    o visualizarse en GitHub, Notion u otras plataformas compatibles con Markdown.
    </div>
    """, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.markdown("""
<div class="footer">
  Municipalidad de Peñalolén &nbsp;·&nbsp; Portal de Transparencia Presupuestaria
  &nbsp;·&nbsp; Proyección basada en comportamiento histórico · No constituye compromiso de ejecución
</div>
""", unsafe_allow_html=True)
