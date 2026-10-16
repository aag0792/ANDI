# Ampliación MCP Softland — consultas de solo lectura

## Hallazgos del código actual
- `main.py` publica herramientas FastMCP.
- `db.py` solo ejecuta procedimientos almacenados parametrizados; **no admite SQL arbitrario**.
- El esquema de negocio acordado es `ASISTENTE`. No confundirlo con el esquema `andi` de los procedimientos existentes.
- Softland no diferencia pedidos y cotizaciones: consultar ambos como historial de pedidos, sin inventar estados.

## Contrato propuesto de herramientas
1. `listar_clientes(pagina=1, tamano_pagina=100, correo=None, nombre=None)`: todos los campos de `ASISTENTE.CLIENTE`, con paginación estable, filtros opcionales y total de registros.
2. `listar_facturas(fecha_desde, fecha_hasta, pagina=1, tamano_pagina=100, codigo_cliente=None)`: encabezados de `ASISTENTE.FACTURA` y, opcionalmente, líneas de `ASISTENTE.FACTURA_LINEA`. No inferir cobros desde el total facturado.
3. `listar_pedidos(fecha_desde=None, fecha_hasta=None, codigo_cliente=None, pagina=1, tamano_pagina=100)`: encabezados de `ASISTENTE.PEDIDO` y detalle de `ASISTENTE.PEDIDO_LINEA`. Son antecedentes comerciales, no necesariamente ventas concretadas.

## Prerrequisitos de implementación
- Confirmar mediante metadatos de SQL Server nombres reales y tipos de columnas en `ASISTENTE.PEDIDO` y `ASISTENTE.PEDIDO_LINEA`, claves y fechas; verificar también la clave compuesta de factura y pedido.
- Crear procedimientos `andi.sp_listar_clientes`, `andi.sp_listar_facturas` y `andi.sp_listar_pedidos` que solo lean tablas `ASISTENTE`, con permisos EXECUTE al usuario del Gateway.
- Limitar `tamano_pagina` a 1–200, validar fechas y filtrar correo sobre los campos disponibles; ordenar por clave estable y devolver el total. No exponer credenciales ni datos personales en auditoría.
- Mantener consultas parametrizadas y auditoría sin resultados completos; pruebas de paginación, rango inclusivo de fechas, coincidencia exacta/parcial de correo y pedidos sin factura.
- Validar primero en una copia de Softland antes de despliegue. No modificar `main` hasta revisión.

## Caso de aceptación
Para Agribio: buscar clientes cuyo correo de facturación sea `recepcionfacturas2@agribiocr.com`; revisar facturas emitidas entre 2026-09-16 y 2026-10-16; recuperar pedidos históricos del cliente y sus líneas.
