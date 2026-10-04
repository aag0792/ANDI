# ANDI Gateway v0.1 (solo lectura)

## 1. Base de datos (en una COPIA de Softland primero)
1. Abre `01_usuario_y_procedimiento.sql` en SSMS.
2. Ajusta `[SOFTLAND]`, `[ASISTENTE]` y las columnas de `CLIENTE`. La contraseña real debe existir únicamente en `.env` local y nunca en Git.
3. Ejecútalo y corre las pruebas del final: ambos procedimientos deben funcionar como andi_gateway; SELECT directo y suplantación de andi_reader deben fallar.

## 2. Instalar el driver ODBC
Instala "ODBC Driver 18 for SQL Server" (Microsoft) si no lo tienes.
Verifica: `Get-OdbcDriver | Select Name`

## 3. Copiar el proyecto a C:\ANDI y preparar el entorno
```powershell
cd C:\ANDI
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip --version        # debe apuntar a C:\ANDI\.venv\...
pip install -r requirements.txt
# Si ya existe conexion.env, úsalo para crear .env
copy .\conexion.env .\.env
# o, si prefieres partir de la plantilla:
# copy .\env.example .\.env
python -c "import secrets; print(secrets.token_urlsafe(48))"   # para GATEWAY_TOKEN
```

## 4. Arrancar
```powershell
cd C:\ANDI
\.\.venv\Scripts\python.exe .\main.py
```
Prueba: http://127.0.0.1:8000/health

> El proyecto acepta tanto `.env` como `conexion.env`, pero el arranque real ocurre desde `main.py` en la raíz del repositorio.

## 5. Probar la herramienta (sin IA todavía)
```powershell
npx @modelcontextprotocol/inspector
```
Transporte: Streamable HTTP · URL: `http://127.0.0.1:8000/mcp`
Header: `Authorization: Bearer <tu GATEWAY_TOKEN>` · Tools > buscar_cliente.

O con Claude Code (desde la misma máquina):
```powershell
claude mcp add --transport http andi http://127.0.0.1:8000/mcp --header "Authorization: Bearer <TOKEN>"
```

## Revisar la auditoría
`C:\ANDI\logs\audit.log` (una línea JSON por consulta; no guarda los datos devueltos).

## Pendiente para la fase siguiente
- Acceso desde iPhone/Mac vía claude.ai: requiere URL HTTPS pública (túnel) y
  autenticación compatible con conectores (OAuth), no solo un token fijo.
- Módulo de aprobación (`/approval`) antes de cualquier herramienta que escriba o envíe.
- Ejecutar como servicio de Windows (NSSM o similar) con cuenta sin privilegios.

## Seguridad y Cliente 360

La conexión usa `andi_gateway`, con EXECUTE únicamente sobre los procedimientos
autorizados. Los dos procedimientos se ejecutan como `andi_reader`, un usuario
WITHOUT LOGIN con SELECT sobre CLIENTE, DOCUMENTOS_CC, FACTURA, FACTURA_LINEA y
CENTRO_COSTO del esquema ASISTENTE. No se otorga db_datareader, SELECT de esquema
ni IMPERSONATE al gateway. Revisar permisos y roles preexistentes antes de aplicar
el script; los GRANT no eliminan permisos heredados de instalaciones anteriores.

Cliente 360 conserva ficha, resumen, cuentas por cobrar e historial de compras.
En Inspector, ejecutar tools/list y luego cliente_360 con codigo_cliente de un
cliente real. El endpoint es exactamente `/mcp` (por ejemplo,
`http://127.0.0.1:1992/mcp` si GATEWAY_PORT=1992), sin redirección requerida;
`/mcp/mcp` deja de ser la ruta de conexión. Reiniciar el gateway y actualizar
los clientes que usaban la ruta duplicada.

Las pruebas locales usan datos simulados y no sustituyen la validación de
permisos en SQL Server. Para ejecutar la suite, instalar pytest y configurar
SQL_DATABASE, SQL_USER, SQL_PASSWORD y GATEWAY_TOKEN (valores ficticios bastan
para las pruebas), además de LOG_DIR apuntando a un directorio local de pruebas:
`python -m pytest -q`.

Se requiere MCP >=1.30 para la ruta directa sin redirección. Actualizar las
dependencias con pip install -r requirements.txt antes de reiniciar.

## Acceso remoto autenticado

Para conectar ChatGPT al gateway por HTTPS, seguir [OAuth con Microsoft
Entra](docs/oauth-entra.md). El modo token sigue disponible para el flujo local;
el modo entra exige un token de Microsoft y restringe usuarios y clientes.
El directorio assets sirve únicamente el logo, nunca archivos del proyecto.

## Cotizaciones PDF AND

`generar_cotizacion` conserva sus argumentos y su integración MCP. Se agregan
`lines` (`quantity`, `description`, `unit_price`), `currency` (`USD`/`CRC`),
`tax_rate`, `quote_number`, `quote_date` (`YYYY-MM-DD`), `codigo_cliente`,
`client`, `requester`, `payment_method`, `observations`, `project_reference`,
`company`, `banks` y `terms`. Las tasas son fracciones: IVA de 13% = `0.13`,
sin IVA = `0`; descuento de 10% = `discount_percent=0.10`.

Con líneas explícitas, los precios ya son comerciales: no se agrega el margen
de la estimación. El subtotal suma los importes redondeados por línea; el
 descuento se aplica antes del IVA, con redondeo decimal a dos posiciones.
Sin líneas se conserva la estimación con margen/descuento; el PDF, respuesta
comercial e historial registran el mismo total. El cronograma sigue siendo una
estimación de proyecto, no se deduce de las líneas comerciales.

`codigo_cliente` consulta `cliente_360` por los procedimientos existentes; no
escribe en Softland. `client` completa o reemplaza campos de la ficha, usando
`name`, `address`, `phone`, `email`, `payment_method` o las columnas originales
`NOMBRE`, `DIRECCION`, `TELEFONO1`, `E_MAIL`, `CONDICION_PAGO`. Una condición de
pago recuperada de Softland puede ser un código: usar `payment_method` para su
texto comercial. No se asignan números oficiales: sin `quote_number` el PDF
muestra `BORRADOR`. La fecha predeterminada usa Costa Rica.

El diseño carta de dos páginas reproduce el logo, colores, datos, tabla,
totales, observaciones, condiciones/aprobación de los tres ejemplos. Las cuentas bancarias se omiten
por defecto; solo se incluyen si se proporcionan explícitamente en `banks`.
No se guardan cuentas bancarias ni datos de contacto de clientes en el código.
El estándar editable reside en `assets/quote-standard.json` y el logo extraído
del PDF de referencia en `assets/quote-logo.png`. Se puede reemplazar company,
banks o terms por cotización. Los textos se ajustan dentro de las celdas; si el
contenido supera dos páginas se devuelve un error antes de escribir el PDF,
sin truncar texto ni guardar historial.

Ejemplo de campos adicionales para Barly:

```json
{
  "lines": [{"quantity": 2, "description": "Consultoría ERP - Base de Datos", "unit_price": 60}],
  "currency": "USD", "tax_rate": 0.13,
  "quote_number": "P02435", "quote_date": "2026-09-16",
  "payment_method": "8 Dias"
}
```

Las pruebas de cotizaciones están en `tests/test_quotation_pdf.py` y las
regresiones MCP en `tests/test_gateway.py`. No requieren acceso a Softland.
