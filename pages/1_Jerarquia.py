"""
pages/1_Jerarquia.py — Jerarquía presupuestaria
================================================
Treemap o Sunburst interactivo con tres niveles: Subtítulo → Ítem → Asignación.
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

PALETA_COMP = [
    "#0250C0", "#63C5DA", "#FFC107", "#7240C2", "#A7349D",
    "#FF8500", "#65930D", "#BC092C", "#B7B7B7", "#A37129",
]

# ---------------------------------------------------------------------------
# Configuración de página
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Jerarquía Presupuestaria · Peñalolén",
    page_icon="🌳",
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
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
    5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
}


def fmt_millones(v: float) -> str:
    v = float(v)
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


def titulo_case(s: str, max_chars: int = 55) -> str:
    s = s.strip().title()
    return s if len(s) <= max_chars else s[:max_chars - 1] + "…"


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
    anio_sel = st.selectbox("Año presupuestario", anios, index=0)

    tipo_sel = st.radio("Tipo de balance", ["Gastos", "Ingresos"], horizontal=True)
    df_base  = df_gastos if tipo_sel == "Gastos" else df_ingresos
    df_anio  = df_base[df_base["anio"] == anio_sel]

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
# Header
# ---------------------------------------------------------------------------

st.markdown(f"""
<div class="header-strip">
  <h1>🌳 Jerarquía presupuestaria — {tipo_sel}</h1>
  <p>Municipalidad de Peñalolén &nbsp;·&nbsp; {mes_lbl} {anio_sel}
     &nbsp;·&nbsp; Niveles: Subtítulo → Ítem → Asignación</p>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Controles del gráfico
# ---------------------------------------------------------------------------

with st.container():
    st.markdown('<div class="control-bar">', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        tipo_grafico = st.radio(
            "Tipo de gráfico", ["Treemap", "Sunburst"], horizontal=True,
            help="Treemap: rectángulos anidados. Sunburst: círculos concéntricos.",
        )
    with c2:
        col_metrica_lbl = st.radio(
            "Tamaño de bloques según",
            ["Devengado acumulado", "Presupuesto vigente"],
            horizontal=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)

col_metrica = (
    "DEVENGADO_ACUMULADO" if col_metrica_lbl == "Devengado acumulado"
    else "PRESUPUESTO_VIGENTE"
)

# Columna y etiqueta de ejecución según tipo de balance
col_ejec_num = "DEVENGADO_ACUMULADO" if tipo_sel == "Gastos" else "PERCIBIDO_ACUMULADO"
col_ejec_lbl = "Devengado acumulado" if tipo_sel == "Gastos" else "Percibido acumulado"

# ---------------------------------------------------------------------------
# Preparación de datos
# ---------------------------------------------------------------------------

df_cierre = df_base[
    (df_base["anio"] == anio_sel) & (df_base["mes_cierre"] == mes_sel)
].copy()

cols_check = ["PRESUPUESTO_VIGENTE", "DEVENGADO_ACUMULADO"]
if col_ejec_num in df_cierre.columns:
    cols_check.append(col_ejec_num)
df_cierre = df_cierre[df_cierre[cols_check].sum(axis=1) > 0].copy()

if df_cierre.empty:
    st.warning(f"No hay datos disponibles para {tipo_sel} — {mes_lbl} {anio_sel}.")
    st.stop()

# ---------------------------------------------------------------------------
# Agregación por Subtítulo → Ítem → Asignación
# Necesaria porque distintas Denominaciones comparten la misma Asignación.
# ---------------------------------------------------------------------------

agg_cols_base = {"PRESUPUESTO_VIGENTE": "sum", "DEVENGADO_ACUMULADO": "sum"}
if col_ejec_num != "DEVENGADO_ACUMULADO" and col_ejec_num in df_cierre.columns:
    agg_cols_base[col_ejec_num] = "sum"

df_agg = (
    df_cierre
    .groupby(["Subtítulo_Nombre", "Ítem_Nombre", "Asignación_Nombre"])
    .agg(agg_cols_base)
    .reset_index()
)

# Asegurar columna de ejecución presente
if col_ejec_num not in df_agg.columns:
    df_agg[col_ejec_num] = df_agg["DEVENGADO_ACUMULADO"]

df_agg["pct_ejec"] = df_agg.apply(
    lambda r: (
        r[col_ejec_num] / r["PRESUPUESTO_VIGENTE"] * 100
        if r["PRESUPUESTO_VIGENTE"] > 0
        else (float("inf") if r[col_ejec_num] > 0 else 0.0)
    ),
    axis=1,
)

# ---------------------------------------------------------------------------
# Construcción de nodos para Plotly
# ---------------------------------------------------------------------------

subtitulos_unicos = df_agg["Subtítulo_Nombre"].unique()
color_map = {
    sub: PALETA_COMP[i % len(PALETA_COMP)]
    for i, sub in enumerate(subtitulos_unicos)
}

ids, labels, parents, values, colors, customdata = [], [], [], [], [], []

ids.append("raiz")
labels.append(f"{tipo_sel} {anio_sel}")
parents.append("")
values.append(0)
colors.append(COLOR_OSCURO)
customdata.append(("", 0, 0, 0))

sub_totales: dict = {}
for sub in subtitulos_unicos:
    mask     = df_agg["Subtítulo_Nombre"] == sub
    ppto_sub = df_agg.loc[mask, "PRESUPUESTO_VIGENTE"].sum()
    ejec_sub = df_agg.loc[mask, col_ejec_num].sum()
    dev_sub  = df_agg.loc[mask, "DEVENGADO_ACUMULADO"].sum()
    val_sub  = df_agg.loc[mask, col_metrica].sum()
    pct_sub  = ejec_sub / ppto_sub * 100 if ppto_sub > 0 else 0.0

    sub_id = f"sub::{sub}"
    ids.append(sub_id)
    labels.append(titulo_case(sub, 40))
    parents.append("raiz")
    values.append(val_sub)
    colors.append(color_map[sub])
    customdata.append((sub, dev_sub, ppto_sub, pct_sub))
    sub_totales[sub] = sub_id

item_totales: dict = {}
for (sub, item), grp in df_agg.groupby(["Subtítulo_Nombre", "Ítem_Nombre"]):
    ppto_i = grp["PRESUPUESTO_VIGENTE"].sum()
    ejec_i = grp[col_ejec_num].sum()
    dev_i  = grp["DEVENGADO_ACUMULADO"].sum()
    val_i  = grp[col_metrica].sum()
    pct_i  = ejec_i / ppto_i * 100 if ppto_i > 0 else 0.0

    item_id = f"item::{sub}::{item}"
    ids.append(item_id)
    labels.append(titulo_case(item, 45))
    parents.append(sub_totales[sub])
    values.append(val_i)
    colors.append(color_map[sub])
    customdata.append((item, dev_i, ppto_i, pct_i))
    item_totales[(sub, item)] = item_id

for _, row in df_agg.iterrows():
    sub  = row["Subtítulo_Nombre"]
    item = row["Ítem_Nombre"]
    asig = row["Asignación_Nombre"]

    asig_id = f"asig::{sub}::{item}::{asig}"
    ids.append(asig_id)
    labels.append(titulo_case(asig, 50))
    parents.append(item_totales[(sub, item)])
    values.append(row[col_metrica])
    colors.append(color_map[sub] + "BB")
    pct_display = row["pct_ejec"] if row["pct_ejec"] != float("inf") else 999.0
    customdata.append((asig, row["DEVENGADO_ACUMULADO"], row["PRESUPUESTO_VIGENTE"], pct_display))

hovertemplate = (
    "<b>%{label}</b><br>"
    f"<b>{col_ejec_lbl}:</b> %{{customdata[1]:$,.0f}}<br>"
    "<b>Presupuesto vigente:</b> %{customdata[2]:$,.0f}<br>"
    "<b>% ejecución:</b> %{customdata[3]:.1f}%"
    "<extra></extra>"
)

# ---------------------------------------------------------------------------
# Figura Plotly
# ---------------------------------------------------------------------------

if tipo_grafico == "Treemap":
    fig = go.Figure(go.Treemap(
        ids=ids, labels=labels, parents=parents, values=values,
        marker=dict(colors=colors, line=dict(width=1.2, color="#FFFFFF")),
        customdata=customdata, hovertemplate=hovertemplate,
        texttemplate="<b>%{label}</b>", textposition="middle center",
        maxdepth=3, branchvalues="total",
        pathbar=dict(visible=True, side="top", thickness=26,
                     textfont=dict(size=12, color=COLOR_BLANCO)),
    ))
else:
    fig = go.Figure(go.Sunburst(
        ids=ids, labels=labels, parents=parents, values=values,
        marker=dict(colors=colors, line=dict(width=1, color="#FFFFFF")),
        customdata=customdata, hovertemplate=hovertemplate,
        texttemplate="<b>%{label}</b>", maxdepth=3, branchvalues="total",
        insidetextorientation="radial", leaf=dict(opacity=0.85),
    ))

fig.update_layout(
    margin=dict(t=10, l=0, r=0, b=10), height=680,
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="sans-serif", size=12, color=COLOR_TEXTO),
    hoverlabel=dict(bgcolor=COLOR_OSCURO, font_color=COLOR_BLANCO,
                    font_size=13, bordercolor=COLOR_PRINCIPAL),
)

# ---------------------------------------------------------------------------
# KPIs de contexto
# ---------------------------------------------------------------------------

ppto_total = df_agg["PRESUPUESTO_VIGENTE"].sum()
ejec_total = df_agg[col_ejec_num].sum()
pct_total  = ejec_total / ppto_total * 100 if ppto_total > 0 else 0.0
kpi_clase  = "" if tipo_sel == "Gastos" else "acento"

st.markdown('<div class="seccion">Resumen del cierre seleccionado</div>', unsafe_allow_html=True)
k1, k2, k3 = st.columns(3)

with k1:
    st.markdown(f"""
    <div class="kpi-mini {kpi_clase}">
      <div class="kpi-mini-label">Presupuesto vigente</div>
      <div class="kpi-mini-value">{fmt_millones(ppto_total)}</div>
      <div class="kpi-mini-sub">{mes_lbl} {anio_sel}</div>
    </div>
    """, unsafe_allow_html=True)

with k2:
    st.markdown(f"""
    <div class="kpi-mini {kpi_clase}">
      <div class="kpi-mini-label">{col_ejec_lbl}</div>
      <div class="kpi-mini-value">{fmt_millones(ejec_total)}</div>
      <div class="kpi-mini-sub">sobre presupuesto vigente</div>
      {badge_html(pct_total, "ejecutado")}
    </div>
    """, unsafe_allow_html=True)

with k3:
    n_con_ejec = int((df_agg[col_ejec_num] > 0).sum())
    n_total    = len(df_agg)
    st.markdown(f"""
    <div class="kpi-mini {kpi_clase}">
      <div class="kpi-mini-label">Asignaciones con ejecución</div>
      <div class="kpi-mini-value">{n_con_ejec} / {n_total}</div>
      <div class="kpi-mini-sub">con al menos $1 registrado</div>
    </div>
    """, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Gráfico principal
# ---------------------------------------------------------------------------

st.markdown(
    f'<div class="seccion">'
    f'{tipo_grafico} — tamaño por {col_metrica_lbl.lower()}'
    f'</div>',
    unsafe_allow_html=True,
)
st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# Tabla resumen por subtítulo
# ---------------------------------------------------------------------------

st.markdown('<div class="seccion">Tabla resumen por subtítulo</div>', unsafe_allow_html=True)

# Agregar siempre con nombres internos fijos para evitar colisiones
resumen_sub = (
    df_agg
    .groupby("Subtítulo_Nombre")
    .agg(
        _ppto=("PRESUPUESTO_VIGENTE", "sum"),
        _dev=("DEVENGADO_ACUMULADO", "sum"),
        _ejec=(col_ejec_num, "sum"),
    )
    .reset_index()
)

resumen_sub["_pct"] = resumen_sub.apply(
    lambda r: r["_ejec"] / r["_ppto"] * 100 if r["_ppto"] > 0 else 0.0,
    axis=1,
)
resumen_sub = resumen_sub.sort_values("_dev", ascending=False)

# Construir tabla de display con nombres legibles
df_tabla = pd.DataFrame({
    "Subtítulo":        resumen_sub["Subtítulo_Nombre"].values,
    "Ppto. vigente":    resumen_sub["_ppto"].apply(fmt_millones).values,
    "Devengado acum.":  resumen_sub["_dev"].apply(fmt_millones).values,
    col_ejec_lbl:       resumen_sub["_ejec"].apply(fmt_millones).values,
    "% ejecución":      resumen_sub["_pct"].apply(lambda x: f"{x:.1f}%").values,
})

# Si gastos, col_ejec_lbl == "Devengado acumulado" == "Devengado acum." → eliminar duplicado
if col_ejec_lbl == "Devengado acumulado":
    df_tabla = df_tabla.drop(columns=[col_ejec_lbl])

st.dataframe(
    df_tabla,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Subtítulo":   st.column_config.TextColumn(width="large"),
        "% ejecución": st.column_config.TextColumn(width="small"),
    },
)

# ---------------------------------------------------------------------------
# Nota metodológica
# ---------------------------------------------------------------------------

nota_ejec = (
    "Una asignación de <b>gasto</b> está 100% ejecutada cuando el devengado acumulado "
    "iguala su presupuesto vigente."
    if tipo_sel == "Gastos"
    else
    "Una asignación de <b>ingreso</b> está 100% ejecutada cuando el percibido acumulado "
    "iguala su presupuesto vigente."
)

st.markdown(f"""
<div class="nota">
  <b>Nota metodológica</b> &nbsp;·&nbsp;
  El gráfico agrega los datos hasta el nivel de <b>Asignación</b>.
  Dentro de cada asignación pueden existir varias denominaciones de cuenta;
  sus montos se suman antes de graficar.
  El tamaño de cada bloque refleja el <b>{col_metrica_lbl.lower()}</b> de esa asignación.
  {nota_ejec}
  Valores superiores al 100% indican <b>sobredevengado o sobrepercibido</b>,
  situación posible cuando un movimiento se registra antes de completarse
  la modificación presupuestaria correspondiente.
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
