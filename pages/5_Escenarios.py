"""
pages/5_Escenarios.py — Proyección plurianual con límites legales
=================================================================
Tres escenarios estructurados:
  A — Techo legal (automático): Contrata ≤ 40% Planta, Honor ≤ 10% Planta
  B — Histórico: comportamiento real proyectado
  C — Manual: definido libremente por el usuario

Incluye diagnóstico histórico de vulneraciones normativas.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from data_loader import cargar_datos
from scenario_engine import (
    Escenario, proyectar_escenario,
    resumen_anual_total,
    generar_reporte_escenarios_md, generar_excel_escenarios,
    MODOS_CRECIMIENTO, MAX_ANIOS_PROYECCION,
    NIVELES, MESES_ES, METODOS,
)
from compliance_engine import (
    diagnosticar_historico, historico_a_df,
    calcular_techo_legal, verificar_proyeccion,
    ITEM_PLANTA, ITEM_CONTRATA,
    LIMITE_CONTRATA, LIMITE_HONOR,
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
COLOR_ESC_A     = "#65930D"
COLOR_ESC_B     = "#0250C0"
COLOR_ESC_C     = "#FF8500"
COLOR_ALERTA    = "#BC092C"
COLOR_OK        = "#1B6B30"

# ---------------------------------------------------------------------------
# Configuración de página
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Escenarios de Personal · Peñalolén",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

st.markdown(f"""
<style>
    [data-testid="stSidebar"] {{ background-color: {COLOR_OSCURO}; }}
    
    [data-testid="stSidebar"] p, 
    [data-testid="stSidebar"] label {{ 
        color: {COLOR_BLANCO} !important; 
    }}
    
    [data-testid="stSidebar"] div[data-baseweb="select"] * {{
        color: #1E1E1E !important;
    }}
    
    [data-testid="stSidebar"] span[data-baseweb="tag"] {{
        background-color: {COLOR_PRINCIPAL} !important;
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
    .alerta-roja {{
        background:#FDECEA; border-left:4px solid {COLOR_ALERTA};
        border-radius:7px; padding:12px 16px;
        font-size:0.82rem; color:#5A0000; line-height:1.6; margin-bottom:10px;
    }}
    .alerta-verde {{
        background:#E6F4EA; border-left:4px solid {COLOR_OK};
        border-radius:7px; padding:12px 16px;
        font-size:0.82rem; color:#0A3D26; line-height:1.6; margin-bottom:10px;
    }}
    .aviso-box {{
        background:#FFFBEA; border-left:4px solid #FFC107;
        border-radius:7px; padding:10px 14px;
        font-size:0.80rem; color:#5A4000; line-height:1.55; margin-bottom:12px;
    }}
    .esc-header {{
        font-size:0.88rem; font-weight:700; padding:6px 12px;
        border-radius:6px; margin-bottom:12px; display:inline-block;
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

def fmt_m(v):
    if v is None: return "—"
    v = float(v)
    if abs(v) >= 1_000_000_000: return f"${v/1e9:,.2f} MM"
    return f"${v/1e6:,.1f} M"

# ---------------------------------------------------------------------------
# Carga de datos
# ---------------------------------------------------------------------------

df_gastos, _ = cargar_datos("data")

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown(
        "<div style='padding:10px 0 18px 0; color: #FFFFFF;'>"
        "<span style='font-size:1.1rem;font-weight:700;'>🏛️ Peñalolén</span><br>"
        "<span style='font-size:0.8rem;opacity:0.7;'>Transparencia Presupuestaria</span>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")

    anios_disp      = sorted(df_gastos["anio"].unique(), reverse=True)
    anio_base       = st.selectbox("Año de referencia", anios_disp, index=0)
    anios_hist_disp = [a for a in anios_disp if a < anio_base]

    anios_historicos = st.multiselect(
        "Años históricos", anios_hist_disp,
        default=anios_hist_disp[:min(3, len(anios_hist_disp))],
    )
    if not anios_historicos:
        st.warning("Selecciona al menos un año histórico.")
        st.stop()

    nivel_sel = st.selectbox("Nivel jerárquico", list(NIVELES.keys()), index=1)
    metodo    = st.selectbox("Método % mensual", METODOS, index=0)
    n_anios   = st.slider("Años a proyectar", 1, MAX_ANIOS_PROYECCION, 8)
    anios_proyeccion = list(range(anio_base + 1, anio_base + n_anios + 1))

    st.markdown("---")
    col_n     = NIVELES[nivel_sel]
    df_ref    = df_gastos[df_gastos["anio"] == anio_base]
    ctas_disp = sorted(df_ref[col_n].unique())
    personal_default = [c for c in [ITEM_PLANTA, ITEM_CONTRATA, "OTRAS REMUNERACIONES"] if c in ctas_disp]
    cuentas_sel = st.multiselect("Cuentas incluidas", ctas_disp, default=personal_default)
    cuentas_filtro = cuentas_sel if cuentas_sel else None

    st.markdown("---")
    st.markdown(
        "<span style='font-size:0.75rem;opacity:0.6;'>"
        "Límites: Contrata ≤ 40% Planta · Honorarios ≤ 10% Planta<br>"
        "Ley N° 18.834 · Ley de Presupuestos</span>",
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.markdown(f"""
<div class="header-strip">
  <h1>📊 Escenarios de gasto en personal — proyección plurianual</h1>
  <p>Municipalidad de Peñalolén &nbsp;·&nbsp;
     Base: {anio_base} &nbsp;·&nbsp;
     Horizonte: {anio_base+1}–{anio_base+n_anios} &nbsp;·&nbsp;
     Límites Ley N° 18.834 y Ley de Presupuestos
  </p>
</div>
""", unsafe_allow_html=True)

if "ajustes_pct_esc" not in st.session_state:
    st.session_state.ajustes_pct_esc = {}

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_diag, tab_esc, tab_comp, tab_exp = st.tabs([
    "🔎 Diagnóstico histórico",
    "⚙️ Escenarios",
    "📈 Comparativa",
    "⬇️ Exportar",
])

# ============================================================
# TAB 1 — Diagnóstico histórico
# ============================================================
with tab_diag:
    st.markdown('<div class="seccion">Cumplimiento normativo en datos reales</div>', unsafe_allow_html=True)

    resultados_hist = diagnosticar_historico(df_gastos)
    df_hist = historico_a_df(resultados_hist)

    if df_hist.empty:
        st.info("No hay datos suficientes para el diagnóstico.")
    else:
        # Alertas del último cierre
        ult_anio = df_hist["anio"].max()
        ult_mes  = df_hist[df_hist["anio"] == ult_anio]["mes_cierre"].max()
        df_ult   = df_hist[
            (df_hist["anio"] == ult_anio) &
            (df_hist["mes_cierre"] == ult_mes) &
            (df_hist["columna"] == "DEVENGADO_ACUMULADO")
        ]

        for _, row in df_ult.iterrows():
            lim_pct = LIMITE_CONTRATA if "Contrata" in row["limite"] else LIMITE_HONOR
            clase   = "alerta-roja" if row["vulnerado"] else "alerta-verde"
            icono   = "⚠" if row["vulnerado"] else "✓"
            estado  = "VULNERADO" if row["vulnerado"] else "CUMPLIDO"
            exceso_txt = f" — exceso: {fmt_m(row['exceso'])}" if row["vulnerado"] else ""
            st.markdown(f"""
            <div class="{clase}">
              <b>{icono} Límite {row['limite']} — {estado}</b>{exceso_txt}<br>
              Ratio actual: {row['ratio_actual_%']:.1f}% (límite: {lim_pct*100:.0f}%)
              &nbsp;·&nbsp; Planta: {fmt_m(row['valor_planta'])}
              &nbsp;·&nbsp; Máximo permitido: {fmt_m(row['maximo_permitido'])}
              &nbsp;·&nbsp; Valor actual: {fmt_m(row['valor_restringido'])}
            </div>
            """, unsafe_allow_html=True)

        # Gráfico histórico
        st.markdown('<div class="seccion">Evolución del ratio de cumplimiento</div>', unsafe_allow_html=True)
        col_vis = st.selectbox(
            "Columna", ["DEVENGADO_ACUMULADO", "PRESUPUESTO_VIGENTE", "PRESUPUESTO_INICIAL"],
            key="col_diag",
        )

        fig_h = go.Figure()
        for lim_nom, col_lim, lim_val in [
            ("Contrata / Planta", COLOR_ESC_B, LIMITE_CONTRATA),
            ("Honorarios / Planta", COLOR_ACENTO, LIMITE_HONOR),
        ]:
            df_l = df_hist[
                (df_hist["limite"] == lim_nom) & (df_hist["columna"] == col_vis)
            ].sort_values(["anio", "mes_cierre"]).copy()
            if df_l.empty: continue

            df_l["periodo"] = df_l["anio"].astype(str) + "-" + df_l["mes_cierre"].map(
                lambda m: MESES_ES.get(m, str(m))[:3]
            )
            fig_h.add_trace(go.Scatter(
                x=df_l["periodo"], y=df_l["ratio_actual_%"],
                mode="lines+markers", name=lim_nom,
                line=dict(color=col_lim, width=2.5),
                marker=dict(
                    size=8,
                    color=[COLOR_ALERTA if v else col_lim for v in df_l["vulnerado"]],
                    symbol=["x" if v else "circle" for v in df_l["vulnerado"]],
                ),
                hovertemplate=f"<b>{lim_nom}</b><br>%{{x}}: %{{y:.1f}}%<extra></extra>",
            ))
            fig_h.add_hline(
                y=lim_val * 100, line_dash="dot", line_color=col_lim, line_width=1.5,
                annotation_text=f"Límite {lim_nom}: {lim_val*100:.0f}%",
                annotation_position="top right",
                annotation_font_size=11, annotation_font_color=col_lim,
            )

        fig_h.update_layout(
            height=380, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="sans-serif", size=11, color=COLOR_TEXTO),
            margin=dict(t=20, l=10, r=10, b=60),
            xaxis=dict(showgrid=True, gridcolor="#EEF2FB", tickangle=-45),
            yaxis=dict(showgrid=True, gridcolor="#EEF2FB", ticksuffix="%"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
            hovermode="x unified",
            hoverlabel=dict(bgcolor=COLOR_OSCURO, font_color=COLOR_BLANCO,
                            font_size=12, bordercolor=COLOR_PRINCIPAL),
        )
        st.plotly_chart(fig_h, use_container_width=True)

        # Tabla detallada
        st.markdown('<div class="seccion">Detalle por cierre</div>', unsafe_allow_html=True)
        df_tbl = df_hist[df_hist["columna"] == col_vis].copy()
        df_tbl["Mes"]    = df_tbl["mes_cierre"].map(MESES_ES)
        df_tbl["Ratio"]  = df_tbl["ratio_actual_%"].apply(lambda x: f"{x:.1f}%")
        df_tbl["Exceso"] = df_tbl["exceso"].apply(lambda x: fmt_m(x) if x > 0 else "—")
        df_tbl["Estado"] = df_tbl["vulnerado"].map({True: "⚠ VULNERADO", False: "✓ OK"})
        st.dataframe(
            df_tbl[["anio","Mes","limite","Ratio","Exceso","Estado"]].rename(
                columns={"anio":"Año","limite":"Límite"}
            ),
            use_container_width=True, hide_index=True,
        )

        st.markdown(f"""
        <div class="nota">
        <b>Fuente normativa:</b>
        El límite del 40% de Contrata sobre Planta está en la
        <b>Ley N° 18.834 (Estatuto Administrativo), Art. 9°</b>
        y se reitera en glosas de la Ley de Presupuestos.
        El 10% para honorarios corresponde a glosa del Subtítulo 21.
        La medición principal es sobre <b>devengado acumulado anual</b>.
        <br><br>
        <b>Aviso:</b> La vulneración detectada puede tener explicaciones normativas
        específicas (glosas de excepción, decretos de urgencia).
        Validar con Contraloría o el Departamento Jurídico antes de
        usar este diagnóstico para efectos de responsabilidad administrativa.
        </div>
        """, unsafe_allow_html=True)

# ============================================================
# TAB 2 — Configuración de escenarios
# ============================================================
with tab_esc:

    # Escenario A — Techo legal
    st.markdown(
        f"<div class='esc-header' style='background:{COLOR_ESC_A};color:#FFF;'>"
        f"Escenario A — Techo legal (automático)</div>",
        unsafe_allow_html=True,
    )
    st.markdown("""
    <div class="aviso-box">
    Calcula automáticamente el presupuesto máximo permitido por norma.
    Define la tasa de crecimiento de Planta — los techos de Contrata
    y Honorarios se recalculan solos.
    </div>
    """, unsafe_allow_html=True)

    tasa_planta_a = st.slider(
        "Crecimiento anual de Planta — Escenario A (%)",
        0.0, 30.0, 5.0, 0.5, format="%.1f%%", key="tasa_a",
    )
    desc_a = st.text_input(
        "Descripción escenario A",
        value=f"Máximo legal: Contrata ≤ 40% · Honorarios ≤ 10% · Planta +{tasa_planta_a:.1f}%/año",
        key="desc_a",
    )

    st.markdown("---")

    # Escenario B — Histórico
    st.markdown(
        f"<div class='esc-header' style='background:{COLOR_ESC_B};color:#FFF;'>"
        f"Escenario B — Proyección histórica</div>",
        unsafe_allow_html=True,
    )
    col_b1, col_b2 = st.columns(2)
    with col_b1:
        modo_b  = st.selectbox("Modo de crecimiento", MODOS_CRECIMIENTO, index=0, key="modo_b")
    with col_b2:
        tasa_b  = st.slider("Tasa anual (%)", -10.0, 30.0, 0.0, 0.5, format="%.1f%%", key="tasa_b") \
                  if modo_b == "Tasa fija anual" else 0.0
    tasas_b  = {}; montos_b = {}
    if modo_b == "Tasa distinta por año":
        cols_tb = st.columns(min(4, n_anios))
        for j, ap in enumerate(anios_proyeccion[:min(4, n_anios)]):
            with cols_tb[j]:
                tasas_b[ap] = st.number_input(f"{ap} (%)", value=3.0, min_value=-20.0,
                    max_value=30.0, step=0.5, format="%.1f", key=f"tb_{ap}") / 100
    elif modo_b == "Monto absoluto por año":
        df_r = df_gastos[(df_gastos["anio"] == anio_base)]
        if cuentas_filtro: df_r = df_r[df_r[NIVELES[nivel_sel]].isin(cuentas_filtro)]
        mx = df_r["mes_cierre"].max() if not df_r.empty else 0
        ps = df_r[df_r["mes_cierre"] == mx]["PRESUPUESTO_VIGENTE"].sum()
        cols_mb = st.columns(min(4, n_anios))
        for j, ap in enumerate(anios_proyeccion[:min(4, n_anios)]):
            with cols_mb[j]:
                montos_b[ap] = st.number_input(f"{ap} (M$)", value=round(ps/1e6, 1),
                    min_value=0.0, step=100.0, format="%.1f", key=f"mb_{ap}") * 1e6
    desc_b = st.text_input("Descripción escenario B",
        value="Comportamiento histórico proyectado", key="desc_b")

    st.markdown("---")

    # Escenario C — Manual
    st.markdown(
        f"<div class='esc-header' style='background:{COLOR_ESC_C};color:#FFF;'>"
        f"Escenario C — Definición manual</div>",
        unsafe_allow_html=True,
    )
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        modo_c = st.selectbox("Modo de crecimiento", MODOS_CRECIMIENTO, index=0, key="modo_c")
    with col_c2:
        tasa_c = st.slider("Tasa anual (%)", -10.0, 50.0, 8.0, 0.5, format="%.1f%%", key="tasa_c") \
                 if modo_c == "Tasa fija anual" else 0.0
    tasas_c  = {}; montos_c = {}
    if modo_c == "Tasa distinta por año":
        cols_tc = st.columns(min(4, n_anios))
        for j, ap in enumerate(anios_proyeccion[:min(4, n_anios)]):
            with cols_tc[j]:
                tasas_c[ap] = st.number_input(f"{ap} (%)", value=8.0, min_value=-20.0,
                    max_value=50.0, step=0.5, format="%.1f", key=f"tc_{ap}") / 100
    elif modo_c == "Monto absoluto por año":
        df_r2 = df_gastos[(df_gastos["anio"] == anio_base)]
        if cuentas_filtro: df_r2 = df_r2[df_r2[NIVELES[nivel_sel]].isin(cuentas_filtro)]
        mx2 = df_r2["mes_cierre"].max() if not df_r2.empty else 0
        ps2 = df_r2[df_r2["mes_cierre"] == mx2]["PRESUPUESTO_VIGENTE"].sum()
        cols_mc = st.columns(min(4, n_anios))
        for j, ap in enumerate(anios_proyeccion[:min(4, n_anios)]):
            with cols_mc[j]:
                montos_c[ap] = st.number_input(f"{ap} (M$)",
                    value=round(ps2/1e6*(1.08**(j+1)), 1),
                    min_value=0.0, step=100.0, format="%.1f", key=f"mc_{ap}") * 1e6
    desc_c = st.text_input("Descripción escenario C",
        value="Aumento de planta municipal — escenario propuesto", key="desc_c")

# ---------------------------------------------------------------------------
# Construir escenarios y calcular
# ---------------------------------------------------------------------------

# Techo legal para Escenario A
df_base_r   = df_gastos[df_gastos["anio"] == anio_base]
mes_max_r   = df_base_r["mes_cierre"].max() if not df_base_r.empty else 0
ppto_planta_base = df_base_r[
    (df_base_r["mes_cierre"] == mes_max_r) &
    (df_base_r[NIVELES[nivel_sel]] == ITEM_PLANTA)
]["PRESUPUESTO_VIGENTE"].sum()

ppto_planta_anio = {
    a: ppto_planta_base * ((1 + tasa_planta_a/100) ** (a - anio_base))
    for a in [anio_base] + anios_proyeccion
}
techo = calcular_techo_legal(
    df=df_gastos, anio_base=anio_base,
    anios_proyeccion=anios_proyeccion,
    ppto_planta_por_anio=ppto_planta_anio,
)
montos_a = {a: techo[ITEM_CONTRATA][a] for a in [anio_base] + anios_proyeccion}

esc_a = Escenario(nombre="A — Techo legal", color=COLOR_ESC_A,
    modo="Monto absoluto por año", montos_por_anio=montos_a, descripcion=desc_a)
esc_b = Escenario(nombre="B — Histórico", color=COLOR_ESC_B,
    modo=modo_b, tasa_fija=tasa_b, tasas_por_anio=tasas_b,
    montos_por_anio=montos_b, descripcion=desc_b)
esc_c = Escenario(nombre="C — Manual", color=COLOR_ESC_C,
    modo=modo_c, tasa_fija=tasa_c, tasas_por_anio=tasas_c,
    montos_por_anio=montos_c, descripcion=desc_c)
escenarios_lista = [esc_a, esc_b, esc_c]

@st.cache_data(show_spinner="Calculando escenarios…")
def calcular(esc_ser, nivel, metodo, anios_hist, anio_base, anios_proy, cuentas, ajustes):
    ajustes_d = {(c, m): p for c, m, p in ajustes}
    return [
        proyectar_escenario(
            df=df_gastos, nivel=nivel, metodo=metodo,
            anios_historicos=list(anios_hist), anio_base=anio_base,
            anios_proyeccion=list(anios_proy),
            escenario=Escenario(**d),
            cuentas_filtro=list(cuentas) if cuentas else None,
            ajustes_pct_manuales=ajustes_d,
        )
        for d in esc_ser
    ]

esc_ser = [{"nombre": e.nombre, "color": e.color, "modo": e.modo,
             "tasa_fija": e.tasa_fija, "tasas_por_anio": e.tasas_por_anio,
             "montos_por_anio": e.montos_por_anio, "descripcion": e.descripcion}
           for e in escenarios_lista]
ajustes_t = tuple((c, m, p) for (c, m), p in st.session_state.ajustes_pct_esc.items())

df_proyecciones = calcular(
    esc_ser=esc_ser, nivel=nivel_sel, metodo=metodo,
    anios_hist=tuple(sorted(anios_historicos)),
    anio_base=anio_base, anios_proy=tuple(anios_proyeccion),
    cuentas=tuple(cuentas_filtro) if cuentas_filtro else None,
    ajustes=ajustes_t,
)

# ============================================================
# TAB 3 — Comparativa
# ============================================================
with tab_comp:
    st.markdown('<div class="seccion">Gasto anual proyectado — tres escenarios</div>', unsafe_allow_html=True)

    vista = st.radio("Vista", ["Líneas", "Barras agrupadas"], horizontal=True, key="vista")
    fig_c = go.Figure()
    res_todos = []

    for esc, df_p in zip(escenarios_lista, df_proyecciones):
        res = resumen_anual_total(df_p)
        res_todos.append(res)
        x = res["anio"].tolist()
        y = res["monto_anual"].tolist()
        if vista == "Líneas":
            fig_c.add_trace(go.Scatter(
                x=x, y=y, mode="lines+markers", name=esc.nombre,
                line=dict(color=esc.color, width=2.5,
                          dash="dash" if esc == esc_a else "solid"),
                marker=dict(size=7, color=esc.color),
                hovertemplate=f"<b>{esc.nombre}</b><br>%{{x}}: %{{y:$,.0f}}<extra></extra>",
            ))
        else:
            fig_c.add_trace(go.Bar(x=x, y=y, name=esc.nombre,
                marker_color=esc.color,
                hovertemplate=f"<b>{esc.nombre}</b><br>%{{x}}: %{{y:$,.0f}}<extra></extra>"))

    # Línea de techo legal total como referencia
    techo_total = {
        a: techo[ITEM_CONTRATA].get(a, 0) + techo["HONORARIOS"].get(a, 0)
        for a in [anio_base] + anios_proyeccion
    }
    fig_c.add_trace(go.Scatter(
        x=list(techo_total.keys()), y=list(techo_total.values()),
        mode="lines", name="Techo legal total (ref.)",
        line=dict(color=COLOR_ALERTA, width=1.5, dash="dot"),
        hovertemplate="<b>Techo legal</b><br>%{x}: %{y:$,.0f}<extra></extra>",
    ))

    fig_c.add_vline(x=anio_base, line_dash="dot", line_color=COLOR_AUXILIAR,
        line_width=1.5, annotation_text=f"Base ({anio_base})",
        annotation_position="top left", annotation_font_size=11,
        annotation_font_color=COLOR_AUXILIAR)

    if vista == "Barras agrupadas":
        fig_c.update_layout(barmode="group")

    fig_c.update_layout(
        height=430, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="sans-serif", size=12, color=COLOR_TEXTO),
        margin=dict(t=20, l=10, r=10, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        xaxis=dict(showgrid=True, gridcolor="#EEF2FB", tickmode="linear", dtick=1),
        yaxis=dict(showgrid=True, gridcolor="#EEF2FB", tickformat="$,.0f"),
        hovermode="x unified",
        hoverlabel=dict(bgcolor=COLOR_OSCURO, font_color=COLOR_BLANCO,
                        font_size=12, bordercolor=COLOR_PRINCIPAL),
    )
    st.plotly_chart(fig_c, use_container_width=True)

    # Verificación de límites por escenario
    st.markdown('<div class="seccion">Verificación de límites legales en proyección</div>', unsafe_allow_html=True)
    for esc, df_p in zip(escenarios_lista, df_proyecciones):
        # Agregar por cuenta×anio preservando la dimensión cuenta
        # resumen_anual_total la pierde al agrupar solo por escenario×anio
        df_p_cta = (
            df_p.groupby(["cuenta", "anio"])["monto_mensual"]
            .sum().reset_index()
            .rename(columns={"monto_mensual": "monto_anual"})
        )
        verif = verificar_proyeccion(df_p_cta, techo)
        if verif.empty:
            continue
        vuln = verif[verif["vulnerado"]]
        if not vuln.empty:
            anios_vuln = ", ".join(str(int(a)) for a in sorted(vuln["anio"].unique()))
            st.markdown(f"""
            <div class="alerta-roja">
            <b>⚠ {esc.nombre}:</b> Vulneración proyectada en {len(vuln)} año(s): {anios_vuln}.
            Los montos proyectados superan el límite legal. Requiere ajuste presupuestario.
            </div>""", unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="alerta-verde">
            <b>✓ {esc.nombre}:</b> Todos los años proyectados cumplen los límites legales.
            </div>""", unsafe_allow_html=True)

    # Tabla comparativa
    st.markdown('<div class="seccion">Tabla comparativa anual</div>', unsafe_allow_html=True)
    tbl = pd.DataFrame({"Año": sorted(set(a for r in res_todos for a in r["anio"]))})
    for esc, res in zip(escenarios_lista, res_todos):
        mp = res.set_index("anio")["monto_anual"].to_dict()
        tbl[esc.nombre] = tbl["Año"].map(lambda a, m=mp: fmt_m(m.get(a, 0)))
    tbl["Techo legal"] = tbl["Año"].map(lambda a, t=techo_total: fmt_m(t.get(a, 0)))
    st.dataframe(tbl, use_container_width=True, hide_index=True)

    st.markdown(f"""
    <div class="nota">
    <b>Techo legal:</b> Suma del máximo de Contrata (40% Planta) + Honorarios (10% Planta)
    con Planta creciendo al {tasa_planta_a:.1f}%/año desde {anio_base}.
    Montos nominales en CLP sin ajuste por inflación.
    </div>
    """, unsafe_allow_html=True)

# ============================================================
# TAB 4 — Exportar
# ============================================================
with tab_exp:
    st.markdown('<div class="seccion">Exportar</div>', unsafe_allow_html=True)
    col_xl, col_md = st.columns(2)

    with col_xl:
        try:
            xl = generar_excel_escenarios(escenarios_lista, df_proyecciones, anio_base)
            st.download_button("⬇ Excel (escenarios)", xl,
                f"Penalolen_Escenarios_{anio_base}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True)
        except Exception as e:
            st.error(f"Error Excel: {e}")

    with col_md:
        md = generar_reporte_escenarios_md(
            escenarios_lista, df_proyecciones, nivel_sel, metodo,
            anios_historicos, anio_base, anios_proyeccion, cuentas_filtro,
            st.session_state.ajustes_pct_esc,
        ).encode("utf-8")
        st.download_button("⬇ Reporte (.md)", md,
            f"Penalolen_Reporte_Escenarios_{anio_base}.md",
            "text/markdown", use_container_width=True)

    if not df_hist.empty:
        st.markdown('<div class="seccion">Diagnóstico de cumplimiento normativo</div>', unsafe_allow_html=True)
        csv_h = df_hist.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button("⬇ Diagnóstico histórico (CSV)", csv_h,
            f"Penalolen_Diagnostico_Limites_{anio_base}.csv",
            "text/csv", use_container_width=True)

    st.markdown("""
    <div class="nota">
    <b>Escenario A — Techo legal:</b> Representa el máximo legalmente permitido,
    no una recomendación de gasto. Operar exactamente en el techo no deja margen de ajuste.
    <br><br>
    <b>Diagnóstico histórico:</b> La vulneración sistemática puede tener explicaciones
    normativas específicas. Validar con Contraloría o Departamento Jurídico antes de
    usar para efectos de responsabilidad administrativa.
    </div>
    """, unsafe_allow_html=True)

st.markdown("""
<div class="footer">
  Municipalidad de Peñalolén &nbsp;·&nbsp; Portal de Transparencia Presupuestaria
  &nbsp;·&nbsp; Límites: Ley N° 18.834 · CLP nominales sin ajuste por inflación
</div>
""", unsafe_allow_html=True)
