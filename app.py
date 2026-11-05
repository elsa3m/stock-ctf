"""
STOCK CTF · app aparte (salió de la pestaña 📦 Stock del Panel CTF, v516).

Stock de cada tienda (Reporte Stock Disponible de SAP) menos lo vendido hoy en
Bsale, y la rotación de cada producto con el historial de salidas (venta en
tienda, retiro en tienda y delivery).

De dónde salen los datos (Google Drive, la misma cuenta de servicio del panel):
  · carpeta «1-panel CTF datos»: reportes de stock, Detalle de ventas de Bsale,
    la DOTACIÓN (para saber la tienda de cada vendedor de Bsale) y las bases
    EQUIPOS / ACCESORIOS del mes;
  · respaldo_panel.zip (solo lectura): lo que el panel ya tenía (stock, historial,
    Bsale del día y las bases subidas desde el panel);
  · respaldo_stock.zip: el respaldo PROPIO de esta app (lo que se sube acá).

Secrets (Streamlit → Settings → Secrets):
  gcp_json  = '''{ …la cuenta de servicio, igual que en el panel… }'''
  clave_ctf = "…"                       # se pide una vez y no se cierra sola
  drive_carpeta = "1-panel CTF datos"   # opcional
"""
from __future__ import annotations

import contextlib as _contextlib
import datetime as dt
import gc as _gc
import io
import json
import re
import threading as _threading
import time
import unicodedata
import zipfile as _zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from core import tema, ui
from core.ui import h, md, num

VERSION = "03/11/2026 · 3"
BASE = Path(__file__).resolve().parent
DATA_RAIZ = BASE / "data"
DATA_RAIZ.mkdir(exist_ok=True)

st.set_page_config(page_title="Stock CTF", page_icon="📦", layout="wide")
tema.iniciar()                       # oscuro por defecto; el botón lo deja claro
tema.inyectar()


class fuentes:                                   # lo único que se usa de core/fuentes.py
    @staticmethod
    def norm(s) -> str:
        """Texto comparable: sin tildes, mayúsculas, sin espacios de más."""
        s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
        return " ".join(s.upper().split())


# las seis tiendas, en el orden de siempre
TIENDAS = pd.DataFrame({
    "pdv": ["5003", "5541", "5245", "5543", "5542", "5544"],
    "tienda": ["Gilberto Fuenzalida", "Open Rancagua", "Arauco Maipú", "Parque Arauco",
               "Arauco Quilicura", "Peñalolén"],
})
NOMBRE_TIENDA = dict(zip(TIENDAS["pdv"], TIENDAS["tienda"]))
MESES_NOMBRE = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto",
                "Septiembre", "Octubre", "Noviembre", "Diciembre"]
ZONA_CHILE = "America/Santiago"
BSALE_DATOS = DATA_RAIZ / "bsale_dia.csv"
BSALE_INFO = DATA_RAIZ / "bsale_dia.json"
VENDEDORES = DATA_RAIZ / "vendedores.csv"       # código, nombre y tienda (sin RUT ni contacto)
BASES_DIR = DATA_RAIZ / "bases"                  # EQUIPOS y ACCESORIOS del mes
BASES_DIR.mkdir(exist_ok=True)
BASES_INFO = BASES_DIR / "bases.json"
STOCK_DIR = DATA_RAIZ / "stock"                  # stock_AAAA-MM-DD.csv
STOCK_DIR.mkdir(exist_ok=True)
HIST_ARCHIVO = DATA_RAIZ / "historial_salidas.csv"


def _secreto(nombre: str) -> str:
    try:
        return str(st.secrets.get(nombre, "")).strip()
    except Exception:                                       # noqa: BLE001
        return ""


def _entrada() -> None:
    """
    Pide la clave CTF una sola vez. Una vez escrita, la app queda abierta
    mientras la pestaña del navegador siga abierta (no se cierra sola por
    tiempo). En el computador, sin secrets, no pide nada.
    """
    clave = _secreto("clave_ctf")
    if not clave or st.session_state.get("stock_abierto"):
        return
    ui.cabecera(BASE / "assets" / "logo.png", "Stock CTF", "Uso interno de CTF TECNOLOGÍA SPA")
    ui.seccion("🔒 Acceso", "Escribe la clave CTF.")
    escrita = st.text_input("Clave", type="password", key="pide_clave",
                            label_visibility="collapsed", placeholder="Clave CTF")
    if escrita and escrita == clave:
        st.session_state["stock_abierto"] = True
        st.rerun()
    if escrita:
        md('<div class="seccion-sub t-mal">Clave incorrecta.</div>')
    st.stop()


_entrada()
# ---------------------------------------------------------------------------


# Copiado del Panel CTF (pestaña Stock y lo que usa)


# ---------------------------------------------------------------------------


ALMACEN_PDV = {"E914": "5003", "E357": "5541", "E741": "5245", "E359": "5543",
               "E358": "5542", "E360": "5544"}


CLASE_STOCK = {"1": "Venta", "3": "Exhibición", "6": "Buyback"}


CATEGORIA_ACC = {"AU": "Audio", "PA": "Audio", "BA": "Energía", "CB": "Energía", "CG": "Energía",
                 "CA": "Protección", "LA": "Protección", "EN": "Multimedia", "NO": "Multimedia",
                 "SH": "Multimedia", "SB": "Wearable", "SW": "Wearable", "TB": "Tablet"}


MARCA_EQ = {"04": "Motorola", "08": "Samsung", "35": "ZTE", "36": "Apple", "37": "Apple",
            "38": "Apple", "71": "Xiaomi", "73": "NXL", "78": "Honor", "82": "Logic"}


COBERTURA_REPONER = 7      # días: con menos, hay que pedir


COBERTURA_SOBRE = 45       # días: con más, es sobre stock


ESTADOS_ROT = ["Quiebre", "Reponer", "OK", "Sobre stock", "Sin rotación"]


HIST_CANALES = ["Tienda", "Retiro", "Delivery"]


HIST_FUENTES = {"equipos": "Equipos (tienda)", "accesorios": "Accesorios (tienda)",
                "pickup": "Retiro en tienda", "delivery": "Delivery"}


DELIVERY_SALIO = {"DELIVERED", "DELIVERED_TO_COURIER", "DELIVERED_IN_SOURCE", "IN_TRANSIT"}


VENTANA_ROT = 90           # días de venta que se usan para la rotación


CSS_STOCK = """<style>
.tabla-caja.stk table.tabla th { white-space:normal !important; line-height:1.15 !important;
  padding:.25rem .45rem !important; font-size:.8rem !important; vertical-align:bottom; }
.tabla-caja.stk table.tabla th.g-eq { background:#0e7c86 !important; }
.tabla-caja.stk table.tabla th.g-ac { background:#3f8f3a !important; }
.tabla-caja.stk table.tabla th.g-cen { text-align:center !important; }
.tabla-caja.res2 table.tabla th, .tabla-caja.res2 table.tabla td { padding:.12rem .3rem !important;
  font-size:.76rem !important; }
.tabla-caja.res2 table.tabla th.g-ini { border-left:2px solid #ffffff !important; }
.tabla-caja.res2 table.tabla th.g-sub { font-size:.68rem !important; }
.tabla-caja.res2 table.tabla td.g-ini { border-left:2px solid #c3ccd9 !important; }
.tabla-caja.res2 table.tabla td.g-der { background:#f4f7fb; }
.tabla-caja.stk table.tabla td { padding:.12rem .45rem !important; font-size:.84rem !important;
  line-height:1.2 !important; }
</style>"""


DRIVE_API = "https://www.googleapis.com/drive/v3/files"


@_contextlib.contextmanager
def desplegable(titulo: str, expanded: bool = False, **kw):
    """
    Una pestaña desplegable (st.expander) que se puede anidar: Streamlit no
    deja meter un expander dentro de otro, así que si ya se está dentro de uno,
    el de adentro se dibuja como un subtítulo y su contenido va a la vista.

    El título lo lleva la pestaña: si adentro viene un ui.seccion con el mismo
    título, se muestra solo su explicación (v377).
    """
    prof = getattr(_EXP_HILO, "prof", 0)
    etiq_previa = getattr(_EXP_HILO, "etiqueta", "")
    _EXP_HILO.etiqueta = _norm_titulo(titulo)
    try:
        if prof:
            md(f'<div class="seccion" style="margin:.9rem 0 .4rem">{h(titulo)}</div>')
            with st.container():
                yield
            return
        _EXP_HILO.prof = prof + 1
        try:
            with st.expander(titulo, expanded=expanded, **kw):
                yield
        finally:
            _EXP_HILO.prof = prof
    finally:
        _EXP_HILO.etiqueta = etiq_previa


def _norm_titulo(t) -> str:
    return re.sub(r"[^0-9a-záéíóúñü]", "", str(t).lower())


def _seccion_en_desplegable(titulo: str, sub: str = "") -> None:
    """ui.seccion, salvo dentro de una pestaña con el mismo título: ahí solo va la explicación."""
    etiq = getattr(_EXP_HILO, "etiqueta", "")
    t = _norm_titulo(titulo)
    if etiq and t and t in etiq:
        if sub:
            md(f'<div class="seccion-sub" style="margin:.1rem 0 .5rem">{h(sub)}</div>')
        return
    _SECCION_ORIGINAL(titulo, sub)


def _mes_nombre(mes_id: str) -> str:
    try:
        a, m = mes_id.split("-")
        return f"{MESES_NOMBRE[int(m) - 1]} {a}"
    except Exception:                                       # noqa: BLE001
        return mes_id or "—"


def _hoy_chile() -> dt.date:
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo(ZONA_CHILE)).date()
    except Exception:                                       # noqa: BLE001
        return dt.date.today()


def _ahora_chile() -> dt.datetime:
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo(ZONA_CHILE)).replace(tzinfo=None)
    except Exception:                                       # noqa: BLE001
        return dt.datetime.now()


def _limpia_bsale(v) -> str:
    """Bsale escribe los textos como ="…" para que Excel no los convierta."""
    s = "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v).strip()
    if s.startswith('="') and s.endswith('"'):
        s = s[2:-1]
    return "" if s.lower() == "nan" else s.strip()


def _numero_bsale(v) -> float:
    """«158075,0» → 158075.0 (coma decimal, sin separador de miles)."""
    s = _limpia_bsale(v).replace("$", "").replace(" ", "")
    if not s:
        return 0.0
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _leer_bsale(datos: bytes) -> tuple[pd.DataFrame, dict]:
    """
    El «Detalle de ventas» de Bsale → una fila por línea vendida, sin datos del
    cliente. Viene como HTML disfrazado de .xls (igual que ENTEL TIENDAS), pero
    también se acepta un .xlsx de verdad.
    """
    crudo = None
    try:
        crudo = pd.read_html(io.BytesIO(datos), header=None, thousands=None)[0]
    except Exception:                                       # noqa: BLE001
        crudo = pd.read_excel(io.BytesIO(datos), header=None, dtype=str)
    crudo = crudo.astype(object)

    fila_cab, info = None, {}
    for i in range(min(len(crudo), 40)):
        valores = [_limpia_bsale(x) for x in crudo.iloc[i].tolist()]
        normal = [fuentes.norm(x) for x in valores]
        if "VENDEDOR" in normal and "TIPO MOVIMIENTO" in normal:
            fila_cab = i
            break
        if normal and normal[0] in ("FECHA INICIO", "FECHA TERMINO"):
            resto = [x for x, n in zip(valores[1:], normal[1:]) if x and n != normal[0]]
            info[normal[0]] = resto[0] if resto else ""
    if fila_cab is None:
        raise ValueError("no encontré la fila de títulos (Tipo Movimiento, Vendedor…). "
                         "¿Es el «Detalle de ventas» de Bsale?")
    cab = [fuentes.norm(_limpia_bsale(x)) for x in crudo.iloc[fila_cab].tolist()]
    cuerpo = crudo.iloc[fila_cab + 1:].copy()
    cuerpo.columns = cab

    def col(nombre):
        return cuerpo[nombre] if nombre in cuerpo.columns else pd.Series([""] * len(cuerpo), index=cuerpo.index)

    d = pd.DataFrame({
        "movimiento": col("TIPO MOVIMIENTO").map(_limpia_bsale),
        "vendedor": col("VENDEDOR").map(_limpia_bsale),
        "fecha_hora": col("FECHA Y HORA VENTA").map(_limpia_bsale),
        "tipo": col("TIPO DE PRODUCTO / SERVICIO").map(_limpia_bsale),
        "sku": col("SKU").map(_limpia_bsale),
        "producto": col("PRODUCTO / SERVICIO").map(_limpia_bsale),
        "cantidad": col("CANTIDAD").map(_numero_bsale),
        "neto_unit": col("PRECIO NETO UNITARIO").map(_numero_bsale),
        "bruto": col("SUBTOTAL BRUTO").map(_numero_bsale),
    })
    d = d[(d["vendedor"] != "") & (d["movimiento"] != "")].reset_index(drop=True)
    momento = pd.to_datetime(d["fecha_hora"], format="%d/%m/%Y %I:%M %p", errors="coerce")
    falta = momento.isna()
    if falta.any():
        momento[falta] = pd.to_datetime(d.loc[falta, "fecha_hora"], dayfirst=True, errors="coerce")
    d["momento"] = momento
    d["fecha"] = d["momento"].dt.date
    return d.drop(columns=["fecha_hora"]), info


def _clasifica_bsale(d: pd.DataFrame) -> pd.DataFrame:
    """Suma a cada línea en qué columnas de la planilla cuenta."""
    d = d.copy()
    tipo = d["tipo"].map(fuentes.norm)
    sku = d["sku"].map(fuentes.norm)
    prod = d["producto"].map(fuentes.norm)
    mov = d["movimiento"].map(fuentes.norm)
    # una devolución o nota de crédito resta (si Bsale no la trae ya en negativo)
    resta = mov.str.contains("DEVOL|NOTA DE CREDITO|ANULA", regex=True)
    q = d["cantidad"].where(~(resta & (d["cantidad"] > 0)), -d["cantidad"])
    neto = d["neto_unit"] * q

    es_plan = tipo.str.startswith("PLAN")
    es_equipo = (~es_plan) & (tipo.str.contains(r"(?:^|\W)SM\s", regex=True) | tipo.str.contains("PHONE"))
    es_acc = (~es_plan) & (~es_equipo) & (tipo != "")
    es_seguro = es_plan & (sku.str.contains("SEGURO") | prod.str.contains("PROTEGIDO"))

    d["hab"] = np.where(es_plan & sku.str.startswith("HABILITACION"), q, 0.0)
    d["porta"] = np.where(es_plan & sku.str.startswith("PORTABILIDAD"), q, 0.0)
    d["mig"] = np.where(es_plan & sku.str.startswith("MIGRACION"), q, 0.0)
    d["sus"] = d["hab"] + d["porta"]
    d["mov"] = d["sus"] + d["mig"]
    d["fib"] = np.where(es_plan & (sku.str.startswith("FIBRA") | prod.str.startswith("FIBRA")), q, 0.0)
    d["seg"] = np.where(es_seguro, q, 0.0)
    d["eq_q"] = np.where(es_equipo, q, 0.0)
    d["eq"] = np.where(es_equipo, neto, 0.0)
    d["acc_q"] = np.where(es_acc, q, 0.0)
    d["acc"] = np.where(es_acc, neto, 0.0)
    d["ene_q"] = np.where(es_acc & tipo.str.startswith("ENERGIA"), q, 0.0)
    d["ene"] = np.where(es_acc & tipo.str.startswith("ENERGIA"), neto, 0.0)
    d["lam"] = np.where(es_acc & tipo.str.startswith("PROTECCION"), q, 0.0)
    return d


def _guardar_bsale(datos: bytes, nombre: str) -> tuple[bool, str]:
    try:
        d, info = _leer_bsale(datos)
    except Exception as e:                                  # noqa: BLE001
        return False, f"No pude leer el archivo: {e}"
    if d.empty:
        return False, "El archivo no trae ventas."
    salida = d.copy()
    salida["momento"] = salida["momento"].dt.strftime("%Y-%m-%d %H:%M")
    salida = salida.drop(columns=["fecha"])
    salida.to_csv(BSALE_DATOS, index=False, encoding="utf-8")
    ultima = d["momento"].max()
    BSALE_INFO.write_text(json.dumps({
        "archivo": nombre,
        "subido": _ahora_chile().strftime("%Y-%m-%d %H:%M"),
        "desde": info.get("FECHA INICIO", ""), "hasta": info.get("FECHA TERMINO", ""),
        "ultima_venta": "" if pd.isna(ultima) else ultima.strftime("%Y-%m-%d %H:%M"),
        "lineas": int(len(d)),
    }, ensure_ascii=False), encoding="utf-8")
    return True, f"Listo: {len(d)} líneas de venta de {d['vendedor'].nunique()} vendedores."


@st.cache_data(show_spinner=False, max_entries=12, ttl=6 * 3600)
def _bsale_guardado(ruta: str, mtime: float) -> pd.DataFrame:
    d = pd.read_csv(ruta, dtype={"sku": str, "tipo": str, "producto": str, "vendedor": str,
                                 "movimiento": str}, keep_default_na=False)
    for c in ("cantidad", "neto_unit", "bruto"):
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0.0)
    d["momento"] = pd.to_datetime(d["momento"], errors="coerce")
    d["fecha"] = d["momento"].dt.date
    return _clasifica_bsale(d)


def _info_bsale() -> dict:
    try:
        return json.loads(BSALE_INFO.read_text(encoding="utf-8"))
    except Exception:                                       # noqa: BLE001
        return {}


def _aviso_respaldo() -> None:
    """Después de subir: si no se pudo guardar la copia en el Drive, avisarlo."""
    problema = st.session_state.pop("aviso_respaldo", None)
    if problema is None:
        return
    if problema:
        md(f'<div class="seccion-sub t-medio">⚠️ Quedó cargado en la app, pero no pude guardar '
           f'la copia en el Drive ({h(problema)}). Si la app se reinicia, habría que subirlo de '
           'nuevo.</div>')
    else:
        md('<div class="seccion-sub t-bien">☁️ Copia guardada en el Drive: no se pierde si la '
           'app se reinicia.</div>')


def _css_tablas_claras() -> str:
    """
    Todas las tablas de la vista (tablas y mapas de calor) con encabezado azul
    CTF y el cuerpo en los colores del tema elegido (claro u oscuro).
    """
    c = tema.TEMAS["claro"]             # tablas siempre en claro, también en modo oscuro
    E = {k: v[c["clave_estado"]] for k, v in tema.ESTADO.items()}
    oscuro = c["clave_estado"] == "oscuro"
    fija, hover, tot = ((c["tarjeta2"], c["borde"], c["tarjeta2"]) if oscuro
                        else ("#f4f7fb", "#eef3fa", "#e8eef7"))
    T = ".tabla-caja"
    return f"""<style>
{T} {{ background:{c['tarjeta']} !important; border:1px solid {c['borde_fuerte']} !important;
  box-shadow:{c['sombra']}; }}
{T} table.tabla {{ background:{c['tarjeta']} !important; }}
{T} table.tabla th, {T} table.tabla th.fija {{ background:#1F3B63 !important; color:#ffffff !important;
  border-bottom:1px solid #1F3B63 !important; }}
{T} table.tabla th * {{ color:#ffffff !important; }}
{T} table.tabla th .t-tenue {{ color:#c9d6ea !important; }}
{T} table.tabla td {{ color:{c['texto']} !important; border-bottom:1px solid {c['borde']} !important; }}
{T} table.tabla td.fija {{ background:{fija} !important; color:{c['texto']} !important; }}
{T} table.tabla tbody tr:hover td {{ background:{hover} !important; }}
{T} table.tabla tr.total td, {T} table.tabla tr.grupo td {{ background:{tot} !important; }}
{T} .t-bien {{ color:{E['bien']} !important; }}
{T} .t-medio {{ color:{E['medio']} !important; }}
{T} .t-mal {{ color:{E['mal']} !important; }}
{T} .t-tenue {{ color:{c['texto3']} !important; }}
{T} .chip.bien {{ background:{c['chip_bien']} !important; color:{E['bien']} !important; }}
{T} .chip.medio {{ background:{c['chip_medio']} !important; color:{E['medio']} !important; }}
{T} .chip.mal {{ background:{c['chip_mal']} !important; color:{E['mal']} !important; }}
{T} table.tabla.mapa td.hm.bien {{ background:{c['chip_bien']} !important; color:{E['bien']} !important; }}
{T} table.tabla.mapa td.hm.medio {{ background:{c['chip_medio']} !important; color:{E['medio']} !important; }}
{T} table.tabla.mapa td.hm.mal {{ background:{c['chip_mal']} !important; color:{E['mal']} !important; }}
{T} table.tabla.mapa td.hm.nulo {{ color:{c['texto']} !important; }}
{T} table.tabla.mapa td.hm {{ border-right:1px solid {c['tarjeta']} !important; }}
{T} table.tabla.mapa tbody tr:hover td.hm {{ filter:brightness(.97); }}
</style>"""


def _banda_fibra(grupos) -> str:
    """
    Diez indicadores del mismo tamaño en una sola fila, con el nombre de su
    grupo encima. Cada tarjeta: rótulo · cifra (y «de N») · chip o barra · pie.
    """
    t = tema.actual()
    cab, cuerpo, n = "", "", 0
    for nombre, tiles, color in grupos:
        if not tiles:
            continue
        cab += (f'<div class="kx-g" style="grid-column:span {len(tiles)};'
                f'border-color:{color};color:{color}">{h(nombre)}</div>')
        for x in tiles:
            n += 1
            est = x.get("estado") or ""
            de = f' <small>{x["de"]}</small>' if x.get("de") else ""
            linea = (f'<div class="kx-l">{x.get("chip", "")}<span>{x.get("pie", "")}</span></div>'
                     if (x.get("chip") or x.get("pie")) else "")
            cuerpo += (f'<div class="kx tarjeta" style="border-top:3px solid {color}">'
                       f'<div class="kx-r">{h(x["rot"])}</div>'
                       f'<div class="kx-v{(" t-" + est) if est in ("bien", "medio", "mal") else ""}">'
                       f'{x["v"]}{de}</div>{x.get("barra", "")}{linea}</div>')
    if not n:
        return ""
    return f"""<style>
.kx-band {{ display:grid; gap:.3rem .5rem; }}
.kx-g {{ font-size:.76rem; font-weight:800; letter-spacing:.06em; text-transform:uppercase;
  border-bottom:2px solid; padding-bottom:.1rem; }}
.kx {{ padding:.5rem .7rem .55rem !important; border-radius:10px !important; min-width:0;
  display:flex; flex-direction:column; gap:.08rem; }}
.kx-r {{ font-size:.8rem; font-weight:800; letter-spacing:.03em; text-transform:uppercase;
  color:{t['texto2']}; white-space:normal; line-height:1.2; }}
.kx-v {{ font-size:1.65rem; font-weight:800; line-height:1.15; color:{t['texto']};
  font-variant-numeric:tabular-nums; white-space:normal; }}
.kx-v small {{ font-size:.85rem; font-weight:600; color:{t['texto3']}; white-space:nowrap;
  display:inline-block; line-height:1.2; }}
.kx-l {{ display:flex; flex-wrap:wrap; align-items:center; gap:.2rem .35rem; font-size:.8rem;
  color:{t['texto3']}; line-height:1.25; }}
.kx-l .chip {{ white-space:nowrap; }}
.kx-l .chip {{ font-size:.78rem !important; padding:.05rem .4rem !important; }}
.kx-p {{ font-size:.66rem; color:{t['texto3']}; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.kx .barra {{ height:8px !important; margin:.25rem 0 .15rem !important; }}
.kx .barra > .corte {{ top:-3px !important; height:12px !important; }}
@media (max-width: 1250px) {{
  .kx-band {{ grid-template-columns:repeat(5, minmax(0,1fr)) !important; }}
  .kx-g {{ display:none; }}
}}
@media (max-width: 640px) {{ .kx-band {{ grid-template-columns:repeat(2, minmax(0,1fr)) !important; }} }}
</style><div class="kx-band" style="grid-template-columns:repeat({n}, minmax(0,1fr))">{cab}{cuerpo}</div>"""


def _css_calendario() -> str:
    t = tema.actual()
    c = '[data-testid="stDateInputCalendar"]'
    p = '[data-testid^="stDateInput"][data-testid$="Popover"]'   # listas de mes, año y rango
    return (
        "<style>"
        f"{c},{p}{{background:{t['tarjeta']} !important;border:1px solid {t['borde_fuerte']} !important;"
        f"box-shadow:{t['sombra']} !important;}}"
        f"{c} *,{p} *{{color:{t['texto']} !important;}}"
        f"{c} svg,{p} svg{{fill:{t['texto']} !important;}}"
        f"{c} hr,{c} [role=\"separator\"]{{border-color:{t['borde']} !important;}}"
        f"{p} [role=\"option\"][data-focused=\"true\"],{p} [role=\"option\"]:hover,"
        f"{p} [role=\"option\"][data-selected=\"true\"]{{background:{t['tarjeta2']} !important;}}"
        f"{c} [data-outside-month=\"true\"],{c} [data-disabled=\"true\"],{c} [data-unavailable=\"true\"]"
        f"{{color:{t['texto3']} !important;opacity:.6;}}"
        f"{c} [data-selection-start=\"true\"],{c} [data-selection-end=\"true\"]{{color:#fff !important;}}"
        "</style>")


def _pintar_calendario() -> None:
    """Deja el calendario legible con los colores del tema del panel."""
    md(_css_calendario())


class _ArchivoDrive(io.BytesIO):
    """
    Se comporta como el archivo que entrega st.file_uploader: un archivo en
    memoria que se puede leer (read/seek) y que trae su nombre. Antes solo
    tenía getvalue(), y pandas no lo podía abrir: de la dotación bajada de
    Drive se perdían todos los que tienen código CMA_.
    """
    def __init__(self, nombre: str, datos: bytes):
        super().__init__(datos)
        self.name, self.size = nombre, len(datos)


def _drive_credenciales():
    info = None
    try:
        crudo = st.secrets.get("gcp_json", "")
        if crudo:
            # strict=False: al pegar el JSON en Secrets entre comillas triples, los
            # «\n» de la llave privada se vuelven saltos de línea de verdad
            info = json.loads(str(crudo), strict=False)
        elif "gcp_service_account" in st.secrets:
            info = dict(st.secrets["gcp_service_account"])
    except Exception:                                       # noqa: BLE001
        info = None
    return info


def _drive_sesion():
    info = _drive_credenciales()
    if not info:
        return None
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    cred = service_account.Credentials.from_service_account_info(
        # «drive» y no «drive.readonly»: el panel también ESCRIBE su respaldo
        # (respaldo_panel.zip). Leer sigue funcionando igual aunque la cuenta
        # de servicio solo sea Lector de la carpeta.
        info, scopes=["https://www.googleapis.com/auth/drive"])
    return AuthorizedSession(cred)


def _drive_listar(ses) -> list:
    comun = {"supportsAllDrives": "true", "includeItemsFromAllDrives": "true", "pageSize": "1000"}
    nombre = (_secreto("drive_carpeta") or DRIVE_CARPETA).replace("'", "\\\\'")
    r = ses.get(DRIVE_API, params={**comun, "fields": "files(id,name)",
                                   "q": f"name = '{nombre}' and trashed = false and "
                                        "mimeType = 'application/vnd.google-apps.folder'"}, timeout=30)
    r.raise_for_status()
    carpetas = r.json().get("files", [])
    if not carpetas:
        raise RuntimeError(f"no encuentro la carpeta «{nombre}». ¿Está compartida con la cuenta "
                           "de servicio del panel?")
    archivos, por_ver, vistas = [], [carpetas[0]["id"]], set()
    while por_ver:                                          # la carpeta y sus subcarpetas
        cid = por_ver.pop()
        token = None
        while True:
            p = {**comun, "q": f"'{cid}' in parents and trashed = false",
                 "fields": "nextPageToken,files(id,name,mimeType,modifiedTime,size)"}
            if token:
                p["pageToken"] = token
            r = ses.get(DRIVE_API, params=p, timeout=30)
            r.raise_for_status()
            j = r.json()
            for f in j.get("files", []):
                if f["mimeType"] == "application/vnd.google-apps.folder":
                    if f["id"] not in vistas:
                        vistas.add(f["id"])
                        por_ver.append(f["id"])
                elif not f["mimeType"].startswith("application/vnd.google-apps"):
                    archivos.append(f)                      # las Hojas de cálculo de Google no
            token = j.get("nextPageToken")
            if not token:
                break
    return archivos


def _sku_txt(v) -> str:
    s = str(v if v is not None else "").strip().upper()
    if s.endswith(".0"):
        s = s[:-2]
    return "" if s in ("NAN", "NONE") else s


def _clasifica_sku(sku: str, desc: str = "") -> tuple[str, str, str]:
    """(clase, tipo, categoría o marca) a partir del código SAP."""
    sku = _sku_txt(sku)
    # SIM cards: códigos cortos (287, 356, 360, 365…) que dicen SIM
    texto = fuentes.norm(desc or "")
    if re.search(r"\bSIM\b", texto) and (len(sku) <= 4 or "CARD" in texto or texto.startswith("SIM")):
        tipo_sim = ("Cambio" if "CAMBIO" in texto else "Portabilidad" if "PORTA" in texto
                    else "Habilitación" if "HABILIT" in texto else "Suelta" if "SUELTA" in texto
                    else "Otras SIM")
        return "Venta", "SIM cards", tipo_sim
    clase = CLASE_STOCK.get(sku[:1], "Otros")
    # los equipos de exhibición a veces vienen con código de venta (1…) pero
    # dicen DEMO o EXHI en la descripción: esos también son exhibición
    if clase == "Venta" and re.search(r"\b(DEMO|EXHI)\b", fuentes.norm(desc or "")):
        clase = "Exhibición"
    par = sku[1:3]
    if par.isdigit():
        marca = MARCA_EQ.get(par)
        if not marca:
            primera = fuentes.norm(desc).split(" ")[0] if desc else ""
            marca = {"APL": "Apple", "SAM": "Samsung", "HN": "Honor", "MOTO": "Motorola"}.get(
                primera, primera.title() or "Otra")
        return clase, "Equipos", marca
    return clase, "Accesorios", CATEGORIA_ACC.get(par, "Otros accesorios")


def _leer_stock(datos: bytes, nombre: str) -> tuple[pd.DataFrame, dt.date | None]:
    crudo = pd.read_excel(io.BytesIO(datos), header=None, dtype=str)
    fila = next((i for i in range(min(15, len(crudo)))
                 if "ALMACEN" in [fuentes.norm(x) for x in crudo.iloc[i].fillna("")]), None)
    if fila is None:
        raise ValueError("no encontré la columna ALMACÉN. ¿Es el Reporte Stock Disponible?")
    cab = [fuentes.norm(x) for x in crudo.iloc[fila].fillna("")]
    cuerpo = crudo.iloc[fila + 1:].copy()
    cuerpo.columns = cab

    def col(*claves):
        for c in cab:
            if all(k in c for k in claves):
                return cuerpo[c]
        return pd.Series([None] * len(cuerpo), index=cuerpo.index)

    d = pd.DataFrame({
        "almacen": col("ALMACEN").fillna("").astype(str).str.strip().str.upper(),
        "sku": col("CODIGO").map(_sku_txt),
        "descripcion": col("DESCRIPCION").fillna("").astype(str).str.strip(),
        "disponible": pd.to_numeric(col("LIBRE"), errors="coerce").fillna(0),
        "transito": pd.to_numeric(col("TRANSITO"), errors="coerce").fillna(0),
        "bloqueado": pd.to_numeric(col("BLOQUEAD"), errors="coerce").fillna(0),
    })
    d = d[(d["sku"] != "") & (d["almacen"] != "")]
    m = re.search(r"(20\d\d)-(\d\d)-(\d\d)", nombre or "")
    fecha = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None
    return d, fecha


def _guardar_stock(archivos) -> list[str]:
    """Guarda los archivos subidos en el CSV de su día. Devuelve los mensajes."""
    mensajes, por_dia = [], {}
    for a in archivos:
        try:
            d, fecha = _leer_stock(a.getvalue(), a.name)
        except Exception as e:                              # noqa: BLE001
            mensajes.append(f"❌ {a.name}: {e}")
            continue
        fecha = fecha or _hoy_chile()
        por_dia.setdefault(fecha, []).append(d)
        alm = ", ".join(sorted(d["almacen"].unique()))
        mensajes.append(f"✅ {a.name}: {len(d)} SKU · almacén {alm} · {fecha:%d/%m/%Y}")
    for fecha, partes in por_dia.items():
        nuevo = pd.concat(partes, ignore_index=True)
        ruta = STOCK_DIR / f"stock_{fecha:%Y-%m-%d}.csv"
        if ruta.exists():
            viejo = pd.read_csv(ruta, dtype={"sku": str, "almacen": str})
            viejo = viejo[~viejo["almacen"].isin(nuevo["almacen"].unique())]
            nuevo = pd.concat([viejo, nuevo], ignore_index=True)
        nuevo.to_csv(ruta, index=False, encoding="utf-8")
    return mensajes


def _fechas_stock() -> list:
    salida = []
    for p in STOCK_DIR.glob("stock_*.csv"):
        try:
            salida.append(dt.date.fromisoformat(p.stem.replace("stock_", "")))
        except ValueError:
            continue
    return sorted(salida)


@st.cache_data(show_spinner=False, max_entries=12, ttl=6 * 3600)
def _stock_del_dia(ruta: str, mtime: float) -> pd.DataFrame:
    d = pd.read_csv(ruta, dtype={"sku": str, "almacen": str, "descripcion": str},
                    keep_default_na=False)
    for c in ("disponible", "transito", "bloqueado"):
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)
    d["sku"] = d["sku"].map(_sku_txt)
    d["pdv"] = d["almacen"].map(ALMACEN_PDV).fillna(d["almacen"])
    cls = [_clasifica_sku(s, x) for s, x in zip(d["sku"], d["descripcion"])]
    d["clase"] = [c[0] for c in cls]
    d["tipo"] = [c[1] for c in cls]
    d["categoria"] = [c[2] for c in cls]
    return d


def _hist_pdv(serie) -> pd.Series:
    return pd.to_numeric(serie, errors="coerce").astype("Int64").astype(str).replace("<NA>", "")


def _hist_leer(datos: bytes, nombre: str) -> pd.DataFrame:
    """Un archivo de Entel → filas (pdv, sku, fecha, canal, fuente, q, orden)."""
    b = pd.read_excel(io.BytesIO(datos))
    cols = {fuentes.norm(c): c for c in b.columns}

    def c(*nombres):
        return next((cols[n] for n in nombres if n in cols), None)

    if c("COD_PDV_DE_RETIRO"):                                  # Pickup
        # la fecha es la del pedido (requisición), no la del cierre: así cada
        # reporte mensual cae entero en su mes y al reemplazar un mes no se
        # pisan pedidos del reporte del mes anterior
        req = pd.to_datetime(b[c("D_A_REQUISICION")], errors="coerce")
        ok = b[c("ESTADO")].astype(str).str.strip().str.upper() == "CIERRE COMPLETADO"
        x = pd.DataFrame({"pdv": _hist_pdv(b[c("COD_PDV_DE_RETIRO")]),
                          "sku": b[c("SKU")].map(_sku_txt), "fecha": req,
                          "canal": "Retiro", "fuente": "pickup",
                          "q": pd.to_numeric(b[c("CANTIDAD_ORDENES")], errors="coerce").fillna(1),
                          "orden": pd.to_numeric(b[c("NUMERO_NEGOCIO")], errors="coerce")})[ok]
    elif c("ESTADO_ACTUAL_OMNIX"):                              # Delivery
        ok = b[c("ESTADO_ACTUAL_OMNIX")].astype(str).str.strip().str.upper().isin(DELIVERY_SALIO)
        x = pd.DataFrame({"pdv": _hist_pdv(b[c("COD_SS")]), "sku": b[c("SKU")].map(_sku_txt),
                          "fecha": pd.to_datetime(b[c("FECHA INGRESO")], errors="coerce"),
                          "canal": "Delivery", "fuente": "delivery", "q": 1.0,
                          "orden": pd.to_numeric(b[c("NRO_DE_NEGOCIO")], errors="coerce")})[ok]
    elif c("ID DEL PDV") and c("SKU"):                          # EQUIPOS / ACCESORIOS
        fuente = "equipos" if c("LINEA NEGOCIO", "CLASIFICACION*", "IMEI*") else "accesorios"
        q = c("Q ORDENES", "CONTADOR")
        x = pd.DataFrame({"pdv": _hist_pdv(b[c("ID DEL PDV")]), "sku": b[c("SKU")].map(_sku_txt),
                          "fecha": pd.to_datetime(b[c("FECHA")], errors="coerce"),
                          "canal": "Tienda", "fuente": fuente,
                          "q": pd.to_numeric(b[q], errors="coerce").fillna(1) if q else 1.0,
                          "orden": pd.to_numeric(b[c("NUMERO ORDEN")], errors="coerce")
                          if c("NUMERO ORDEN") else np.nan})
    else:
        raise ValueError("no lo reconozco: tiene que ser la base de EQUIPOS o ACCESORIOS, "
                         "o el reporte de Pickup o de Delivery")
    x = x[(x["pdv"] != "") & (x["sku"] != "") & x["fecha"].notna()]
    x["fecha"] = x["fecha"].dt.normalize()
    return x


def _hist_cargado() -> pd.DataFrame:
    vacio = pd.DataFrame(columns=["pdv", "sku", "fecha", "canal", "fuente", "q", "orden"])
    if not HIST_ARCHIVO.exists():
        return vacio
    try:
        return _hist_csv(str(HIST_ARCHIVO), HIST_ARCHIVO.stat().st_mtime)
    except Exception:                                       # noqa: BLE001
        return vacio


@st.cache_data(show_spinner=False, max_entries=12, ttl=6 * 3600)
def _hist_csv(ruta: str, mtime: float) -> pd.DataFrame:
    d = pd.read_csv(ruta, dtype={"pdv": str, "sku": str, "canal": str, "fuente": str})
    d["fecha"] = pd.to_datetime(d["fecha"], errors="coerce")
    d["q"] = pd.to_numeric(d["q"], errors="coerce").fillna(0)
    return d


def _hist_guardar(archivos) -> list[str]:
    """Suma los archivos al historial; un mes de una fuente reemplaza al que había."""
    hist = _hist_cargado()
    mensajes, nuevos, vistos = [], [], set()
    for a in archivos:
        huella = hash(a.getvalue())
        if huella in vistos:                                # el mismo archivo dos veces
            continue
        vistos.add(huella)
        try:
            x = _hist_leer(a.getvalue(), a.name)
        except Exception as e:                              # noqa: BLE001
            mensajes.append(f"❌ {a.name}: {e}")
            continue
        if x.empty:
            mensajes.append(f"⚠️ {a.name}: no trae salidas válidas.")
            continue
        meses = sorted(x["fecha"].dt.strftime("%Y-%m").unique())
        mensajes.append(f"✅ {a.name}: {HIST_FUENTES[x['fuente'].iloc[0]]} · {num(x['q'].sum())} "
                        f"unid. · {', '.join(_mes_nombre(m) for m in meses)}")
        nuevos.append(x)
    if not nuevos:
        return mensajes
    nuevo = pd.concat(nuevos, ignore_index=True)
    # varios archivos del mismo mes y fuente subidos juntos se suman; lo que ya
    # estaba guardado de ese mes y fuente se reemplaza
    clave_n = set(zip(nuevo["fuente"], nuevo["fecha"].dt.strftime("%Y-%m")))
    if not hist.empty:
        clave_h = list(zip(hist["fuente"], hist["fecha"].dt.strftime("%Y-%m")))
        hist = hist[[k not in clave_n for k in clave_h]]
    todo = pd.concat([hist, nuevo], ignore_index=True)
    todo["fecha"] = pd.to_datetime(todo["fecha"], errors="coerce")
    todo.assign(fecha=todo["fecha"].dt.strftime("%Y-%m-%d")).to_csv(
        HIST_ARCHIVO, index=False, encoding="utf-8")
    return mensajes


@st.cache_data(show_spinner=False, max_entries=12, ttl=6 * 3600)
def _salidas_bases(r_eq: str, m_eq: float, r_acc: str, m_acc: float, hasta: str) -> pd.DataFrame:
    """Las bases EQUIPOS y ACCESORIOS del mes en curso, con el mismo formato del historial."""
    partes = []
    for ruta in (r_eq, r_acc):
        if not ruta:
            continue
        try:
            x = _hist_leer(Path(ruta).read_bytes(), Path(ruta).name)
        except Exception:                                   # noqa: BLE001
            continue
        if hasta:
            x = x[x["fecha"] <= pd.Timestamp(hasta)]
        partes.append(x)
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(
        columns=["pdv", "sku", "fecha", "canal", "fuente", "q", "orden"])


def _excel_stock(hojas: dict) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        for nombre, df in hojas.items():
            df.to_excel(w, sheet_name=nombre[:31], index=False)
            ws = w.sheets[nombre[:31]]
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            for col in ws.columns:
                largo = max(len(str(c.value or "")) for c in col[:200])
                ws.column_dimensions[col[0].column_letter].width = min(max(8, largo + 2), 45)
    return buf.getvalue()


def _css_stkt() -> str:
    """Estilo de las tablas de detalle (claro u oscuro, según el tema)."""
    t_ = tema.actual()
    if False:                     # las tablas van siempre en claro, también en modo oscuro
        K = {"BG": t_["tarjeta"], "BORDE": t_["borde_fuerte"], "TXT": t_["texto"], "LINEA": t_["borde"],
             "CERO": "#5b6575", "SA": "#1d2b44", "HOV": t_["tarjeta2"], "SAH": "#24375a"}
    else:
        K = {"BG": "#fff", "BORDE": "#d6dbe3", "TXT": "#10233f", "LINEA": "#edf0f4",
             "CERO": "#b8c0cc", "SA": "#e6eefb", "HOV": "#f4f7fb", "SAH": "#d8e5fa"}
    _css = """<style>
    .stkt { max-height:600px; overflow:auto; border-radius:12px; border:1px solid @BORDE; background:@BG; }
    .stkt table { border-collapse:separate; border-spacing:0; width:100%; font-size:.76rem; color:@TXT; }
    .stkt thead th { position:sticky; z-index:2; color:#fff; text-align:center; padding:.28rem .3rem;
      border-right:1px solid rgba(255,255,255,.25); line-height:1.15; }
    .stkt thead tr:first-child th { top:0; font-size:.74rem; letter-spacing:.03em; text-transform:uppercase; }
    .stkt thead tr:nth-child(2) th { top:1.55rem; font-size:.72rem; font-weight:700; cursor:help; }
    .stkt thead th span { font-weight:500; opacity:.85; font-size:.66rem; }
    .stkt td { padding:.16rem .35rem; border-bottom:1px solid @LINEA; white-space:nowrap; background:@BG; }
    .stkt td.n { text-align:right; font-variant-numeric:tabular-nums; }
    .stkt td.cero { color:@CERO; }
    .stkt td.sa { background:@SA; font-weight:800; text-align:right; }
    .stkt td.desc { white-space:normal; min-width:180px; }
    .stkt td.est { font-weight:800; text-align:center; }
    .stkt tbody tr:hover td { background:@HOV; }
    .stkt tbody tr:hover td.sa { background:@SAH; }
    </style>"""
    for _k, _v in K.items():
        _css = _css.replace("@" + _k, _v)
    return _css


def _tabla_stock_hoy(d: pd.DataFrame, fecha) -> None:
    """Solo el stock de hoy por tienda y producto, sin rotación."""
    LIMITE = 1500
    v = d.copy()
    v["_t"] = v["tienda"].map(fuentes.norm)
    v = v.sort_values(["_t", "tipo", "sku"], kind="stable")
    v["Tienda"] = v["tienda"].astype(str).str.replace(r"^CTF\s+", "", regex=True).str.title()
    cols = [("Tienda", "Tienda", "", "izq"), ("sku", "SKU", "", "izq"),
            ("descripcion", "Descripción", "", "desc"), ("categoria", "Categoría", "", "izq"),
            ("disponible", "Disponible", "SAP", "n"), ("transito", "En", "tránsito", "n"),
            ("bloqueado", "Bloqueado", "", "n"), ("actual", "Stock", "actual", "sa")]
    rojo = "#b42323"                    # tablas siempre en claro

    def _m(x):
        try:
            return f"{float(x):,.0f}".replace(",", ".")
        except (TypeError, ValueError):
            return "—"

    def _cel(c, clase, val):
        if clase == "izq":
            return f'<td class="izq">{h(str(val))}</td>'
        if clase == "desc":
            return f'<td class="izq desc">{h(str(val))}</td>'
        if clase == "sa":
            return f'<td class="n sa">{_m(val)}</td>'
        if c == "bloqueado" and val:
            return f'<td class="n" style="color:{rojo};font-weight:700">{_m(val)}</td>'
        return f'<td class="n{" cero" if not val else ""}">{_m(val)}</td>'

    th1 = ('<th colspan="4" class="g" style="background:#475569">Producto</th>'
           '<th colspan="4" class="g" style="background:#0e7490">📦 Stock hoy</th>')
    th2 = "".join(f'<th class="s" style="background:{"#475569" if i < 4 else "#0e7490"}">{h(a)}'
                  f'{f"<br><span>{h(b)}</span>" if b else ""}</th>'
                  for i, (_, a, b, _) in enumerate(cols))
    vt = v.head(LIMITE)
    filas = "".join("<tr>" + "".join(_cel(c, k, r[c]) for c, _, _, k in cols) + "</tr>"
                    for _, r in vt.iterrows())
    tot = ('<tr><td class="izq" colspan="4"><b>Total</b></td>'
           + "".join(f'<td class="n{" sa" if c == "actual" else ""}"><b>{_m(v[c].sum())}</b></td>'
                     for c in ("disponible", "transito", "bloqueado", "actual")) + "</tr>")
    md(_css_stkt())
    md(f'<div class="stkt"><table><thead><tr>{th1}</tr><tr>{th2}</tr></thead>'
       f'<tbody>{filas}{tot}</tbody></table></div>')
    if len(v) > LIMITE:
        md(f'<div class="seccion-sub t-medio">Se muestran {LIMITE} de {num(len(v))} filas: '
           'usa los filtros de arriba o descarga el Excel para verlas todas.</div>')
    xls = v[[c for c, _, _, _ in cols]].rename(columns={
        "sku": "SKU", "descripcion": "Descripción", "categoria": "Categoría", "disponible": "Disponible SAP",
        "transito": "En tránsito", "bloqueado": "Bloqueado", "actual": "Stock actual"})
    st.download_button("⬇️ Stock hoy en Excel", _excel_stock({"Stock hoy": xls}),
                       file_name=f"stock_hoy_{fecha:%Y-%m-%d}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       key="stk_hoy_xlsx")


def desplegable_historial() -> None:
    """Carga del historial de ventas y salidas: va al final de la página."""
    hist = _hist_cargado()
    with desplegable("📚 Historial de ventas y salidas (tienda, retiro en tienda y delivery)",
                     expanded=False):
        md('<div class="seccion-sub">Con esto la rotación mira los últimos '
           f'<b>{VENTANA_ROT} días</b> y no solo el mes en curso. Sube las bases de <b>EQUIPOS</b> y '
           '<b>ACCESORIOS</b> (de varios meses juntos o de a uno) y los reportes de <b>Pickup</b> y '
           '<b>Delivery</b>. Subir de nuevo un mes reemplaza solo ese mes de ese archivo. '
           'Del retiro se cuenta lo «Cierre completado» y del delivery lo despachado (sin '
           'cancelados). Súbelos aquí, no en la carpeta del Drive.</div>')
        subidos_h = st.file_uploader("Historial", type=["xlsx", "xls"], accept_multiple_files=True,
                                     key="hist_subir", label_visibility="collapsed")
        if subidos_h:
            firma_h = "|".join(f"{a.name}·{a.size}" for a in subidos_h)
            if st.session_state.get("hist_firma") != firma_h:
                st.session_state["hist_firma"] = firma_h
                with st.spinner("Leyendo los archivos…"):
                    st.session_state["hist_msgs"] = _hist_guardar(subidos_h)
                st.session_state["aviso_respaldo"] = respaldar_en_drive()
                st.rerun()
        for m_ in st.session_state.pop("hist_msgs", []):
            md(f'<div class="seccion-sub">{h(m_)}</div>')
        _aviso_respaldo()
        if not hist.empty:
            cob = (hist.assign(mes=hist["fecha"].dt.strftime("%Y-%m"))
                   .pivot_table(index="fuente", columns="mes", values="q", aggfunc="sum", fill_value=0))
            cob.index = [HIST_FUENTES.get(i, i) for i in cob.index]
            cob.columns = [_mes_nombre(c)[:3] + " " + c[2:4] for c in cob.columns]
            md('<div class="seccion-sub">Unidades cargadas por mes:</div>')
            st.dataframe(cob.astype(int), use_container_width=True)
        else:
            st.caption("Todavía no hay historial cargado: la rotación usa solo el mes en curso.")


def vista_stock() -> None:
    _t = tema.actual()
    md(_css_tablas_claras() + CSS_STOCK)
    ui.seccion("📦 Stock",
               "Stock de cada tienda (SAP) menos lo vendido hoy en Bsale, y la rotación del mes "
               "de cada producto contra el stock que queda.")
    fechas = _fechas_stock()

    with desplegable("📥 Cargar stock del día", expanded=not fechas):
        md('<div class="seccion-sub">Sube el <b>Reporte Stock Disponible</b> de cada tienda (los '
           'seis juntos o de a uno). La fecha se toma del nombre del archivo '
           '(<i>Reporte_Stock_Disponible_2026-09-29</i>); si no la trae, se usa la de hoy. '
           'Subir de nuevo una tienda el mismo día reemplaza solo esa tienda.</div>')
        subidos = st.file_uploader("Reporte Stock Disponible", type=["xlsx", "xls"],
                                   accept_multiple_files=True, key="stock_subir",
                                   label_visibility="collapsed")
        if subidos:
            firma = "|".join(f"{a.name}·{a.size}" for a in subidos)
            if st.session_state.get("stock_firma") != firma:
                st.session_state["stock_firma"] = firma
                for m in _guardar_stock(subidos):
                    md(f'<div class="seccion-sub">{h(m)}</div>')
                st.session_state["aviso_respaldo"] = respaldar_en_drive()
                st.rerun()
        _aviso_respaldo()

    hist = _hist_cargado()

    _bloque_bsale()

    if not fechas:
        st.info("Todavía no hay stock cargado. Sube los reportes de stock arriba.")
        return

    # ── filtros ─────────────────────────────────────────────────────────────
    _pintar_calendario()
    c0, c1, c2, c3 = st.columns([0.55, 2.2, 1.3, 1.1])   # fecha angosta; más espacio a tiendas
    with c0:
        elegida = st.date_input("Stock del día", fechas[-1], format="DD/MM/YYYY",
                                key="stk_fecha_cal")
    # si ese día no se cargó stock, se usa el último cargado antes de esa fecha
    previas = [f for f in fechas if f <= elegida]
    fecha = previas[-1] if previas else fechas[0]
    if fecha != elegida:
        md(f'<div class="seccion-sub t-medio">No hay stock cargado del {elegida:%d/%m/%Y}: '
           f'se muestra el del <b>{fecha:%d/%m/%Y}</b>. Días con stock: '
           f'{h(", ".join(f"{x:%d/%m}" for x in fechas[-10:]))}.</div>')
    ruta = STOCK_DIR / f"stock_{fecha:%Y-%m-%d}.csv"
    s = _stock_del_dia(str(ruta), ruta.stat().st_mtime)
    pdvs = [p for p in TIENDAS["pdv"] if p in set(s["pdv"])] + \
           sorted(set(s["pdv"]) - set(TIENDAS["pdv"]))
    with c1:
        tiendas = st.multiselect("Tienda", pdvs, default=pdvs, key="stk_tienda",
                                 format_func=lambda p: NOMBRE_TIENDA.get(p, p))
    with c2:
        tipos = st.multiselect("Tipo de producto", ["Equipos", "Accesorios", "SIM cards"],
                               default=["Equipos", "Accesorios", "SIM cards"], key="stk_tipo")
    with c3:
        clases = st.multiselect("Clase", ["Venta", "Exhibición", "Buyback", "Otros"],
                                default=["Venta"], key="stk_clase")
    c4, c5 = st.columns([1.6, 1.6])
    base = s[s["pdv"].isin(tiendas) & s["tipo"].isin(tipos) & s["clase"].isin(clases)]
    with c4:
        cats = sorted(base["categoria"].unique())
        cat_sel = st.multiselect("Categoría / marca", cats, default=[], key="stk_cat",
                                 placeholder="Todas")
    with c5:
        buscar = st.text_input("SKU o descripción", key="stk_buscar",
                               placeholder="Ej: 108421 o IPHONE 17")
    agrupar = "Por tienda"   # siempre detalle por tienda (se quitó el selector «Ver»)
    if cat_sel:
        base = base[base["categoria"].isin(cat_sel)]
    if buscar.strip():
        t = fuentes.norm(buscar.strip())
        base = base[base["sku"].str.contains(re.escape(t), na=False)
                    | base["descripcion"].map(fuentes.norm).str.contains(re.escape(t), na=False)]

    faltan = [NOMBRE_TIENDA.get(p, p) for a, p in ALMACEN_PDV.items() if p not in set(s["pdv"])]
    if faltan:
        md(f'<div class="seccion-sub t-medio">⚠️ Falta el stock del {fecha:%d/%m} de: '
           f'<b>{h(", ".join(faltan))}</b>.</div>')

    # ── venta de hoy (Bsale) ────────────────────────────────────────────────
    hoy, sin_tienda = _ventas_bsale_sku(elegida)
    d = base.merge(hoy, on=["pdv", "sku"], how="left")
    d["vendido_hoy"] = pd.to_numeric(d["vendido_hoy"], errors="coerce").fillna(0)
    d["actual"] = (d["disponible"] - d["vendido_hoy"]).clip(lower=0)

    # ── rotación: historial de salidas (tienda + retiro + delivery) ─────────
    # La venta diaria sale de los últimos VENTANA_ROT días hasta el día del
    # stock (o desde donde haya datos, si el historial es más corto).
    sal = _salidas(fecha)
    hasta_ts = pd.Timestamp(fecha)
    ini_ventana = hasta_ts - pd.Timedelta(days=VENTANA_ROT - 1)
    ini_datos = sal["fecha"].min() if not sal.empty else hasta_ts.replace(day=1)
    desde_ts = max(ini_ventana, ini_datos)
    dias_vent = max((hasta_ts - desde_ts).days + 1, 1)
    ini_mes = hasta_ts.replace(day=1)
    if not sal.empty:
        v_ = sal[sal["fecha"] >= desde_ts]
        rot = v_.pivot_table(index=["pdv", "sku"], columns="canal", values="q",
                             aggfunc="sum", fill_value=0)
        for c_ in HIST_CANALES:
            if c_ not in rot.columns:
                rot[c_] = 0.0
        rot = rot[HIST_CANALES].rename(columns={"Tienda": "v_tienda", "Retiro": "v_retiro",
                                                 "Delivery": "v_delivery"})
        rot["vendido_vent"] = rot.sum(axis=1)
        rot["vendido_mes"] = sal[sal["fecha"] >= ini_mes].groupby(["pdv", "sku"])["q"].sum()
        rot["ultima_venta"] = sal.groupby(["pdv", "sku"])["fecha"].max()
        # tendencia: ritmo de los últimos 30 días contra el de la ventana completa
        ult30 = sal[sal["fecha"] > hasta_ts - pd.Timedelta(days=30)].groupby(["pdv", "sku"])["q"].sum()
        rot["v_30"] = ult30
        rot = rot.reset_index()
    else:
        rot = pd.DataFrame(columns=["pdv", "sku", "v_tienda", "v_retiro", "v_delivery",
                                    "vendido_vent", "vendido_mes", "ultima_venta", "v_30"])
    d = d.merge(rot, on=["pdv", "sku"], how="left")
    for c_ in ("v_tienda", "v_retiro", "v_delivery", "vendido_vent", "vendido_mes", "v_30"):
        d[c_] = pd.to_numeric(d[c_], errors="coerce").fillna(0)
    # la última venta también fuera de la ventana (para «sin rotación hace…»)
    if not sal.empty:
        ult_total = sal.groupby(["pdv", "sku"])["fecha"].max().rename("ult2").reset_index()
        d = d.merge(ult_total, on=["pdv", "sku"], how="left")
        d["ultima_venta"] = d["ult2"]
        d = d.drop(columns="ult2")
    dias_mes = dias_vent                                    # compatibilidad con lo de abajo

    def estado(r):
        # las SIM no tienen venta por SKU en tienda con qué medirlas
        if r["clase"] != "Venta" or r["tipo"] == "SIM cards":
            return "—"
        if r["vendido_vent"] <= 0:
            return "Sin rotación" if r["actual"] > 0 else "—"
        if r["actual"] <= 0:
            return "Quiebre"
        cob = r["actual"] / (r["vendido_vent"] / dias_vent)
        return ("Reponer" if cob < COBERTURA_REPONER else
                "Sobre stock" if cob > COBERTURA_SOBRE else "OK")

    def cobertura(r):
        if r["vendido_vent"] <= 0:
            return None
        return round(r["actual"] / (r["vendido_vent"] / dias_vent), 1)

    def tendencia(r):
        if r["vendido_vent"] <= 0 or dias_vent < 45:
            return "—"
        ritmo_30 = r["v_30"] / 30
        ritmo = r["vendido_vent"] / dias_vent
        if ritmo_30 >= ritmo * 1.25:
            return "▲ sube"
        if ritmo_30 <= ritmo * 0.75:
            return "▼ baja"
        return "■ estable"

    if not d.empty:
        d["venta_dia"] = (d["vendido_vent"] / dias_vent).round(2)
        d["venta_mes_prom"] = (d["vendido_vent"] / dias_vent * 30).round(1)
        d["cobertura"] = d.apply(cobertura, axis=1)
        d["estado"] = d.apply(estado, axis=1)
        d["tendencia"] = d.apply(tendencia, axis=1)
        hoy_ts = hasta_ts
        d["dias_sin_venta"] = [(hoy_ts - pd.Timestamp(u)).days if pd.notna(u) else None
                               for u in d.get("ultima_venta", pd.Series([None] * len(d)))]
    else:
        for c_ in ("venta_dia", "venta_mes_prom", "cobertura", "estado", "tendencia", "dias_sin_venta"):
            d[c_] = []
    d["tienda"] = d["pdv"].map(lambda p: NOMBRE_TIENDA.get(p, p))

    if d.empty:
        st.info("No hay productos con esos filtros.")
        return

    # ── resumen por tienda ──────────────────────────────────────────────────

    # cada indicador en dos columnas: cuántos SKU distintos y cuántas unidades
    GRUPOS_RES = [  # (rótulo, color, filtro de filas, columna de unidades)
        ("Equipos", "#0e7c86", lambda g: g[(g["tipo"] == "Equipos") & (g["disponible"] > 0)], "disponible"),
        ("Accesorios", "#3f8f3a", lambda g: g[(g["tipo"] == "Accesorios") & (g["disponible"] > 0)], "disponible"),
        ("SIM cards", "#7a1f6e", lambda g: g[(g["tipo"] == "SIM cards") & (g["disponible"] > 0)], "disponible"),
        ("En tránsito", "#2f6fb0", lambda g: g[g["transito"] > 0], "transito"),
        ("Bloqueado", "#b42323", lambda g: g[g["bloqueado"] > 0], "bloqueado"),
        ("Stock actual", "#1F3B63", lambda g: g[g["actual"] > 0], "actual"),
        ("Vendido mes", "#0e7490", lambda g: g[g["vendido_mes"] > 0], "vendido_mes"),
        ("Quiebre", "#c2410c", lambda g: g[g["estado"] == "Quiebre"], "vendido_mes"),
        ("Reponer", "#b45309", lambda g: g[g["estado"] == "Reponer"], "actual"),
        ("Sobre stock", "#6d28d9", lambda g: g[g["estado"] == "Sobre stock"], "actual"),
        ("Sin rotación", "#5b6b82", lambda g: g[g["estado"] == "Sin rotación"], "actual"),
    ]

    def _fila_res(g, rotulo):
        fila = [rotulo]
        for nombre, _, filtro, col in GRUPOS_RES:
            x = filtro(g)
            unid = num(x[col].sum())
            fila += [num(x["sku"].nunique()), f"<b>{unid}</b>" if nombre == "Stock actual" else unid]
        return fila

    filas = [_fila_res(d[d["pdv"] == p], f'<b>{h(NOMBRE_TIENDA.get(p, p))}</b>')
             for p in [x for x in pdvs if x in set(d["pdv"])]]
    total = _fila_res(d, "<b>Total</b>")
    # ── stock hoy (sin rotación) ────────────────────────────────────────────
    with desplegable("📦 Stock hoy", expanded=True):
        md('<div class="seccion-sub">Stock de cada tienda y producto, ordenado de la A a la Z '
           'por tienda, tipo de producto y SKU. Usa los filtros de arriba para acotar.</div>')
        _tabla_stock_hoy(d, fecha)

    # ── detalle por SKU ─────────────────────────────────────────────────────
    with desplegable("📋 Detalle por producto", expanded=True):   # (v445) siempre abierto
        ui.seccion("Detalle por producto",
                   "Ordenado de la A a la Z por tienda, tipo de producto y SKU. Haz clic en "
                   "cualquier columna para ordenar por ella; el filtro de estado sirve para ver solo "
                   "lo que hay que reponer o lo que sobra.")
        est_sel = st.multiselect("Estado de rotación", ESTADOS_ROT + ["—"], default=[],
                                 key="stk_estado", placeholder="Todos")
        v = d if not est_sel else d[d["estado"].isin(est_sel)]
        if agrupar == "Todas juntas":
            v = v.groupby(["sku", "descripcion", "tipo", "categoria", "clase"], as_index=False).agg(
                **{c_: (c_, "sum") for c_ in ["disponible", "transito", "bloqueado", "vendido_hoy", "actual",
                                             "vendido_mes", "v_tienda", "v_retiro", "v_delivery",
                                             "vendido_vent", "v_30"]},
                ultima_venta=("ultima_venta", "max"))
            v["venta_dia"] = (v["vendido_vent"] / dias_vent).round(2)
            v["venta_mes_prom"] = (v["vendido_vent"] / dias_vent * 30).round(1)
            v["cobertura"] = [round(a / (m / dias_vent), 1) if m > 0 else None
                              for a, m in zip(v["actual"], v["vendido_vent"])]
            v["estado"] = v.apply(estado, axis=1)
            v["tendencia"] = v.apply(tendencia, axis=1)
            v["dias_sin_venta"] = [(hasta_ts - pd.Timestamp(u)).days if pd.notna(u) else None
                                   for u in v["ultima_venta"]]
            cols = []
        else:
            cols = ["tienda"]
        cols += ["sku", "descripcion", "tipo", "categoria", "clase", "disponible", "transito",
                 "bloqueado", "actual", "vendido_mes", "v_tienda", "v_retiro", "v_delivery",
                 "vendido_vent", "venta_mes_prom", "venta_dia", "cobertura", "tendencia",
                 "dias_sin_venta", "estado"]
        nombres = {"tienda": "Tienda", "sku": "SKU", "descripcion": "Descripción", "tipo": "Tipo",
                   "categoria": "Categoría / marca", "clase": "Clase", "disponible": "Disponible",
                   "transito": "En tránsito", "bloqueado": "Bloqueado", "vendido_hoy": "Vendido hoy",
                   "actual": "Stock actual", "vendido_mes": "Vendido mes", "venta_dia": "Venta/día",
                   "v_tienda": f"Tienda {dias_vent}d", "v_retiro": f"Retiro {dias_vent}d",
                   "v_delivery": f"Delivery {dias_vent}d", "vendido_vent": f"Salidas {dias_vent}d",
                   "venta_mes_prom": "Prom. mensual", "tendencia": "Tendencia",
                   "dias_sin_venta": "Días sin venta",
                   "cobertura": "Días cobertura", "estado": "Estado"}
        # orden A→Z para buscar un producto: tienda, tipo de producto y SKU
        orden = [c for c in ("tienda", "tipo", "sku") if c in cols]
        tabla = (v[cols].assign(_t=v[cols]["tienda"].map(fuentes.norm) if "tienda" in cols else "")
                 .sort_values(["_t"] + [c for c in orden if c != "tienda"], kind="stable")
                 .drop(columns="_t").rename(columns=nombres))
        # en pantalla: rótulos cortos, anchos justos (todas las columnas a la vista)
        # y colores: estado de rotación, stock actual, bloqueado y vendido hoy
        vista = tabla.rename(columns={
            "Categoría / marca": "Categoría", "Disponible": "Disp.", "En tránsito": "Tráns.",
            "Bloqueado": "Bloq.", "Vendido hoy": "Vend. hoy", "Stock actual": "Stock act.",
            "Vendido mes": "Vend. mes", "Días cobertura": "Cobertura",
            f"Tienda {dias_vent}d": "En tienda", f"Retiro {dias_vent}d": "Retiro",
            f"Delivery {dias_vent}d": "Deliv.", f"Salidas {dias_vent}d": "Salidas",
            "Prom. mensual": "Prom/mes", "Días sin venta": "Sin venta"})
        if "Tienda" in vista:
            vista["Tienda"] = vista["Tienda"].astype(str).str.replace(r"^CTF\s+", "", regex=True).str.title()
        _osc = False                    # tablas siempre en claro
        COLOR_ESTADO = ({"Quiebre": ("#3a1618", "#f08a8a"), "Reponer": ("#33280a", "#fab219"),
                         "OK": ("#12301a", "#4ccf6a"), "Sobre stock": ("#2a1f45", "#c4b5fd"),
                         "Sin rotación": ("#232a36", "#aab3c0")} if _osc else
                        {"Quiebre": ("#fbdcdc", "#b42323"), "Reponer": ("#fdefc8", "#8a5a00"),
                         "OK": ("#d7f2dc", "#11713a"), "Sobre stock": ("#e9e0fb", "#5b2d8e"),
                         "Sin rotación": ("#e9edf2", "#4b5563")})
        C_ROJO, C_VERDE, C_GRIS = (("#f08a8a", "#4ccf6a", "#98a1af") if _osc
                                   else ("#b42323", "#11713a", "#6b7280"))

        def _pinta_estado(x):
            f, c = COLOR_ESTADO.get(x, ("", ""))
            return f"background-color:{f};color:{c};font-weight:700" if f else "color:#9aa3af"

        def _miles(x):
            try:
                return f"{float(x):,.0f}".replace(",", ".")
            except (TypeError, ValueError):
                return "—"

        enteros = ["Disp.", "Tráns.", "Bloq.", "Stock act.", "Vend. mes",
                   "En tienda", "Retiro", "Deliv.", "Salidas"]
        vista["Sin venta"] = ["—" if pd.isna(x) else f"{int(x)} d"
                              for x in pd.to_numeric(vista["Sin venta"], errors="coerce")]
        vista["Prom/mes"] = pd.to_numeric(vista["Prom/mes"], errors="coerce").fillna(0)
        # Streamlit muestra «None» en los vacíos de una tabla con estilo: la
        # cobertura va como texto («—» cuando no hubo venta en el mes)
        vista["Cobertura"] = [("—" if pd.isna(x) else f"{x:,.1f}".replace(",", "X").replace(".", ",")
                               .replace("X", ".")) for x in pd.to_numeric(vista["Cobertura"], errors="coerce")]
        vista[enteros] = vista[enteros].apply(pd.to_numeric, errors="coerce").fillna(0).round().astype(int)
        sty = (vista.style
               .format({c: _miles for c in enteros})
               .format({"Venta/día": lambda x: f"{x:.2f}".replace(".", ","),
                        "Prom/mes": lambda x: f"{x:.1f}".replace(".", ",")})
               .map(lambda x: "color:#11713a;font-weight:700" if str(x).startswith("▲") else
                    ("color:#b42323;font-weight:700" if str(x).startswith("▼") else "color:#6b7280"),
                    subset=["Tendencia"])
               .map(_pinta_estado, subset=["Estado"])
               .map(lambda x: "background-color:#e6eefb;color:#10233f;font-weight:800", subset=["Stock act."])
               .map(lambda x: "color:#b42323;font-weight:700" if x and x > 0 else "", subset=["Bloq."])
               .map(lambda x: "color:#0e7490" if x and x > 0 else "", subset=["Tráns."])
               .map(lambda x: "text-align:right;color:#9aa3af" if x == "—" else "text-align:right",
                    subset=["Cobertura"]))
        # lo que significa cada columna: aparece al pasar el cursor por el encabezado
        AYUDA_STK = {
            "Disp.": "Disponible: stock libre según SAP el día del reporte.",
            "Tráns.": "En tránsito: unidades que vienen en camino a la tienda.",
            "Bloq.": "Bloqueado: stock que no se puede vender.",
            "Stock act.": "Stock actual = disponible − vendido hoy.",
            "Vend. mes": "Unidades que salieron en el mes en curso (todos los canales).",
            "En tienda": f"Vendido por los ejecutivos en la tienda en los últimos {dias_vent} días.",
            "Retiro": f"Retiro en tienda (pickup) entregado en los últimos {dias_vent} días.",
            "Deliv.": f"Delivery despachado desde la tienda en los últimos {dias_vent} días.",
            "Salidas": f"Total que salió en {dias_vent} días = en tienda + retiro + delivery.",
            "Prom/mes": "Cuánto sale en un mes a este ritmo.",
            "Venta/día": "Unidades que salen por día en promedio.",
            "Cobertura": "Días que alcanza el stock actual a este ritmo (stock ÷ venta/día).",
            "Tendencia": "▲ los últimos 30 días se vende más que el promedio · ▼ menos · ■ igual.",
            "Sin venta": "Días desde la última vez que salió una unidad.",
            "Estado": f"Quiebre: vende y no hay stock · Reponer: < {COBERTURA_REPONER} días · "
                      f"OK · Sobre stock: > {COBERTURA_SOBRE} días · Sin rotación: no sale hace "
                      f"{dias_vent} días.",
        }
        # ── la tabla: encabezado en dos pisos, por grupo y con color ────────────
        # Arriba el grupo (qué pregunta responde), abajo cada columna en palabras
        # de todos los días. Al pasar el cursor, la explicación larga.
        GRUPOS_TAB = [
            ("Producto", "#475569", [("Tienda", "Tienda", ""), ("SKU", "SKU", ""),
                                     ("Descripción", "Descripción", ""), ("Categoría", "Categoría", "")]),
            ("📦 Stock hoy", "#0e7490", [("Disp.", "Disponible", "SAP"), ("Tráns.", "En", "tránsito"),
                                        ("Bloq.", "Bloqueado", ""), 
                                        ("Stock act.", "Stock", "actual")]),
            (f"🛒 Salidas últimos {dias_vent} días", "#3f8f3a",
             [("En tienda", "Venta", "en tienda"), ("Retiro", "Retiro", "en tienda"),
              ("Deliv.", "Delivery", ""), ("Salidas", "Total", "salidas"),
              ("Vend. mes", "Este", "mes")]),
            ("📈 Ritmo de venta", "#6d28d9", [("Prom/mes", "Unid.", "por mes"),
                                             ("Venta/día", "Unid.", "por día"),
                                             ("Tendencia", "Tendencia", "últ. 30 días")]),
            ("⏳ ¿Alcanza?", "#1F3B63", [("Cobertura", "Días de", "stock"),
                                         ("Sin venta", "Días sin", "venta"), ("Estado", "Estado", "")]),
        ]
        cols_tab = [(c, a, b, k) for k, (_, _, cs) in enumerate(GRUPOS_TAB) for (c, a, b) in cs
                    if c in vista.columns]
        ORDENES = {"Tienda y SKU": None, "Urgencia (quiebre primero)": "estado",
                   "Más días de stock": "cob_desc", "Menos días de stock": "cob_asc",
                   "Más salidas": "salidas", "Más días sin venta": "sinventa"}
        c_o, _ = st.columns([1.2, 3])
        with c_o:
            orden_sel = st.selectbox("Ordenar por", list(ORDENES), key="stk_orden_tab")
        vt = vista.copy()
        _num = lambda col: pd.to_numeric(vt[col].astype(str).str.replace(".", "", regex=False)
                                          .str.replace(",", ".", regex=False).str.replace(" d", "", regex=False),
                                          errors="coerce")
        o = ORDENES[orden_sel]
        if o == "estado":
            rk = {"Quiebre": 0, "Reponer": 1, "Sobre stock": 2, "Sin rotación": 3, "OK": 4}
            vt = vt.assign(_o=vt["Estado"].map(rk).fillna(9)).sort_values("_o", kind="stable")
        elif o in ("cob_desc", "cob_asc"):
            vt = vt.assign(_o=_num("Cobertura")).sort_values("_o", ascending=(o == "cob_asc"),
                                                             na_position="last", kind="stable")
        elif o == "salidas":
            vt = vt.sort_values("Salidas", ascending=False, kind="stable")
        elif o == "sinventa":
            vt = vt.assign(_o=_num("Sin venta")).sort_values("_o", ascending=False,
                                                             na_position="last", kind="stable")
        LIMITE = 1500
        total_filas = len(vt)
        vt = vt.head(LIMITE)

        def _cel(col, val):
            txt = val
            if col in enteros:
                txt = _miles(val)
                if col == "Stock act.":
                    return f'<td class="n sa">{txt}</td>'
                if col == "Bloq." and val:
                    return f'<td class="n" style="color:{C_ROJO};font-weight:700">{txt}</td>'
                if col == "Vend. hoy" and val:
                    return f'<td class="n" style="color:#11713a;font-weight:700">{txt}</td>'
                if col in ("Salidas",):
                    return f'<td class="n" style="font-weight:700">{txt}</td>'
                return f'<td class="n{" cero" if not val else ""}">{txt}</td>'
            if col == "Prom/mes":
                return f'<td class="n">{float(val):.1f}</td>'.replace(".", ",")
            if col == "Venta/día":
                return f'<td class="n">{float(val):.2f}</td>'.replace(".", ",")
            if col == "Estado":
                f_, c_ = COLOR_ESTADO.get(val, ("", C_GRIS))
                return (f'<td class="est" style="background:{f_};color:{c_}">{h(str(val))}</td>' if f_
                        else f'<td class="est" style="color:{C_GRIS}">{h(str(val))}</td>')
            if col == "Tendencia":
                color = C_VERDE if str(val).startswith("▲") else C_ROJO if str(val).startswith("▼") else C_GRIS
                return f'<td style="color:{color};font-weight:700;white-space:nowrap">{h(str(val))}</td>'
            if col in ("Cobertura", "Sin venta"):
                return f'<td class="n{" cero" if val == "—" else ""}">{h(str(val))}</td>'
            if col == "Descripción":
                return f'<td class="izq desc">{h(str(val))}</td>'
            return f'<td class="izq">{h(str(val))}</td>'

        th1 = ""
        for k, (g, color, cs) in enumerate(GRUPOS_TAB):
            n_ = sum(1 for c in cs if c[0] in vista.columns)
            if n_:
                th1 += f'<th colspan="{n_}" class="g" style="background:{color}">{h(g)}</th>'
        th2 = ""
        for c, a, b, k in cols_tab:
            color = GRUPOS_TAB[k][1]
            ayuda = AYUDA_STK.get(c, "")
            th2 += (f'<th class="s" style="background:{color}" title="{h(ayuda)}">{h(a)}'
                    f'{f"<br><span>{h(b)}</span>" if b else ""}</th>')
        filas_html = "".join(
            "<tr>" + "".join(_cel(c, r[c]) for c, _, _, _ in cols_tab) + "</tr>"
            for _, r in vt.iterrows())
        md(_css_stkt())
        md(f'<div class="stkt"><table><thead><tr>{th1}</tr><tr>{th2}</tr></thead>'
           f'<tbody>{filas_html}</tbody></table></div>')
        if total_filas > LIMITE:
            md(f'<div class="seccion-sub t-medio">Se muestran {LIMITE} de {num(total_filas)} filas: '
               'usa los filtros de arriba o descarga el Excel para verlas todas.</div>')
        md('<div class="seccion-sub" style="font-size:.74rem">Pasa el cursor por cada encabezado para '
           'ver qué significa.</div>')
        md('<div class="seccion-sub" style="font-size:.76rem">Estado: '
           '<b style="color:#e66767">Quiebre</b> · <b style="color:#fab219">Reponer</b> (&lt; '
           f'{COBERTURA_REPONER} días) · <b style="color:#0ca30c">OK</b> · '
           f'<b style="color:#c4b5fd">Sobre stock</b> (&gt; {COBERTURA_SOBRE} días) · '
           f'<b>Sin rotación</b> (con stock y sin salidas en {dias_vent} días). <b>En tienda / Retiro / '
           f'Deliv.</b> = salidas de cada canal en esos {dias_vent} días · <b>Salidas</b> = la suma · '
           '<b>Prom/mes</b> = salidas de un mes a ese ritmo · <b>Cobertura</b> = stock actual ÷ venta/día · '
           '<b>Tendencia</b> = ritmo de los últimos 30 días contra el de todo el período · '
           '<b>Sin venta</b> = días desde la última salida.</div>')
        resumen_df = pd.DataFrame(
            [[x.replace("<b>", "").replace("</b>", "") for x in f] for f in filas + [total]],
            columns=["Tienda"] + [f"{g[0]} {x}" for g in GRUPOS_RES for x in ("SKU", "unid.")])
        b1, b2, _ = st.columns([1, 1, 4])
        with b1:
            st.download_button("⬇️ Descargar en Excel", _excel_stock({
                "Stock": tabla, "Resumen tiendas": resumen_df}),
                file_name=f"stock_{fecha:%Y-%m-%d}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="stk_xlsx")
        with b2:
            try:
                filtros = (f"Stock SAP del {fecha:%d/%m/%Y} · venta Bsale del {elegida:%d/%m/%Y} · "
                           f"Tiendas: {', '.join(NOMBRE_TIENDA.get(p, p) for p in tiendas) or '—'} · "
                           f"Tipo: {', '.join(tipos) or '—'} · Clase: {', '.join(clases) or '—'}"
                           + (f" · Categoría: {', '.join(cat_sel)}" if cat_sel else "")
                           + (f" · Búsqueda: {buscar.strip()}" if buscar.strip() else "")
                           + (f" · Estado: {', '.join(est_sel)}" if est_sel else ""))
                st.download_button("⬇️ Descargar en PDF", _pdf_stock(
                    resumen_df, vista.drop(columns=["En tienda", "Retiro", "Deliv.", "Prom/mes", "Clase",
                                                    "Tendencia"], errors="ignore"), filtros),
                                   file_name=f"stock_{fecha:%Y-%m-%d}.pdf", mime="application/pdf",
                                   key="stk_pdf")
            except Exception as e:                              # noqa: BLE001
                st.caption(f"No pude armar el PDF: {e}")


def _pdf_stock(resumen: pd.DataFrame, detalle: pd.DataFrame, filtros: str) -> bytes:
    """PDF A4 apaisado: resumen por tienda y detalle por producto con el estado en color."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (Image, Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=10 * mm, rightMargin=10 * mm,
                            topMargin=10 * mm, bottomMargin=10 * mm,
                            title="Stock CTF", author="Stock CTF")
    azul = colors.HexColor("#1F3B63")
    t_tit = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=14, textColor=azul)
    t_sub = ParagraphStyle("s", fontName="Helvetica", fontSize=7.5, textColor=colors.HexColor("#4b5563"),
                           leading=9.5)
    t_sec = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=10, textColor=azul, spaceBefore=6)
    celda = ParagraphStyle("c", fontName="Helvetica", fontSize=6.6, leading=7.8)
    celda_h = ParagraphStyle("ch", fontName="Helvetica-Bold", fontSize=6.6, leading=7.8,
                             textColor=colors.white)
    partes = []
    logo = BASE / "assets" / "logo.png"
    cab = [Paragraph("Stock y rotación · CTF", t_tit)]
    if logo.exists():
        partes.append(Table([[cab[0], Image(str(logo), width=34 * mm, height=11 * mm)]],
                            colWidths=[240 * mm, 37 * mm],
                            style=[("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (1, 0), (1, 0), "RIGHT")]))
    else:
        partes += cab
    partes += [Paragraph(h(filtros) + f" · Generado {_ahora_chile():%d/%m/%Y %H:%M}", t_sub),
               Spacer(1, 4)]

    def _tabla(df, anchos, num_desde, estado_col=None):
        filas_ = [[Paragraph(h(str(c)), celda_h) for c in df.columns]]
        for _, r in df.iterrows():
            fila = []
            for i, c in enumerate(df.columns):
                val = r[c]
                if isinstance(val, float):
                    txt = "—" if pd.isna(val) else f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                elif isinstance(val, (int, np.integer)):
                    txt = f"{int(val):,}".replace(",", ".")
                else:
                    txt = str(val)
                fila.append(Paragraph(h(txt), celda) if i < num_desde else txt)
            filas_.append(fila)
        t = Table(filas_, colWidths=anchos, repeatRows=1)
        est = [("BACKGROUND", (0, 0), (-1, 0), azul),
               ("FONTNAME", (0, 1), (-1, -1), "Helvetica"), ("FONTSIZE", (0, 1), (-1, -1), 6.6),
               ("ALIGN", (num_desde, 1), (-1, -1), "RIGHT"),
               ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
               ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d5dde8")),
               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f7fb")]),
               ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]
        if estado_col is not None:
            j = list(df.columns).index(estado_col)
            tonos = {"Quiebre": ("#fbdcdc", "#b42323"), "Reponer": ("#fdefc8", "#8a5a00"),
                     "OK": ("#d7f2dc", "#11713a"), "Sobre stock": ("#e9e0fb", "#5b2d8e"),
                     "Sin rotación": ("#e9edf2", "#4b5563")}
            for i, x in enumerate(df[estado_col].tolist(), start=1):
                if x in tonos:
                    est += [("BACKGROUND", (j, i), (j, i), colors.HexColor(tonos[x][0])),
                            ("TEXTCOLOR", (j, i), (j, i), colors.HexColor(tonos[x][1])),
                            ("FONTNAME", (j, i), (j, i), "Helvetica-Bold"), ("ALIGN", (j, i), (j, i), "LEFT")]
            if "Stock act." in df.columns:
                k = list(df.columns).index("Stock act.")
                est += [("BACKGROUND", (k, 1), (k, -1), colors.HexColor("#e6eefb")),
                        ("FONTNAME", (k, 1), (k, -1), "Helvetica-Bold")]
        else:
            est += [("BACKGROUND", (0, len(filas_) - 1), (-1, len(filas_) - 1), colors.HexColor("#e8eef7")),
                    ("FONTNAME", (0, len(filas_) - 1), (-1, len(filas_) - 1), "Helvetica-Bold")]
        t.setStyle(TableStyle(est))
        return t

    partes += [Paragraph("Resumen por tienda", t_sec), Spacer(1, 2),
               _tabla(resumen, [35 * mm] + [(242 / max(len(resumen.columns) - 1, 1)) * mm] * (len(resumen.columns) - 1), 1), Spacer(1, 6),
               Paragraph(f"Detalle por producto ({len(detalle)} filas)", t_sec), Spacer(1, 2)]
    ancho_total = 277 * mm
    fijos = {"Tienda": 26, "SKU": 17, "Descripción": 58, "Tipo": 15, "Categoría": 17, "Clase": 13,
             "Estado": 18}
    cols = list(detalle.columns)
    resto = [c for c in cols if c not in fijos]
    libre = ancho_total / mm - sum(fijos[c] for c in cols if c in fijos)
    anchos = [(fijos[c] if c in fijos else libre / max(len(resto), 1)) * mm for c in cols]
    num_desde = next((i for i, c in enumerate(cols) if c == "Disp."), len(cols))
    partes.append(_tabla(detalle, anchos, num_desde, estado_col="Estado" if "Estado" in cols else None))
    partes += [Spacer(1, 4), Paragraph(
        f"Estado: Quiebre = se vende y no hay stock · Reponer = menos de {COBERTURA_REPONER} días de "
        f"cobertura · Sobre stock = más de {COBERTURA_SOBRE} días · Sin rotación = stock sin venta en el "
        "mes. Cobertura = stock actual ÷ venta diaria del mes.", t_sub)]
    doc.build(partes)
    return buf.getvalue()
# ---------------------------------------------------------------------------
# Lo propio de la app (lo que en el panel dependía de otras pestañas)
# ---------------------------------------------------------------------------
_EXP_HILO = _threading.local()
_SECCION_ORIGINAL = ui.seccion
ui.seccion = _seccion_en_desplegable


def _ts_utc(x) -> pd.Timestamp | None:
    """Una fecha cualquiera (ISO del Drive, «AAAA-MM-DD HH:MM» de Chile…) → UTC."""
    if x is None or str(x).strip() == "":
        return None
    try:
        t = pd.Timestamp(str(x).strip())
    except Exception:                                       # noqa: BLE001
        return None
    if t.tzinfo is None:
        try:
            t = t.tz_localize(ZONA_CHILE, ambiguous="NaT", nonexistent="shift_forward")
        except Exception:                                   # noqa: BLE001
            t = t.tz_localize("UTC")
    return t.tz_convert("UTC")


def _chile_txt(t: pd.Timestamp | None) -> str:
    return "" if t is None or pd.isna(t) else t.tz_convert(ZONA_CHILE).strftime("%Y-%m-%d %H:%M")


# ── vendedores: la tienda de cada vendedor de Bsale sale de la DOTACIÓN ─────
# De la dotación se guardan SOLO el código, el nombre y la tienda (nada de RUT,
# correos ni teléfonos).
_DOTA_COLS = {"IDENTIDAD RED": "ejecutivo", "NOMBRE COMPLETO": "nombre", "PDV": "pdv"}


def _leer_dotacion(datos: bytes) -> pd.DataFrame:
    xl = pd.ExcelFile(io.BytesIO(datos))
    hoja = next((s for s in xl.sheet_names if "DOTAC" in fuentes.norm(s)), xl.sheet_names[0])
    raw = xl.parse(sheet_name=hoja, header=None, dtype=str)
    fila = next((i for i in range(min(10, len(raw)))
                 if any(fuentes.norm(v) == "IDENTIDAD RED" for v in raw.iloc[i].fillna(""))), None)
    if fila is None:
        raise ValueError("no encontré la columna IDENTIDAD RED. ¿Es la DOTACIÓN?")
    cab = [fuentes.norm(v).replace("°", "") for v in raw.iloc[fila].fillna("")]
    cols = {}
    for j, c in enumerate(cab):
        k = _DOTA_COLS.get(c)
        if k and k not in cols:
            cols[k] = j
    if len(cols) < 3:
        raise ValueError("a la dotación le falta IDENTIDAD RED, NOMBRE COMPLETO o PDV")
    d = raw.iloc[fila + 1:]
    out = pd.DataFrame({k: d.iloc[:, j].fillna("").astype(str).str.strip().values
                        for k, j in cols.items()})
    out["ejecutivo"] = out["ejecutivo"].str.upper()
    out = out[out["ejecutivo"].str.startswith("CMA_")].copy()
    out["pdv"] = out["pdv"].str.split(".").str[0]
    return out.drop_duplicates("ejecutivo").reset_index(drop=True)[["ejecutivo", "nombre", "pdv"]]


@st.cache_data(show_spinner=False, max_entries=4, ttl=6 * 3600)
def _vendedores_csv(ruta: str, mtime: float) -> pd.DataFrame:
    return pd.read_csv(ruta, dtype=str, keep_default_na=False)


def _vendedores() -> pd.DataFrame:
    if not VENDEDORES.exists():
        return pd.DataFrame(columns=["ejecutivo", "nombre", "pdv"])
    try:
        return _vendedores_csv(str(VENDEDORES), VENDEDORES.stat().st_mtime)
    except Exception:                                       # noqa: BLE001
        return pd.DataFrame(columns=["ejecutivo", "nombre", "pdv"])


def _codigo_de_vendedor() -> "callable":
    """
    El vendedor de Bsale («Gianna Figueroa») → su código de la dotación. Se
    cruza por palabras: todas las del nombre de Bsale tienen que estar en el de
    la dotación, y el cruce tiene que ser único (igual que en el panel).
    """
    v = _vendedores()
    candidatos = [(str(c), fuentes.norm(n)) for c, n in zip(v["ejecutivo"], v["nombre"]) if str(c)]
    memo: dict = {}

    def buscar(nombre: str):
        clave = fuentes.norm(nombre)
        if clave in memo:
            return memo[clave]
        palabras = set(clave.split())
        cod = None
        if palabras:
            exactos = [c for c, n in candidatos if n == clave]
            dentro = [c for c, n in candidatos if palabras <= set(n.split())]
            if len(set(exactos)) == 1:
                cod = exactos[0]
            elif len(set(dentro)) == 1:
                cod = dentro[0]
            elif len(palabras) >= 2:
                p = clave.split()
                par = {p[0], p[-1]}
                cerca = [c for c, n in candidatos if par <= set(n.split())]
                if len(set(cerca)) == 1:
                    cod = cerca[0]
        memo[clave] = cod
        return cod
    return buscar


def _ventas_bsale_sku(desde: dt.date) -> tuple[pd.DataFrame, int]:
    """Unidades de Bsale por tienda y SKU del día elegido; la tienda sale del vendedor."""
    vacio = pd.DataFrame(columns=["pdv", "sku", "vendido_hoy"])
    if not BSALE_DATOS.exists():
        return vacio, 0
    try:
        b = _bsale_guardado(str(BSALE_DATOS), BSALE_DATOS.stat().st_mtime)
    except Exception:                                       # noqa: BLE001
        return vacio, 0
    # solo lo vendido EL DÍA ELEGIDO: el stock de SAP ya descuenta lo de los
    # días anteriores, así que restarlo de nuevo lo contaría dos veces
    b = b[(b["fecha"].notna()) & (b["fecha"] == desde)]
    b = b[(b["eq_q"] != 0) | (b["acc_q"] != 0)]
    if b.empty:
        return vacio, 0
    buscar = _codigo_de_vendedor()
    v = _vendedores()
    pdv_de = {str(c): str(p).split(".")[0] for c, p in zip(v["ejecutivo"], v["pdv"])}
    # vendedores nuevos que no están en la dotación: la tienda que se les eligió a
    # mano en el panel (🎯 Meta del día, v517), si la hay
    a_mano = _bsale_tiendas()
    b = b.assign(pdv=b["vendedor"].map(lambda x: pdv_de.get(str(buscar(x) or ""), "")
                                       or a_mano.get(fuentes.norm(x), "")),
                 sku=b["sku"].map(_sku_txt), q=b["eq_q"] + b["acc_q"])
    b.loc[~b["pdv"].isin(set(TIENDAS["pdv"])), "pdv"] = ""
    sin_tienda = int((b["pdv"] == "").sum())
    b = b[b["pdv"] != ""]
    return (b.groupby(["pdv", "sku"], as_index=False)["q"].sum()
            .rename(columns={"q": "vendido_hoy"}), sin_tienda)


BSALE_TIENDAS = DATA_RAIZ / "bsale_tiendas.csv"   # del panel: vendedor de Bsale → tienda, a mano


def _bsale_tiendas() -> dict:
    try:
        d = pd.read_csv(BSALE_TIENDAS, dtype=str, keep_default_na=False)
        return {fuentes.norm(v): str(p).split(".")[0] for v, p in zip(d["vendedor"], d["pdv"])
                if str(p).strip()}
    except Exception:                                       # noqa: BLE001
        return {}


# ── bases EQUIPOS / ACCESORIOS del mes en curso ─────────────────────────────
def _bases_info() -> dict:
    try:
        return json.loads(BASES_INFO.read_text(encoding="utf-8"))
    except Exception:                                       # noqa: BLE001
        return {}


def _tomar_base(fuente: str, datos: bytes, nombre: str, cuando: pd.Timestamp | None) -> bool:
    """Guarda la base si es más nueva que la que había. Devuelve si cambió."""
    info = _bases_info()
    previa = _ts_utc(info.get(fuente, {}).get("fecha"))
    cuando = cuando or pd.Timestamp.now(tz="UTC")
    if previa is not None and previa >= cuando:
        return False
    (BASES_DIR / f"{fuente}.xlsx").write_bytes(datos)
    info[fuente] = {"fecha": cuando.isoformat(), "nombre": nombre}
    BASES_INFO.write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
    return True


def _salidas(hasta) -> pd.DataFrame:
    """Historial + bases del mes en curso (que mandan para su mes), sin duplicar retiros."""
    r_eq, r_acc = BASES_DIR / "equipos.xlsx", BASES_DIR / "accesorios.xlsx"
    base = _salidas_bases(str(r_eq) if r_eq.exists() else "", r_eq.stat().st_mtime if r_eq.exists() else 0,
                          str(r_acc) if r_acc.exists() else "", r_acc.stat().st_mtime if r_acc.exists() else 0,
                          str(hasta) if hasta is not None else "")
    hist = _hist_cargado()
    if not base.empty and not hist.empty:
        clave_b = set(zip(base["fuente"], base["fecha"].dt.strftime("%Y-%m")))
        hist = hist[[k not in clave_b for k in zip(hist["fuente"], hist["fecha"].dt.strftime("%Y-%m"))]]
    d = pd.concat([x for x in (hist, base) if not x.empty], ignore_index=True) \
        if not (hist.empty and base.empty) else hist
    if d.empty:
        return d
    d["fecha"] = pd.to_datetime(d["fecha"], errors="coerce")
    d["q"] = pd.to_numeric(d["q"], errors="coerce").fillna(0)
    tienda_ord = set(d.loc[d["canal"] == "Tienda", "orden"].dropna())
    d = d[~((d["canal"] == "Retiro") & d["orden"].isin(tienda_ord))]
    if hasta is not None:
        d = d[d["fecha"] <= pd.Timestamp(hasta)]
    return d


def _tomar_bsale(datos: bytes, nombre: str, cuando: pd.Timestamp | None) -> bool:
    """Un Detalle de ventas de Bsale: se queda si es más nuevo que el guardado."""
    previa = _ts_utc(_info_bsale().get("subido"))
    cuando = cuando or pd.Timestamp.now(tz="UTC")
    if previa is not None and previa >= cuando:
        return False
    ok, _ = _guardar_bsale(datos, nombre)
    if ok:
        info = _info_bsale()
        info["subido"] = _chile_txt(cuando)
        BSALE_INFO.write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
    return ok


# ---------------------------------------------------------------------------
# ☁️ Google Drive: leer la carpeta del panel y guardar el respaldo propio
# ---------------------------------------------------------------------------
DRIVE_CARPETA = "1-panel CTF datos"
DRIVE_DIR = DATA_RAIZ / "_drive"
DRIVE_MANIF = DRIVE_DIR / "manifiesto.json"
DRIVE_CADA_SEG = 300                    # como mucho una revisión cada 5 minutos
DRIVE_MAX_MB = 40                       # archivos más grandes no se bajan
RESPALDO_NOMBRE = "respaldo_stock.zip"  # el de esta app (lo crea Elsa una vez)
RESPALDO_PANEL = "respaldo_panel.zip"   # el del panel: solo se lee
_RESP_ARCH = ("bsale_dia.csv", "bsale_dia.json", "historial_salidas.csv", "vendedores.csv",
              "bsale_tiendas.csv")
EXT_DATOS = (".xlsx", ".xlsm", ".xls", ".html", ".htm")


def _drive_manif() -> dict:
    try:
        return json.loads(DRIVE_MANIF.read_text(encoding="utf-8"))
    except Exception:                                       # noqa: BLE001
        return {}


def _manif_guardar(manif: dict) -> None:
    DRIVE_DIR.mkdir(parents=True, exist_ok=True)
    DRIVE_MANIF.write_text(json.dumps(manif, ensure_ascii=False), encoding="utf-8")


def _local_vacio() -> bool:
    return not any(STOCK_DIR.glob("stock_*.csv")) and not HIST_ARCHIVO.exists()


def _respaldo_zip() -> bytes:
    buf = io.BytesIO()
    with _zipfile.ZipFile(buf, "w", _zipfile.ZIP_DEFLATED) as z:
        for n in _RESP_ARCH:
            if (DATA_RAIZ / n).exists():
                z.write(DATA_RAIZ / n, n)
        for p in sorted(STOCK_DIR.glob("stock_*.csv")):
            z.write(p, f"stock/{p.name}")
    return buf.getvalue()


def _poner_fecha(ruta: Path, info: _zipfile.ZipInfo) -> None:
    """La fecha del archivo = la que trae dentro del zip (así se sabe cuál es más nuevo)."""
    try:
        import os as _os
        t = dt.datetime(*info.date_time).replace(tzinfo=dt.timezone.utc).timestamp()
        _os.utime(ruta, (t, t))
    except Exception:                                       # noqa: BLE001
        pass


def _respaldo_restaurar(datos: bytes) -> int:
    """Después de un reinicio: vuelve a poner lo que esta app había guardado."""
    n = 0
    with _zipfile.ZipFile(io.BytesIO(datos)) as z:
        for info in z.infolist():
            base = Path(info.filename).name
            if info.filename.startswith("stock/") and re.fullmatch(r"stock_\d{4}-\d{2}-\d{2}\.csv", base):
                destino = STOCK_DIR / base
            elif base in _RESP_ARCH:
                destino = DATA_RAIZ / base
            else:
                continue
            destino.write_bytes(z.read(info))
            _poner_fecha(destino, info)
            n += 1
    return n


def _desde_respaldo_panel(datos: bytes) -> bool:
    """
    Lo que el panel ya tenía (respaldo_panel.zip), sin pisar lo de esta app:
    días de stock que no estén acá, el historial si acá no hay, el Bsale del
    día y las bases EQUIPOS/ACCESORIOS subidas desde el panel si son más nuevas.
    """
    cambio = False
    with _zipfile.ZipFile(io.BytesIO(datos)) as z:
        nombres = {i.filename: i for i in z.infolist()}
        for nombre, info in nombres.items():
            base = Path(nombre).name
            if nombre.startswith("stock/") and re.fullmatch(r"stock_\d{4}-\d{2}-\d{2}\.csv", base) \
                    and not (STOCK_DIR / base).exists():
                (STOCK_DIR / base).write_bytes(z.read(info))
                _poner_fecha(STOCK_DIR / base, info)
                cambio = True
        if "historial_salidas.csv" in nombres and not HIST_ARCHIVO.exists():
            HIST_ARCHIVO.write_bytes(z.read("historial_salidas.csv"))
            cambio = True
        if "bsale_dia.csv" in nombres and "bsale_dia.json" in nombres:
            try:
                info_p = json.loads(z.read("bsale_dia.json"))
                t_p, t_l = _ts_utc(info_p.get("subido")), _ts_utc(_info_bsale().get("subido"))
                if t_p is not None and (t_l is None or t_p > t_l):
                    BSALE_DATOS.write_bytes(z.read("bsale_dia.csv"))
                    BSALE_INFO.write_bytes(z.read("bsale_dia.json"))
                    cambio = True
            except Exception:                               # noqa: BLE001
                pass
        if "bsale_tiendas.csv" in nombres:
            nuevo = z.read("bsale_tiendas.csv")
            if not BSALE_TIENDAS.exists() or BSALE_TIENDAS.read_bytes() != nuevo:
                BSALE_TIENDAS.write_bytes(nuevo)
                cambio = True
        if "subidos_panel.json" in nombres:
            try:
                reg = json.loads(z.read("subidos_panel.json"))
            except Exception:                               # noqa: BLE001
                reg = {}
            for fuente in ("equipos", "accesorios"):
                if reg.get(fuente) and f"bases/{fuente}.xlsx" in nombres:
                    if _tomar_base(fuente, z.read(f"bases/{fuente}.xlsx"), f"{fuente} (subida en el panel)",
                                   _ts_utc(reg[fuente])):
                        cambio = True
    return cambio


def _olfatear(datos: bytes) -> str:
    """Qué es un archivo, mirando solo sus primeras filas."""
    try:
        x = pd.read_excel(io.BytesIO(datos), header=None, nrows=15, dtype=str)
    except Exception:                                       # noqa: BLE001
        return "otro"
    celdas = {fuentes.norm(v) for v in x.fillna("").values.ravel() if str(v).strip()}
    if "ALMACEN" in celdas:
        return "stock"
    if "ID DEL PDV" in celdas and "SKU" in celdas:
        return "base"
    if "IDENTIDAD RED" in celdas:
        return "dotacion"
    return "otro"


def respaldar_en_drive() -> str:
    """Sube al Drive (respaldo_stock.zip) lo de esta app. '' si salió bien, o el problema."""
    if not _drive_credenciales():
        return "la app no tiene acceso al Drive"
    try:
        ses = _drive_sesion()
        manif = _drive_manif()
        fid = manif.get("_respaldo_id")
        if not fid:
            r = ses.get(DRIVE_API, params={
                "q": f"name = '{RESPALDO_NOMBRE}' and trashed = false", "fields": "files(id)",
                "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"}, timeout=30)
            r.raise_for_status()
            hallados = r.json().get("files", [])
            if not hallados:
                return (f"falta el archivo «{RESPALDO_NOMBRE}» en la carpeta del Drive "
                        "(hay que crearlo una vez)")
            fid = hallados[0]["id"]
        r = ses.patch(f"https://www.googleapis.com/upload/drive/v3/files/{fid}",
                      params={"uploadType": "media", "supportsAllDrives": "true"},
                      data=_respaldo_zip(), headers={"Content-Type": "application/zip"}, timeout=120)
        if r.status_code in (401, 403):
            return "la cuenta de servicio no puede escribir en el Drive (tiene que ser Editor de la carpeta)"
        r.raise_for_status()
        manif["_respaldo_id"] = fid
        manif.setdefault(fid, {})["firma"] = f'{fid}:{r.json().get("modifiedTime", "")}'
        _manif_guardar(manif)
        return ""
    except Exception as e:                                  # noqa: BLE001
        return str(e)[:200]


def sincronizar_drive(forzar: bool = False) -> dict | None:
    """Trae de la carpeta del Drive lo que sea nuevo. None si no está configurado."""
    if not _drive_credenciales():
        return None
    manif = _drive_manif()
    arranque = not manif.get("_revisado")
    if not forzar and not arranque and time.time() - manif.get("_revisado", 0) < DRIVE_CADA_SEG:
        return manif.get("_estado")
    estado = {"revisado": pd.Timestamp.now(tz="UTC").tz_convert(ZONA_CHILE).strftime("%d/%m %H:%M"), "nuevos": 0, "archivos": 0,
              "error": ""}
    migrar = False
    try:
        ses = _drive_sesion()
        archivos = _drive_listar(ses)
        estado["archivos"] = len(archivos)

        def bajar(a) -> bytes:
            r = ses.get(f'{DRIVE_API}/{a["id"]}', params={"alt": "media", "supportsAllDrives": "true"},
                        timeout=180)
            r.raise_for_status()
            return r.content

        def nombre_de(a):
            return a["name"].strip().lower()

        cambio = False
        # 1) el respaldo propio (solo al arrancar con el disco vacío)
        mio = next((a for a in archivos if nombre_de(a) == RESPALDO_NOMBRE), None)
        if mio:
            manif["_respaldo_id"] = mio["id"]
            firma = f'{mio["id"]}:{mio.get("modifiedTime", "")}'
            if _local_vacio():
                if int(mio.get("size") or 0) > 22:
                    if _respaldo_restaurar(bajar(mio)):
                        cambio = True
                        estado["nuevos"] += 1
                else:
                    migrar = True               # respaldo propio vacío: primera vez
            manif[mio["id"]] = {"firma": firma, "destino": "respaldo", "nombre": mio["name"]}
        # 2) el respaldo del panel (cuando cambia)
        pan = next((a for a in archivos if nombre_de(a) == RESPALDO_PANEL), None)
        if pan:
            firma = f'{pan["id"]}:{pan.get("modifiedTime", "")}'
            if manif.get(pan["id"], {}).get("firma") != firma and int(pan.get("size") or 0) > 22:
                if _desde_respaldo_panel(bajar(pan)):
                    cambio = True
                    estado["nuevos"] += 1
                manif[pan["id"]] = {"firma": firma, "destino": "panel", "nombre": pan["name"]}
        # 3) los archivos sueltos, del más viejo al más nuevo (el más nuevo manda)
        sueltos = sorted([a for a in archivos if nombre_de(a).endswith(EXT_DATOS)],
                         key=lambda a: a.get("modifiedTime", ""))
        stock_nuevo = []
        for a in sueltos:
            firma = f'{a["id"]}:{a.get("modifiedTime", "")}'
            if manif.get(a["id"], {}).get("firma") == firma:
                continue
            if int(a.get("size") or 0) > DRIVE_MAX_MB * 1024 * 1024:
                manif[a["id"]] = {"firma": firma, "destino": "grande", "nombre": a["name"]}
                continue
            cuando = _ts_utc(a.get("modifiedTime"))
            datos = bajar(a)
            tipo = _olfatear(datos)
            destino = "ignorado"
            try:
                if tipo == "stock":
                    _, fecha = _leer_stock(datos, a["name"])
                    fecha = fecha or _hoy_chile()
                    csv = STOCK_DIR / f"stock_{fecha:%Y-%m-%d}.csv"
                    # si ese día ya se cargó algo más nuevo en la app, manda lo de la app
                    if not csv.exists() or cuando is None or cuando.timestamp() > csv.stat().st_mtime:
                        stock_nuevo.append(_ArchivoDrive(a["name"], datos))
                    destino = "stock"
                elif tipo == "base":
                    x = _hist_leer(datos, a["name"])
                    f_ = x["fuente"].iloc[0] if not x.empty else ""
                    if f_ in ("equipos", "accesorios"):
                        if _tomar_base(f_, datos, a["name"] + " (Drive)", cuando):
                            cambio = True
                        destino = f_
                elif tipo == "dotacion" or "DOTAC" in fuentes.norm(a["name"]):
                    v = _leer_dotacion(datos)
                    if not v.empty:
                        v.to_csv(VENDEDORES, index=False, encoding="utf-8")
                        cambio, destino = True, "dotacion"
                elif nombre_de(a).endswith((".xls", ".html", ".htm", ".xlsx")):
                    if _tomar_bsale(datos, a["name"], cuando):
                        cambio, destino = True, "bsale"
                    elif _info_bsale():
                        destino = "bsale?"
            except Exception:                               # noqa: BLE001
                destino = "ignorado"
            manif[a["id"]] = {"firma": firma, "destino": destino, "nombre": a["name"]}
            if destino not in ("ignorado", "bsale?"):
                estado["nuevos"] += 1
        if stock_nuevo:
            _guardar_stock(stock_nuevo)
            cambio = True
        if cambio:
            st.cache_data.clear()
    except Exception as e:                                  # noqa: BLE001
        estado["error"] = str(e)[:300]
        migrar = False
    manif["_revisado"] = time.time()
    manif["_estado"] = estado
    _manif_guardar(manif)
    if migrar and not _local_vacio():
        # primera vez: lo que vino del panel queda también en el respaldo propio
        problema = respaldar_en_drive()
        if problema:
            estado["error"] = f"no pude guardar el respaldo propio: {problema}"
            manif = _drive_manif()
            manif["_estado"] = estado
            _manif_guardar(manif)
    return estado


def aviso_drive(estado) -> None:
    c1 = st.container()                  # (se quitó el botón «Traer de Drive»: se revisa sola)
    with c1:
        if estado is None:
            md('<div class="seccion-sub">☁️ Sin conexión al Drive (falta <b>gcp_json</b> en '
               'Secrets): lo que se suba acá se pierde si la app se reinicia.</div>')
        elif estado.get("error"):
            md(f'<div class="seccion-sub t-mal">☁️ No pude leer la carpeta del Drive: '
               f'{h(estado["error"])}</div>')
        else:
            md(f'<div class="seccion-sub">☁️ Carpeta del Drive <b>«{h(_secreto("drive_carpeta") or DRIVE_CARPETA)}»</b>: '
               f'{estado.get("archivos", 0)} archivos · revisada {h(estado.get("revisado", ""))}'
               + (f' · <b>{estado["nuevos"]} nuevos</b>' if estado.get("nuevos") else "")
               + '. Se revisa sola cada 5 minutos.</div>')


def _bloque_bsale() -> None:
    """Ya no se muestra: Bsale y dotación llegan solos desde el Drive y el respaldo del panel."""
    return


def _memoria_mb() -> int:
    try:
        for linea in Path("/proc/self/status").read_text().splitlines():
            if linea.startswith("VmRSS:"):
                return int(linea.split()[1]) // 1024
    except Exception:                                       # noqa: BLE001
        pass
    return 0


# ---------------------------------------------------------------------------
# La página
# ---------------------------------------------------------------------------
_cab, _btn = st.columns([6, 1.1])
with _cab:
    ui.cabecera(BASE / "assets" / "logo.png", "Stock CTF",
                "Stock de las 8 tiendas")
with _btn:
    md('<div style="height:1.1rem"></div>')
    tema.interruptor()
aviso_drive(sincronizar_drive())
vista_stock()
desplegable_historial()

_pie1, _pie2 = st.columns([6, 1.3])
with _pie1:
    md(f'<div class="seccion-sub" style="font-size:.72rem;opacity:.7">Stock CTF · versión {h(VERSION)}'
       + (f' · memoria {_memoria_mb()} MB' if _memoria_mb() else "") + '</div>')
with _pie2:
    if st.button("🧹 Liberar memoria", key="liberar"):
        st.cache_data.clear()
        _gc.collect()
        st.rerun()
_gc.collect()
