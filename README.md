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
