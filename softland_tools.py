"""Herramientas de lectura masiva de Softland."""
import asyncio
from datetime import date

def register(mcp, db):
    async def query(tool, proc, params, args):
        try:
            rows = await asyncio.to_thread(db.call_procedure, proc, *args)
        except Exception as exc:
            db.audit(tool, params, None, False, type(exc).__name__)
            return {"error": "Error de consulta; revisar audit.log"}
        db.audit(tool, params, len(rows), True)
        total = rows[0].get("_total_registros", 0) if rows else 0
        for row in rows:
            row.pop("_total_registros", None)
        return {"total": total, "devueltos": len(rows), "datos": rows}

    def validate(pagina, tamano, desde=None, hasta=None):
        if not 1 <= pagina or not 1 <= tamano <= 200:
            return "Paginación inválida"
        try:
            if desde: date.fromisoformat(desde)
            if hasta: date.fromisoformat(hasta)
        except ValueError:
            return "Fechas inválidas: usar YYYY-MM-DD"
        return None

    @mcp.tool()
    async def listar_clientes(pagina: int = 1, tamano: int = 100, correo: str | None = None, nombre: str | None = None) -> dict:
        """Devuelve todas las columnas de negocio de clientes; permite buscar correos compartidos."""
        if error := validate(pagina, tamano):
            return {"error": error}
        return await query("listar_clientes", "andi.sp_listar_clientes", {"pagina": pagina, "tamano": tamano, "filtro_correo": bool(correo)}, [pagina, tamano, correo, nombre])

    @mcp.tool()
    async def listar_facturas(pagina: int = 1, tamano: int = 100, desde: str | None = None, hasta: str | None = None, cliente: str | None = None) -> dict:
        """Facturas de los últimos dos años; fechas opcionales YYYY-MM-DD."""
        if error := validate(pagina, tamano, desde, hasta):
            return {"error": error}
        return await query("listar_facturas", "andi.sp_listar_facturas", {"pagina": pagina, "tamano": tamano, "desde": desde, "hasta": hasta, "cliente": cliente}, [pagina, tamano, desde, hasta, cliente])

    @mcp.tool()
    async def listar_pedidos(pagina: int = 1, tamano: int = 100, desde: str | None = None, hasta: str | None = None, cliente: str | None = None) -> dict:
        """Pedidos de los últimos dos años; son antecedentes comerciales, no facturas."""
        if error := validate(pagina, tamano, desde, hasta):
            return {"error": error}
        return await query("listar_pedidos", "andi.sp_listar_pedidos", {"pagina": pagina, "tamano": tamano, "desde": desde, "hasta": hasta, "cliente": cliente}, [pagina, tamano, desde, hasta, cliente])

    @mcp.tool()
    async def factura_lineas(tipo_documento: str, factura: str) -> dict:
        """Líneas de una factura de los últimos dos años."""
        if not tipo_documento or not factura:
            return {"error": "tipo_documento y factura requeridos"}
        return await query("factura_lineas", "andi.sp_factura_lineas", {"tipo_documento": tipo_documento, "factura": factura}, [tipo_documento, factura])

    @mcp.tool()
    async def pedido_lineas(pedido: str) -> dict:
        """Líneas de un pedido de los últimos dos años."""
        if not pedido:
            return {"error": "pedido requerido"}
        return await query("pedido_lineas", "andi.sp_pedido_lineas", {"pedido": pedido}, [pedido])
