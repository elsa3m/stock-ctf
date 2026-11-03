"""
Componentes visuales del panel.

Todo lo que se dibuja pasa por aquí, así el estilo queda parejo en las seis vistas.
Regla que se respeta en todos los componentes: **el color nunca informa solo**.
Cada semáforo lleva una forma (▲ ■ ▼) y el número al lado.
"""
from __future__ import annotations

import base64
import html as _html
import math
from pathlib import Path

import pandas as pd
import streamlit as st

from . import tema


# ---------------------------------------------------------------------------
# formatos (convención chilena: coma decimal, punto de miles)
# ---------------------------------------------------------------------------
def h(x) -> str:
    return _html.escape(str(x))


def md(s: str) -> None:
    st.markdown(s, unsafe_allow_html=True)


def num(x, dec=0, vacio="—") -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return vacio
    s = f"{x:,.{dec}f}"
    return s.replace(",", "·").replace(".", ",").replace("·", ".")


def pct(x, dec=1, vacio="—") -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return vacio
    return f"{x * 100:,.{dec}f}%".replace(",", "·").replace(".", ",").replace("·", ".")


def clp(x, vacio="—") -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return vacio
    return "$" + f"{round(x):,.0f}".replace(",", ".")


def clp_corto(x, vacio="—") -> str:
    """Pesos en corto, para cuando no cabe la cifra entera: $628,9 M."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return vacio
    if abs(x) >= 1_000_000:
        return "$" + f"{x / 1_000_000:.1f}".replace(".", ",") + " M"
    return clp(x)


def fecha(f, vacio="—") -> str:
    # ojo con NaT: es «verdadero» para un if, pero revienta al formatearlo, y
    # llega cada vez que una solicitud todavía no tiene fecha de instalación
    if f is None or f is pd.NaT or (isinstance(f, float) and math.isnan(f)):
        return vacio
    try:
        return f.strftime("%d/%m/%Y")
    except (ValueError, AttributeError):
        return vacio


def pct_topado(x, tope=1.5, dec=1) -> str:
    """Sobre el tope muestra '> 150%': una proyección de 400% no informa, confunde."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    return f"> {pct(tope, 0)}" if x > tope else pct(x, dec)


# ---------------------------------------------------------------------------
# piezas
# ---------------------------------------------------------------------------
def chip(estado: str, texto: str = "") -> str:
    """Etiqueta de estado: color + forma + texto. Nunca solo color."""
    e = tema.ESTADO.get(estado, tema.ESTADO["nulo"])
    return f'<span class="chip {estado}"><span class="f">{e["forma"]}</span>{h(texto or e["texto"])}</span>'


def tarjeta(cuerpo: str, plana: bool = False) -> None:
    md(f'<div class="tarjeta{" plana" if plana else ""}">{cuerpo}</div>')


def metrica(rotulo: str, valor: str, pie: str = "", estado: str = "",
            icono: str = "", ancho_total: bool = False) -> None:
    """Una cifra grande con su rótulo y una línea de contexto."""
    color = f" t-{estado}" if estado in ("bien", "medio", "mal") else ""
    marca = '<div class="ancho-total"></div>' if ancho_total else ""
    md(f'<div class="tarjeta metrica">{marca}'
       f'<div class="rotulo">{icono} {h(rotulo)}</div>'
       f'<div class="valor{color}">{valor}</div>'
       f'{f"<div class=pie>{pie}</div>" if pie else ""}</div>')


def seccion(titulo: str, sub: str = "") -> None:
    md(f'<div style="margin:1.1rem 0 .5rem"><div class="seccion">{h(titulo)}</div>'
       f'{f"<div class=seccion-sub>{h(sub)}</div>" if sub else ""}</div>')


def barra(cumplimiento: float, color: str, corte: float | None = None) -> str:
    """Barra de avance con una marca vertical en el avance esperado del mes."""
    ancho = max(0.0, min(1.0, cumplimiento or 0.0)) * 100
    marca = ""
    if corte and 0 < corte <= 1:
        marca = (f'<div class="corte" style="left:{min(99, corte * 100):.1f}%" '
                 f'title="Avance esperado del mes: {pct(corte)}"></div>')
    return f'<div class="barra"><div class="relleno" style="width:{ancho:.1f}%;background:{color}"></div>{marca}</div>'


def producto(nombre: str, real, meta, cump, color: str, corte: float,
             detalles=(), plata: bool = False) -> str:
    """
    Tarjeta de un producto: cuánto lleva, de cuánto, y si va al día.

    `detalles` son las líneas que van abajo —cumplimiento, conversión, peso—,
    una debajo de la otra. `plata` muestra las cifras en pesos en vez de
    unidades, para equipos y accesorios.
    """
    estado = tema.estado_de(cump, corte)
    cifra = clp if plata else num
    falta = max(0, math.ceil((meta or 0) - (real or 0) - 1e-9))
    lineas = "".join(f'<div>{d}</div>' for d in detalles if d)
    # en pesos la meta no cabe al lado de la cifra: baja a las líneas de detalle
    encabezado = (f'<span class="cifra">{cifra(real)}</span>' if plata else
                  f'<span class="cifra">{cifra(real)}</span> '
                  f'<span class="de">de {cifra(meta)}</span>')
    falta_txt = clp_corto(falta) if plata else num(falta)
    return (
        f'<div class="producto">'
        f'<div class="titulo"><span class="punto" style="background:{color}"></span>{h(nombre)}</div>'
        f'<div style="margin:.35rem 0 .1rem">{encabezado}</div>'
        f'{barra(cump, color, corte)}'
        f'<div style="margin:.15rem 0 .3rem">{chip(estado, "al día" if estado == "bien" else f"faltan {falta_txt}")}</div>'
        f'<div class="detalle">{lineas}</div>'
        f'</div>'
    )


def tabla(columnas: list[str], filas: list[list[str]], izq: int = 1,
          total: list[str] | None = None, escapar: bool = True) -> str:
    """Tabla con cabecera fija y primera columna fija al desplazarse."""
    def clase(i):
        c = ["izq"] if i < izq else []
        if i == 0:
            c.append("fija")
        return " ".join(c)

    th = "".join(f'<th class="{clase(i)}">{h(c) if escapar else c}</th>' for i, c in enumerate(columnas))
    tr = "".join("<tr>" + "".join(f'<td class="{clase(i)}">{c}</td>' for i, c in enumerate(f)) + "</tr>"
                 for f in filas)
    if total:
        tr += '<tr class="total">' + "".join(f'<td class="{clase(i)}">{c}</td>' for i, c in enumerate(total)) + "</tr>"
    return f'<div class="tabla-caja"><table class="tabla"><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></div>'


def mapa(columnas: list, filas: list) -> str:
    """
    Tabla-mapa de calor: una columna por indicador, el fondo de cada celda
    teñido según su estado. Entra mucha más información en el mismo ancho y el
    patrón se ve de una mirada.

    `columnas`: lista de (título, subtítulo) para la cabecera.
    `filas`: lista de (etiqueta_html, [(texto, estado), …]).
    """
    th = f'<th class="izq fija">{columnas[0][0]}</th>'
    for titulo, sub in columnas[1:]:
        # el subtítulo puede venir en varias líneas separadas por "\n": así una
        # columna dice "Conv." arriba, "móvil" debajo y la meta al pie, sin
        # tener que ensancharla para que quepa todo en una sola línea
        lineas = "".join(
            f'<br><span class="t-tenue" style="font-weight:600">{h(p)}</span>'
            for p in str(sub).split("\n") if p)
        th += f'<th>{h(titulo)}{lineas}</th>'
    tr = ""
    for etiqueta, celdas in filas:
        tr += f'<tr><td class="izq fija">{etiqueta}</td>'
        for texto, estado in celdas:
            tr += f'<td class="hm {estado}">{texto}</td>'
        tr += "</tr>"
    return (f'<div class="tabla-caja"><table class="tabla mapa">'
            f'<thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></div>')


def celda_estado(valor, referencia, dec=1) -> str:
    """Celda de tabla con forma + número, legible sin depender del color."""
    e = tema.estado_de(valor, referencia)
    return f'<span class="t-{e}"><b>{tema.ESTADO[e]["forma"]}</b> {pct(valor, dec)}</span>'


def logo_html(ruta: Path) -> str:
    if not ruta.exists():
        return ""
    b64 = base64.b64encode(ruta.read_bytes()).decode()
    return f'<div class="marca"><img src="data:image/png;base64,{b64}" alt="CTF Tecnología"></div>'


def cabecera(ruta_logo: Path, titulo: str, subtitulo: str) -> None:
    md(f'<div class="cabecera">{logo_html(ruta_logo)}'
       f'<div><h1>{h(titulo)}</h1><div class="sub">{h(subtitulo)}</div></div></div>')


def leyenda_semaforo() -> str:
    return (f'<div class="seccion-sub">{chip("bien", "al día o mejor")} '
            f'{chip("medio", "entre 80% y 100% del corte")} {chip("mal", "bajo el 80% del corte")} '
            f'<span class="t-tenue">· cada estado lleva su forma, no solo el color</span></div>')
