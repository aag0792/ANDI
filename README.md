# ANDI Gateway v0.1 (solo lectura)

## 1. Base de datos (en una COPIA de Softland primero)
1. Abre `sql/01_usuario_y_procedimiento.sql` en SSMS.
2. Ajusta `[SOFTLAND_DB]`, `[EMPRESA]`, las columnas de `CLIENTE` y la clave.
3. Ejecútalo y corre las dos pruebas del final (la segunda DEBE fallar).

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
Prueba: http://127.0.0.1:1992/health

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
