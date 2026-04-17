"""
app.py — Transparencia Presupuestaria · Municipalidad de Peñalolén
==================================================================
Lógica de ejecución presupuestaria:
  - Gastos 100% ejecutado  = DEVENGADO_ACUMULADO / PRESUPUESTO_VIGENTE
  - Ingresos 100% ejecutado = PERCIBIDO_ACUMULADO / PRESUPUESTO_VIGENTE
  - % pagado sobre devengado y % percibido sobre devengado son
    indicadores de liquidez/cobro, no de ejecución presupuestaria.
  - Se permiten valores >100% (sobredevengado / sobrepercibido).
"""

import streamlit as st
import pandas as pd

from data_loader import cargar_datos

# ---------------------------------------------------------------------------
# Paleta institucional
# ---------------------------------------------------------------------------

COLOR_PRINCIPAL  = "#0250C0"
COLOR_OSCURO     = "#222957"
COLOR_ACENTO     = "#FF8500"
COLOR_AUXILIAR   = "#3A5694"
COLOR_FONDO_CARD = "#F5F7FC"
COLOR_BARRA_BASE = "#D6E4F7"
COLOR_TEXTO      = "#1E1E1E"
COLOR_BLANCO     = "#FFFFFF"

# ---------------------------------------------------------------------------
# Configuración de página (debe ser la primera llamada Streamlit)
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Transparencia Presupuestaria · Municipalidad de Peñalolén",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# CSS institucional
# ---------------------------------------------------------------------------

st.markdown(f"""
<style>
[data-testid="stAppViewContainer"] {{
        background-color: #FFFFFF;
    }}
    [data-testid="stSidebar"] {{ background-color: {COLOR_OSCURO}; }}
    [data-testid="stSidebar"] * {{ color: {COLOR_BLANCO} !important; }}
    [data-testid="stPageLink"] a {{
        background-color: {COLOR_BLANCO};
        color: #222957 !important; 
        border: 1px solid #DDE4F0;
        border-radius: 8px;
        padding: 8px 12px;
        text-decoration: none;
        transition: all 0.3s ease;
        display: inline-flex;
    }}

    /* Efecto al pasar el ratón */
    [data-testid="stPageLink"] a:hover {{
        background-color: #E8F0FE;
        border-color: {COLOR_PRINCIPAL};
        color: #FF8500 !important;
        transform: translateY(-1px);
    }}

    /* Efecto al hacer clic */
    [data-testid="stPageLink"] a:active {{
        transform: translateY(0px);
    }}
    .header-strip h1 {{
        font-size: 1.7rem; font-weight: 700; margin: 0 0 4px 0;
        color: {COLOR_BLANCO}; letter-spacing: 0.01em;
    }}
    .header-strip p {{ font-size: 0.95rem; margin: 0; opacity: 0.85; color: {COLOR_BLANCO}; }}

    .kpi-card {{
        background: {COLOR_FONDO_CARD};
        border-left: 5px solid {COLOR_PRINCIPAL};
        border-radius: 8px; padding: 18px 20px 14px 20px; margin-bottom: 4px;
    }}
    .kpi-card.acento {{ border-left-color: {COLOR_ACENTO}; }}
    .kpi-label {{
        font-size: 0.78rem; font-weight: 600; text-transform: uppercase;
        letter-spacing: 0.07em; color: {COLOR_AUXILIAR}; margin-bottom: 4px;
    }}
    .kpi-value {{ font-size: 1.75rem; font-weight: 700; color: {COLOR_OSCURO}; line-height: 1.1; }}
    .kpi-sub {{ font-size: 0.82rem; color: #555; margin-top: 4px; }}
    .kpi-badge {{
        display: inline-block; font-size: 0.78rem; font-weight: 600;
        padding: 2px 9px; border-radius: 12px; margin-top: 6px;
    }}
    .badge-ok   {{ background: #E6F4EA; color: #1B6B30; }}
    .badge-warn {{ background: #FFF3E0; color: #8B4A00; }}
    .badge-info {{ background: #E8F0FE; color: #1A3A7A; }}
    .badge-over {{ background: #FDECEA; color: #8B1A1A; }}

    .intro-box {{
        background: {COLOR_BLANCO}; border: 1px solid #DDE4F0;
        border-radius: 10px; padding: 24px 28px; margin-bottom: 28px;
        line-height: 1.75; color: {COLOR_TEXTO};
    }}
    .intro-box h3 {{ color: {COLOR_OSCURO}; font-size: 1.05rem; margin-bottom: 10px; }}

    .nav-card {{
        background: {COLOR_BLANCO}; border: 1.5px solid #C9D6EE;
        border-radius: 10px; padding: 20px 20px 16px 20px; text-align: center;
    }}
    .nav-card .nav-icon {{ font-size: 2rem; margin-bottom: 8px; }}
    .nav-card h4 {{ color: {COLOR_OSCURO}; font-size: 0.97rem; font-weight: 700; margin: 0 0 6px 0; }}
    .nav-card p {{ font-size: 0.82rem; color: #555; margin: 0; line-height: 1.5; }}

    .nota-metodologica {{
        background: #EEF2FB; border-radius: 8px; padding: 14px 18px;
        font-size: 0.82rem; color: #333; line-height: 1.65; margin-top: 8px;
    }}
    .nota-metodologica b {{ color: {COLOR_OSCURO}; }}

    .progress-row {{ margin-bottom: 10px; }}
    .progress-label {{
        font-size: 0.8rem; font-weight: 600; color: {COLOR_TEXTO};
        margin-bottom: 3px; display: flex; justify-content: space-between;
    }}
    .progress-track {{
        background: {COLOR_BARRA_BASE}; border-radius: 6px;
        height: 13px; width: 100%; overflow: hidden;
    }}
    .progress-fill {{
        height: 13px; border-radius: 6px; background: {COLOR_PRINCIPAL};
    }}
    .progress-fill.naranja {{ background: {COLOR_ACENTO}; }}
    .progress-over {{
        height: 13px; border-radius: 6px;
        background: repeating-linear-gradient(
            90deg, #BC092C 0px, #BC092C 6px, #F09595 6px, #F09595 10px
        );
        width: 100%;
    }}

    .section-title {{
        font-size: 0.82rem; font-weight: 700; text-transform: uppercase;
        letter-spacing: 0.08em; color: {COLOR_AUXILIAR};
        border-bottom: 2px solid {COLOR_BARRA_BASE};
        padding-bottom: 6px; margin: 28px 0 16px 0;
    }}
    .footer {{
        text-align: center; font-size: 0.75rem; color: #888;
        margin-top: 48px; padding-top: 16px; border-top: 1px solid #DDE4F0;
    }}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MESES_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}


def fmt_millones(valor: float) -> str:
    if abs(valor) >= 1_000_000_000:
        return f"${valor / 1_000_000_000:,.2f} MM"
    return f"${valor / 1_000_000:,.1f} M"


def badge(pct: float, label: str = "ejecutado") -> str:
    """
    Badge semántico de ejecución.
    >100%: rojo (sobredevengado/sobrepercibido) | >=70%: verde
    >=40%: naranja | <40%: azul informativo
    """
    texto = f"{pct:.1f}% {label}"
    if pct > 100:
        return f'<span class="kpi-badge badge-over">{texto} &#9888;</span>'
    elif pct >= 70:
        return f'<span class="kpi-badge badge-ok">{texto}</span>'
    elif pct >= 40:
        return f'<span class="kpi-badge badge-warn">{texto}</span>'
    return f'<span class="kpi-badge badge-info">{texto}</span>'


def barra_html(pct: float, naranja: bool = False) -> str:
    """
    Barra de progreso. Sobre 100% muestra patrón rayado rojo;
    la barra nunca supera visualmente el 100% del contenedor.
    """
    if pct > 100:
        return '<div class="progress-track"><div class="progress-over"></div></div>'
    pct_v = max(pct, 0)
    cls = "naranja" if naranja else ""
    return (
        f'<div class="progress-track">'
        f'<div class="progress-fill {cls}" style="width:{pct_v:.1f}%"></div>'
        f'</div>'
    )


def cierre_reciente(df: pd.DataFrame, anio: int) -> pd.DataFrame:
    sub = df[df["anio"] == anio]
    if sub.empty:
        return pd.DataFrame()
    return sub[sub["mes_cierre"] == sub["mes_cierre"].max()]


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
    anios = sorted(
        set(df_gastos["anio"].unique()) | set(df_ingresos["anio"].unique()),
        reverse=True,
    )
    anio_sel = st.selectbox("Año presupuestario", options=anios, index=0)
    st.markdown("---")
    st.markdown(
        "<span style='font-size:0.75rem;opacity:0.6;'>"
        "Información oficial extraída del ERP contable municipal. "
        "Actualización mensual.</span>",
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.markdown(f"""
<div class="header-strip">
  <h1>🏛️ Transparencia Presupuestaria</h1>
  <p>Municipalidad de Peñalolén &nbsp;·&nbsp;
     Ejecución presupuestaria {anio_sel} &nbsp;·&nbsp; Datos oficiales</p>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Introducción
# ---------------------------------------------------------------------------

st.markdown("""
<div class="intro-box">
  <h3>¿Qué es este portal?</h3>
  Este portal permite conocer en detalle cómo la Municipalidad de Peñalolén ejecuta
  su presupuesto a lo largo del año. La información proviene directamente del sistema
  contable municipal y se actualiza mensualmente con cada cierre contable oficial.
  <br><br>
  Aquí puedes explorar <b>cuánto se ha devengado o percibido</b> respecto del presupuesto
  vigente, <b>cómo se distribuyen el gasto y los ingresos</b> por área de gestión,
  y <b>cómo evoluciona la ejecución mes a mes</b> frente a años anteriores.
  <br><br>
  Usa el menú lateral para navegar entre los módulos de análisis.
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# KPIs — cálculo
# ---------------------------------------------------------------------------

df_g_sel = cierre_reciente(df_gastos,  anio_sel)
df_i_sel = cierre_reciente(df_ingresos, anio_sel)

ppto_g    = df_g_sel["PRESUPUESTO_VIGENTE"].sum()  if not df_g_sel.empty else 0
dev_g     = df_g_sel["DEVENGADO_ACUMULADO"].sum()  if not df_g_sel.empty else 0
pagado    = (df_g_sel["PAGADO_ACUMULADO"].sum()
             if not df_g_sel.empty and "PAGADO_ACUMULADO" in df_g_sel.columns else 0)

ppto_i    = df_i_sel["PRESUPUESTO_VIGENTE"].sum()  if not df_i_sel.empty else 0
dev_i     = df_i_sel["DEVENGADO_ACUMULADO"].sum()  if not df_i_sel.empty else 0
percibido = (df_i_sel["PERCIBIDO_ACUMULADO"].sum()
             if not df_i_sel.empty and "PERCIBIDO_ACUMULADO" in df_i_sel.columns else 0)

# Ejecución presupuestaria (denominador = presupuesto vigente)
pct_ejec_gasto   = dev_g     / ppto_g * 100 if ppto_g > 0 else 0
pct_ejec_ingreso = percibido / ppto_i * 100 if ppto_i > 0 else 0

# Liquidez / cobro (denominador = devengado acumulado)
pct_pagado_dev = pagado    / dev_g * 100 if dev_g > 0 else 0
pct_percib_dev = percibido / dev_i * 100 if dev_i > 0 else 0

mes_g_lbl = MESES_ES.get(int(df_g_sel["mes_cierre"].max()) if not df_g_sel.empty else 0, "—")
mes_i_lbl = MESES_ES.get(int(df_i_sel["mes_cierre"].max()) if not df_i_sel.empty else 0, "—")

# ---------------------------------------------------------------------------
# KPIs — visualización
# ---------------------------------------------------------------------------

st.markdown('<div class="section-title">Resumen de ejecución</div>', unsafe_allow_html=True)

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown(f"""
    <div class="kpi-card">
      <div class="kpi-label">% gasto ejecutado</div>
      <div class="kpi-value">{fmt_millones(dev_g)}</div>
      <div class="kpi-sub">
        devengado acumulado &nbsp;/&nbsp; ppto. vigente {fmt_millones(ppto_g)}
        &nbsp;·&nbsp; cierre {mes_g_lbl}
      </div>
      {badge(pct_ejec_gasto, "ejecutado")}
      {barra_html(pct_ejec_gasto)}
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown(f"""
    <div class="kpi-card">
      <div class="kpi-label">% pagado sobre devengado</div>
      <div class="kpi-value">{fmt_millones(pagado)}</div>
      <div class="kpi-sub">
        pagado acumulado &nbsp;/&nbsp; devengado {fmt_millones(dev_g)}
        &nbsp;·&nbsp; cierre {mes_g_lbl}
      </div>
      {badge(pct_pagado_dev, "pagado")}
      {barra_html(pct_pagado_dev)}
    </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown(f"""
    <div class="kpi-card acento">
      <div class="kpi-label">% ingreso ejecutado</div>
      <div class="kpi-value">{fmt_millones(percibido)}</div>
      <div class="kpi-sub">
        percibido acumulado &nbsp;/&nbsp; ppto. vigente {fmt_millones(ppto_i)}
        &nbsp;·&nbsp; cierre {mes_i_lbl}
      </div>
      {badge(pct_ejec_ingreso, "percibido")}
      {barra_html(pct_ejec_ingreso, naranja=True)}
    </div>
    """, unsafe_allow_html=True)

with col4:
    st.markdown(f"""
    <div class="kpi-card acento">
      <div class="kpi-label">% percibido sobre devengado</div>
      <div class="kpi-value">{fmt_millones(percibido)}</div>
      <div class="kpi-sub">
        percibido acumulado &nbsp;/&nbsp; devengado {fmt_millones(dev_i)}
        &nbsp;·&nbsp; cierre {mes_i_lbl}
      </div>
      {badge(pct_percib_dev, "percibido")}
      {barra_html(pct_percib_dev, naranja=True)}
    </div>
    """, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Barras por subtítulo — Gastos (devengado / ppto. vigente)
# ---------------------------------------------------------------------------

if not df_g_sel.empty:
    st.markdown(
        '<div class="section-title">'
        'Ejecución por subtítulo — Gastos &nbsp;(devengado / presupuesto vigente)'
        '</div>',
        unsafe_allow_html=True,
    )

    resumen_g = (
        df_g_sel.groupby("Subtítulo_Nombre")[
            ["PRESUPUESTO_VIGENTE", "DEVENGADO_ACUMULADO"]
        ]
        .sum()
        .reset_index()
    )
    # Conservar filas con presupuesto o con devengado (sobredevengado sin ppto.)
    resumen_g = resumen_g[
        (resumen_g["PRESUPUESTO_VIGENTE"] > 0) | (resumen_g["DEVENGADO_ACUMULADO"] > 0)
    ].copy()
    resumen_g["pct"] = resumen_g.apply(
        lambda r: r["DEVENGADO_ACUMULADO"] / r["PRESUPUESTO_VIGENTE"] * 100
        if r["PRESUPUESTO_VIGENTE"] > 0 else float("inf"),
        axis=1,
    )
    resumen_g = resumen_g.sort_values("DEVENGADO_ACUMULADO", ascending=False)

    mitad = len(resumen_g) // 2 + len(resumen_g) % 2
    col_a, col_b = st.columns(2)

    for col_st, chunk in zip([col_a, col_b], [resumen_g.iloc[:mitad], resumen_g.iloc[mitad:]]):
        with col_st:
            for _, row in chunk.iterrows():
                label = row["Subtítulo_Nombre"].title()
                if len(label) > 42:
                    label = label[:40] + "…"
                pct = row["pct"]
                pct_txt = f"{pct:.1f}%" if pct != float("inf") else "sin ppto."
                color_pct = "#FFFFFF" if pct > 100 else COLOR_PRINCIPAL
                st.markdown(f"""
                <div class="progress-row">
                  <div class="progress-label">
                    <span>{label}</span>
                    <span style="color:{color_pct};font-weight:700">{pct_txt}</span>
                  </div>
                  {barra_html(pct)}
                  <div style="font-size:0.73rem;color:#666;margin-top:2px;">
                    Dev. {fmt_millones(row['DEVENGADO_ACUMULADO'])}
                    &nbsp;/&nbsp;
                    Ppto. {fmt_millones(row['PRESUPUESTO_VIGENTE'])}
                  </div>
                </div>
                """, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Módulos de análisis
# ---------------------------------------------------------------------------

st.markdown('<div class="section-title">Módulos de análisis</div>', unsafe_allow_html=True)

nav1, nav2, nav3 = st.columns(3)

with nav1:
    st.markdown("""
    <div class="nav-card">
      <div class="nav-icon">🌳</div>
      <h4>Jerarquía presupuestaria</h4>
      <p>Explora la estructura completa del presupuesto con treemaps y gráficos
      de anillos interactivos, desde el título hasta la denominación de cuenta.</p>
    </div>
    """, unsafe_allow_html=True)
    st.page_link("pages/1_Jerarquia.py", label="Ir a Jerarquía →")

with nav2:
    st.markdown("""
    <div class="nav-card">
      <div class="nav-icon">📈</div>
      <h4>Evolución temporal</h4>
      <p>Compara la ejecución mes a mes entre distintos años presupuestarios.
      Identifica tendencias y patrones de comportamiento histórico.</p>
    </div>
    """, unsafe_allow_html=True)
    st.page_link("pages/2_Evolucion.py", label="Ir a Evolución →")

with nav3:
    st.markdown("""
    <div class="nav-card">
      <div class="nav-icon">🔍</div>
      <h4>Detalle y descarga</h4>
      <p>Consulta el detalle de cualquier cuenta presupuestaria y descarga los datos
      filtrados en CSV o Excel para tu propio análisis.</p>
    </div>
    """, unsafe_allow_html=True)
    st.page_link("pages/3_Detalle.py", label="Ir a Detalle →")

# ---------------------------------------------------------------------------
# Nota metodológica
# ---------------------------------------------------------------------------

st.markdown("""
<div class="nota-metodologica">
  <b>Nota metodológica</b> &nbsp;·&nbsp; Los montos se expresan en pesos chilenos (CLP). <br><br>
  <b>Devengado acumulado:</b> compromisos presupuestarios reconocidos desde el 1 de enero,
  independientemente de si han sido pagados.<br>
  <b>Pagado acumulado:</b> monto efectivamente transferido a proveedores o beneficiarios.<br>
  <b>Percibido acumulado:</b> monto efectivamente ingresado a las arcas municipales.<br>
  <b>Presupuesto vigente:</b> presupuesto inicial más modificaciones aprobadas.<br><br>
  Una línea de <b>gasto</b> está 100% ejecutada cuando el devengado acumulado iguala
  el presupuesto vigente; una línea de <b>ingreso</b> está 100% ejecutada cuando el
  percibido acumulado iguala el presupuesto vigente.<br>
  Valores superiores al 100% indican <b>sobredevengado o sobrepercibido</b>,
  situación que puede ocurrir cuando un movimiento se registra antes de completarse
  la modificación presupuestaria correspondiente.
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
