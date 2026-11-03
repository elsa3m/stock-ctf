"""
Diseño del panel: tema claro (por defecto) y oscuro, con interruptor.

Decisiones y por qué:

* **Claro por defecto.** Se lee mejor a cualquier edad, en cualquier pantalla y
  en proyector. Quien prefiera oscuro lo cambia con un botón.
* **Tipografía grande.** El cuerpo parte en 16 px y nada baja de 13 px. En el
  panel anterior había textos de 11 px que costaban leer.
* **Colores validados para daltonismo.** La paleta de los productos pasa las seis
  comprobaciones (separación en visión protán/deután/tritán, contraste sobre la
  superficie, banda de luminosidad) en los dos modos.
* **El color nunca es la única señal.** Los semáforos verde/amarillo/rojo se
  confunden en daltonismo rojo-verde: por eso cada uno lleva SIEMPRE una forma
  (▲ ■ ▼) y el número al lado. El color acompaña, no informa solo.
"""
from __future__ import annotations

import streamlit as st

# --- paleta categórica validada (productos) --------------------------------
SERIES_CLARO = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7"]
SERIES_OSCURO = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9"]
# Tres colores más para equipos, seguros y accesorios: distintos de los siete
# de producto, para que se note que son otra familia sin volverlos grises.
DINERO_CLARO = ["#00868b", "#8a5a2b", "#b23a8f"]
DINERO_OSCURO = ["#22a8ad", "#b3763a", "#d060ad"]

# --- estado (nunca solo color: siempre con forma y número) ------------------
ESTADO = {
    "bien":  {"claro": "#0ca30c", "oscuro": "#0ca30c", "forma": "▲", "texto": "sobre la meta"},
    "medio": {"claro": "#b06f00", "oscuro": "#fab219", "forma": "■", "texto": "en riesgo"},
    "mal":   {"claro": "#d03b3b", "oscuro": "#e66767", "forma": "▼", "texto": "bajo la meta"},
    "nulo":  {"claro": "#6b7280", "oscuro": "#8b93a1", "forma": "·", "texto": "sin dato"},
}

TEMAS = {
    "claro": {
        "fondo": "#f2f5f9", "tarjeta": "#ffffff", "tarjeta2": "#f7f9fc",
        "borde": "#dde3ec", "borde_fuerte": "#c3ccd9",
        "texto": "#111827", "texto2": "#4b5563", "texto3": "#6b7280",
        "marca": "#5b2d8e", "marca2": "#0e7490",
        "sombra": "0 1px 2px rgba(16,24,40,.06), 0 8px 24px rgba(16,24,40,.06)",
        "series": SERIES_CLARO, "dinero": DINERO_CLARO, "clave_estado": "claro",
        "chip_bien": "#e7f6e7", "chip_medio": "#fdf3d9", "chip_mal": "#fbe9e9",
    },
    "oscuro": {
        "fondo": "#0e1218", "tarjeta": "#171c26", "tarjeta2": "#1d2431",
        "borde": "#2a3342", "borde_fuerte": "#3b4658",
        "texto": "#f3f5f8", "texto2": "#c3c9d4", "texto3": "#98a1af",
        "marca": "#c4b5fd", "marca2": "#67e8f9",
        "sombra": "0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.35)",
        "series": SERIES_OSCURO, "dinero": DINERO_OSCURO, "clave_estado": "oscuro",
        "chip_bien": "#12301a", "chip_medio": "#33280a", "chip_mal": "#3a1618",
    },
}


# Con qué contraste abre el panel. El botón de arriba a la derecha lo cambia.
TEMA_POR_DEFECTO = "claro"


def actual() -> dict:
    """Tema vigente en esta sesión."""
    return TEMAS[st.session_state.get("tema", TEMA_POR_DEFECTO)]


def color_estado(nombre: str) -> str:
    t = actual()
    return ESTADO[nombre][t["clave_estado"]]


def estado_de(valor, referencia) -> str:
    """
    Clasifica un cumplimiento contra su referencia (la meta, o el avance del mes).

        >= 100 % de la referencia  -> bien
        >=  80 %                   -> medio
        <   80 %                   -> mal
    """
    if valor is None or referencia in (None, 0):
        return "nulo"
    r = valor / referencia
    if r >= 1.0:
        return "bien"
    if r >= 0.8:
        return "medio"
    return "mal"


def css() -> str:
    t = actual()
    s = t["series"]
    return f"""
<style>
:root {{ color-scheme: {"light" if t is TEMAS["claro"] else "dark"}; }}

html, body, .stApp, [data-testid="stAppViewContainer"] {{
  background: {t['fondo']};
  color: {t['texto']};
  font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
  font-size: 16px;
}}
[data-testid="stHeader"] {{ background: transparent; }}
.block-container, [data-testid="stMainBlockContainer"] {{
  max-width: 1500px !important; padding: .8rem 1.4rem 3rem !important;
}}

/* ---------- encabezado ---------- */
.cabecera {{
  display:flex; align-items:center; gap:1rem; flex-wrap:wrap;
  padding:.5rem 0 .9rem;
}}
.cabecera .marca {{
  background:#fff; border-radius:12px; padding:.45rem .7rem; line-height:0;
  box-shadow:{t['sombra']}; border:1px solid {t['borde']};
}}
.cabecera .marca img {{ height:38px; width:auto; }}
.cabecera h1 {{
  font-size:clamp(1.25rem,2.4vw,1.85rem); font-weight:800; margin:0;
  letter-spacing:-.01em; color:{t['texto']};
}}
.cabecera .sub {{ font-size:.95rem; color:{t['texto2']}; margin-top:.1rem; }}

/* ---------- tarjetas ---------- */
.tarjeta {{
  background:{t['tarjeta']}; border:1px solid {t['borde']}; border-radius:16px;
  padding:1rem 1.1rem; box-shadow:{t['sombra']}; margin-bottom:.75rem;
}}
.tarjeta.plana {{ box-shadow:none; background:{t['tarjeta2']}; }}
.tarjeta h2, .seccion {{
  font-size:1.05rem; font-weight:750; color:{t['texto']}; margin:0 0 .15rem;
  letter-spacing:-.01em;
}}
.seccion-sub {{ font-size:.9rem; color:{t['texto2']}; margin-bottom:.6rem; }}

/* ---------- números grandes ---------- */
.metrica .rotulo {{
  font-size:.9rem; font-weight:650; color:{t['texto2']};
  text-transform:none; letter-spacing:0; display:flex; gap:.35rem; align-items:center;
}}
.metrica .valor {{
  font-size:clamp(1.7rem,3vw,2.3rem); font-weight:800; line-height:1.1;
  margin:.25rem 0 .1rem; color:{t['texto']}; font-variant-numeric:tabular-nums;
}}
.metrica .pie {{ font-size:.88rem; color:{t['texto2']}; line-height:1.45; }}

/* ---------- chip de estado (color + forma + texto) ---------- */
.chip {{
  display:inline-flex; align-items:center; gap:.3rem; border-radius:999px;
  padding:.12rem .55rem; font-size:.82rem; font-weight:700; white-space:nowrap;
  border:1px solid transparent;
}}
.chip .f {{ font-size:.8em; }}
.chip.bien  {{ background:{t['chip_bien']};  color:{ESTADO['bien'][t['clave_estado']]};  border-color:{ESTADO['bien'][t['clave_estado']]}55; }}
.chip.medio {{ background:{t['chip_medio']}; color:{ESTADO['medio'][t['clave_estado']]}; border-color:{ESTADO['medio'][t['clave_estado']]}55; }}
.chip.mal   {{ background:{t['chip_mal']};   color:{ESTADO['mal'][t['clave_estado']]};   border-color:{ESTADO['mal'][t['clave_estado']]}55; }}
.chip.nulo  {{ background:transparent;       color:{t['texto3']};                        border-color:{t['borde']}; }}

.t-bien  {{ color:{ESTADO['bien'][t['clave_estado']]}  !important; }}
.t-medio {{ color:{ESTADO['medio'][t['clave_estado']]} !important; }}
.t-mal   {{ color:{ESTADO['mal'][t['clave_estado']]}   !important; }}
.t-suave {{ color:{t['texto2']} !important; }}
.t-tenue {{ color:{t['texto3']} !important; }}

/* ---------- barra de progreso con marca de corte ---------- */
.barra {{
  position:relative; height:12px; border-radius:6px; overflow:visible;
  background:{t['borde']}; margin:.45rem 0 .3rem;
}}
.barra > .relleno {{ height:100%; border-radius:6px; }}
.barra > .corte {{
  position:absolute; top:-4px; width:3px; height:20px; border-radius:2px;
  background:{t['texto']}; opacity:.75;
}}

/* ---------- producto ---------- */
.producto {{
  background:{t['tarjeta']}; border:1px solid {t['borde']}; border-radius:14px;
  padding:.8rem .9rem; height:100%;
}}
.producto .titulo {{ font-size:.92rem; font-weight:750; color:{t['texto']}; display:flex; gap:.4rem; align-items:center; }}
.producto .punto {{ width:10px; height:10px; border-radius:3px; flex:none; }}
.producto .cifra {{ font-size:1.5rem; font-weight:800; color:{t['texto']}; font-variant-numeric:tabular-nums; }}
.producto .de {{ font-size:1rem; font-weight:650; color:{t['texto2']}; }}
.producto .detalle {{ font-size:.86rem; color:{t['texto2']}; line-height:1.6; }}

/* Los siete productos en una sola fila: las cajitas se aprietan un poco y la
   cifra baja de tamaño, pero mantienen los mismos datos. */
.grid.productos .producto {{ padding:.7rem .7rem; }}
.grid.productos .producto .titulo {{ font-size:.85rem; }}
.grid.productos .producto .cifra {{ font-size:1.25rem; }}
.grid.productos .producto .de {{ font-size:.9rem; }}
.grid.productos .producto .detalle {{ font-size:.78rem; line-height:1.55; }}
/* con diez cajitas en la fila las cifras en pesos necesitan un punto menos */
.grid.g10 .producto .cifra {{ font-size:1.05rem; }}
.grid.g10 .producto .de {{ font-size:.8rem; }}
.grid.g10 .producto .titulo {{ font-size:.8rem; }}
/* con diez columnas iguales, una línea larga se parte en vez de ensanchar su
   cajita: así la fila queda pareja */
.grid.g10 .producto .detalle > div {{ white-space:normal; }}
/* cada dato en UNA línea: si no cabe, se achica la letra, no se parte el dato */
.grid.g10 .producto .detalle {{ font-size:.73rem; }}
.grid.productos .producto .detalle > div {{ white-space:nowrap; }}

/* ---------- grillas ---------- */
.grid {{ display:grid; gap:.7rem; }}
.g2 {{ grid-template-columns:repeat(2,1fr); }}
.g3 {{ grid-template-columns:repeat(3,1fr); }}
.g4 {{ grid-template-columns:repeat(4,1fr); }}
.g5 {{ grid-template-columns:repeat(5,1fr); }}
.g6 {{ grid-template-columns:repeat(6,1fr); }}
.g7 {{ grid-template-columns:repeat(7,1fr); }}
.g10 {{ grid-template-columns:repeat(10,minmax(0,1fr)); }}

/* ---------- tabla ---------- */
.tabla-caja {{ overflow-x:auto; border-radius:12px; border:1px solid {t['borde']}; }}
table.tabla {{ width:100%; border-collapse:separate; border-spacing:0; font-size:1rem; background:{t['tarjeta']}; }}
table.tabla th {{
  position:sticky; top:0; z-index:2; background:{t['tarjeta2']}; text-align:right;
  font-size:.92rem; font-weight:700; color:{t['texto2']}; padding:.55rem .6rem;
  border-bottom:1px solid {t['borde_fuerte']}; white-space:nowrap;
}}
table.tabla td {{
  text-align:right; padding:.5rem .6rem; border-bottom:1px solid {t['borde']};
  color:{t['texto']}; font-variant-numeric:tabular-nums; white-space:nowrap;
}}
table.tabla th.izq, table.tabla td.izq {{ text-align:left; }}
table.tabla th.fija, table.tabla td.fija {{ position:sticky; left:0; background:{t['tarjeta']}; z-index:1; }}
table.tabla th.fija {{ background:{t['tarjeta2']}; z-index:3; }}
table.tabla tbody tr:hover td {{ background:{t['tarjeta2']}; }}
table.tabla tr.total td {{ background:{t['tarjeta2']}; font-weight:750; }}
/* subtotales de la ficha en papel (Total Captura / Calidad / Foco) */
table.tabla tr.grupo td {{
  background:{t['tarjeta2']}; font-weight:700; border-top:1.5px solid {t['borde_fuerte']};
}}
table.tabla tr.grupo td.fija {{ background:{t['tarjeta2']}; }}

/* Las tarjetas de una misma fila quedan todas de la misma altura, aunque una
   traiga dos líneas de nota y otra ninguna. Si no, la fila se ve despareja.
   Streamlit envuelve cada tarjeta en varios contenedores: hay que dejar pasar
   el alto por todos ellos hasta la tarjeta. */
[data-testid="stHorizontalBlock"] {{ align-items:stretch; }}
[data-testid="stColumn"] > div,
[data-testid="stColumn"] [data-testid="stVerticalBlock"] {{ height:100%; }}
[data-testid="stColumn"] [data-testid="stElementContainer"]:has(.tarjeta),
[data-testid="stColumn"] [data-testid="stMarkdown"]:has(.tarjeta),
[data-testid="stColumn"] [data-testid="stMarkdown"]:has(.tarjeta) > div,
[data-testid="stColumn"] [data-testid="stMarkdown"]:has(.tarjeta) [data-testid="stMarkdownContainer"] {{
  height:100%; width:100%;
}}
[data-testid="stColumn"] [data-testid="stMarkdown"]:has(.tarjeta) > div {{ align-items:stretch !important; }}
[data-testid="stColumn"] .tarjeta {{ height:100%; }}

/* ---------- tarjeta de identidad de la persona ---------- */
.nombre-persona {{ font-size:1.5rem; font-weight:800; color:{t['texto']}; line-height:1.2;
                   letter-spacing:-.01em; margin-bottom:.15rem; }}
.dato {{ display:flex; align-items:baseline; gap:.5rem; padding:.28rem 0; }}
.dato + .dato {{ border-top:1px solid {t['borde']}; }}
.dato .rot {{ color:{t['texto3']}; font-size:.82rem; min-width:6.5rem; }}
.dato .val {{ color:{t['texto']}; font-weight:700; font-size:.95rem; }}
.dato .val.suave {{ font-weight:600; color:{t['texto2']}; }}

/* ---------- mapa de calor ----------
   Una celda por indicador, apretada y con el fondo teñido según el estado.
   Así entran los quince KPI en una pantalla y el patrón se ve de una mirada:
   una fila casi toda roja o una columna casi toda ámbar saltan solas. */
table.tabla.mapa {{ font-size:.82rem; }}
table.tabla.mapa th, table.tabla.mapa td {{ padding:.32rem .4rem; }}
/* En el mapa los valores van centrados, así que los títulos también: si el
   título queda a la derecha y el número al centro, la columna se ve chueca. */
table.tabla.mapa th {{ text-align:center; }}
table.tabla.mapa th.izq, table.tabla.mapa th.fija {{ text-align:left; }}
table.tabla.mapa th {{ font-size:.76rem; line-height:1.25; }}
table.tabla.mapa td.hm {{ text-align:center; font-weight:700; font-variant-numeric:tabular-nums;
                          border-radius:6px; }}
table.tabla.mapa td.hm.bien {{ background:{t['chip_bien']}; color:{ESTADO['bien'][t['clave_estado']]}; }}
table.tabla.mapa td.hm.medio {{ background:{t['chip_medio']}; color:{ESTADO['medio'][t['clave_estado']]}; }}
table.tabla.mapa td.hm.mal {{ background:{t['chip_mal']}; color:{ESTADO['mal'][t['clave_estado']]}; }}
table.tabla.mapa td.hm.nulo {{ color:{t['texto3']}; }}
table.tabla.mapa tbody tr:hover td.hm {{ filter:brightness(1.12); }}
/* cabecera de la ficha, como la del papel */
.ficha-cab {{
  display:flex; flex-wrap:wrap; gap:.4rem 1.4rem; align-items:baseline;
  background:{t['tarjeta2']}; border:1px solid {t['borde']}; border-left:5px solid {t['marca']};
  border-radius:12px; padding:.6rem .9rem; margin:.2rem 0 .6rem;
}}
.ficha-cab .nom {{ font-size:1.05rem; font-weight:800; letter-spacing:-.01em; }}
.ficha-cab .dato {{ font-size:.86rem; }}
.ficha-cab .dato b {{ font-weight:750; }}

/* ---------- desplegables ---------- */
/* Streamlit pinta la cabecera del desplegable con su propio color claro; en
   modo oscuro el texto quedaba casi invisible. Aquí se fuerza a los colores
   del tema, y el cuerpo queda visiblemente DENTRO de la misma caja. */
details[data-testid="stExpander"], [data-testid="stExpander"] {{
  background:{t['tarjeta']} !important;
  border:1px solid {t['borde']} !important; border-radius:14px !important;
  box-shadow:{t['sombra']}; margin-bottom:.75rem; overflow:hidden;
}}
[data-testid="stExpander"] summary, [data-testid="stExpander"] > div:first-child {{
  background:{t['tarjeta2']} !important; border-radius:0 !important;
}}
[data-testid="stExpander"] summary {{
  padding:.7rem 1rem !important; border-bottom:1px solid {t['borde']};
}}
[data-testid="stExpander"] summary:hover {{ background:{t['borde']} !important; }}
[data-testid="stExpander"] summary p,
[data-testid="stExpander"] summary span,
[data-testid="stExpander"] summary div,
[data-testid="stExpander"] summary svg {{
  color:{t['texto']} !important; fill:{t['texto']} !important;
  font-weight:700; font-size:.98rem;
}}
[data-testid="stExpanderDetails"] {{ padding:.9rem 1rem 1rem !important; }}

/* ---------- controles de Streamlit ---------- */
div[data-baseweb="select"] > div {{
  background:{t['tarjeta']} !important; color:{t['texto']} !important;
  border:1.5px solid {t['borde_fuerte']} !important; border-radius:10px; font-size:.95rem; font-weight:600;
}}
div[data-baseweb="select"] * {{ color:{t['texto']} !important; }}
div[data-baseweb="popover"] li {{ background:{t['tarjeta']}; color:{t['texto']}; }}
label[data-testid="stWidgetLabel"] p {{ color:{t['texto2']}; font-weight:650; font-size:.9rem; }}
details {{ background:{t['tarjeta']}; border:1px solid {t['borde']}; border-radius:14px; }}
summary p {{ color:{t['texto']} !important; font-weight:700; font-size:.98rem; }}
[data-testid="stAlert"] {{ background:{t['tarjeta2']}; border:1px solid {t['borde']}; color:{t['texto']}; border-radius:12px; }}
.stButton > button, .stDownloadButton > button,
[data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-primary"] {{
  background:{t['tarjeta']} !important; color:{t['texto']} !important;
  border:1.5px solid {t['borde_fuerte']} !important;
  border-radius:10px; font-weight:700; font-size:.92rem; padding:.45rem .9rem; width:100%;
}}
/* el texto del botón vive dentro de un <p>: sin esto queda del color de Streamlit */
.stButton > button p, .stDownloadButton > button p,
[data-testid="stBaseButton-secondary"] p, [data-testid="stBaseButton-primary"] p {{
  color:{t['texto']} !important; font-weight:700;
}}
.stButton > button:hover, .stDownloadButton > button:hover {{ border-color:{t['marca2']}; color:{t['texto']}; }}
div[role="radiogroup"] {{ gap:.4rem; flex-wrap:wrap; }}
div[role="radiogroup"] > label {{
  background:{t['tarjeta']}; border:1.5px solid {t['borde']}; border-radius:999px;
  padding:.4rem .9rem; font-weight:700; font-size:.92rem;
}}
div[role="radiogroup"] > label:has(input:checked) {{
  background:{t['marca']}; border-color:{t['marca']}; color:#fff;
}}
div[role="radiogroup"] > label:has(input:checked) p {{ color:#fff !important; }}
div[role="radiogroup"] p {{ color:{t['texto']}; }}

/* etiquetas de los filtros multiselección */
span[data-baseweb="tag"] {{
  background:{t['marca']} !important; color:#fff !important; border-radius:8px !important;
  font-weight:650; font-size:.85rem;
}}
span[data-baseweb="tag"] span, span[data-baseweb="tag"] svg {{ color:#fff !important; fill:#fff !important; }}
[data-testid="stCheckbox"] p {{ color:{t['texto']}; font-weight:600; }}

.pie-pagina {{ text-align:center; color:{t['texto3']}; font-size:.85rem; margin-top:1.5rem; }}

/* ---------- responsive ---------- */
@media (max-width: 1450px) {{
  /* pantalla de notebook: las cajitas pasan a cinco por fila */
  .grid.productos {{ grid-template-columns:repeat(5,1fr); }}
}}
@media (max-width: 1100px) {{
  .g5, .g6, .g7, .g10, .grid.productos {{ grid-template-columns:repeat(3,1fr); }}
  [data-testid="stHorizontalBlock"] {{ flex-wrap:wrap !important; }}
  [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{ flex:1 1 46% !important; min-width:46% !important; }}
}}
@media (max-width: 640px) {{
  html, body, .stApp {{ font-size:15px; }}
  .block-container, [data-testid="stMainBlockContainer"] {{ padding:.6rem .7rem 2rem !important; }}
  [data-testid="stHorizontalBlock"] {{ gap:.5rem !important; }}
  [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{ flex:1 1 46% !important; min-width:46% !important; width:46% !important; }}
  [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:has(.ancho-total) {{ flex:1 1 100% !important; min-width:100% !important; width:100% !important; }}
  .g3, .g4, .g5, .g6, .g7, .g10, .grid.productos {{ grid-template-columns:repeat(2,1fr); }}
  /* las vistas se acomodan en dos o tres por fila, no una debajo de otra */
  div[role="radiogroup"] {{ gap:.3rem; flex-direction:row !important; flex-wrap:wrap !important; }}
  div[role="radiogroup"] > label {{ flex:0 1 auto; padding:.35rem .6rem; font-size:.85rem; }}
  .tarjeta {{ padding:.8rem .85rem; border-radius:14px; }}
  .metrica .valor {{ font-size:1.6rem; }}
  table.tabla th, table.tabla td {{ font-size:.92rem; padding:.4rem .45rem; }}
}}
</style>
"""


def inyectar():
    st.markdown(css(), unsafe_allow_html=True)


def interruptor():
    """Botón claro / oscuro. Devuelve el tema elegido."""
    if "tema" not in st.session_state:
        st.session_state["tema"] = TEMA_POR_DEFECTO
    actual_ = st.session_state["tema"]
    etiqueta = "🌙 Modo oscuro" if actual_ == "claro" else "☀️ Modo claro"
    if st.button(etiqueta, key="btn_tema", help="Cambia entre fondo claro y oscuro"):
        st.session_state["tema"] = "oscuro" if actual_ == "claro" else "claro"
        st.rerun()
    return st.session_state["tema"]
