# Stock CTF

App de Streamlit solo de stock (salió de la pestaña 📦 Stock del Panel CTF).

- Stock de cada tienda (Reporte Stock Disponible de SAP) menos lo vendido hoy en Bsale.
- Rotación con el historial de salidas (tienda, retiro en tienda y delivery), últimos 90 días.
- Ventas por mes, detalle por producto, Excel y PDF.

## Qué se sube a GitHub (repo elsa3m/stock-ctf)
`app.py`, `requirements.txt`, `README.md`, la carpeta `core` y la carpeta `assets`.
La carpeta `_armado` NO se sube (son las piezas con que se armó app.py).

## Secrets en Streamlit
```
gcp_json = '''{ ...la misma cuenta de servicio del panel... }'''
clave_ctf = "..."
```
La clave se pide una vez y la app queda abierta mientras la pestaña siga abierta.

## Datos (Google Drive)
- Lee la carpeta «1-panel CTF datos»: reportes de stock, Detalle de ventas de Bsale,
  DOTACIÓN y bases EQUIPOS/ACCESORIOS del mes. Se revisa sola cada 5 minutos.
- Lee (sin tocarlo) `respaldo_panel.zip`: stock, historial y Bsale que ya tenía el panel.
- Guarda lo propio en `respaldo_stock.zip` (misma carpeta).
