-- Diagnóstico de estructura Softland. Ejecutar en SSMS con permisos de solo lectura.
-- No devuelve filas de clientes; solo metadatos y muestras limitadas.
SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE,
       CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE, ORDINAL_POSITION
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'ASISTENTE'
  AND TABLE_NAME IN ('CLIENTE','FACTURA','FACTURA_LINEA','PEDIDO','PEDIDO_LINEA')
ORDER BY TABLE_NAME, ORDINAL_POSITION;

SELECT t.name AS tabla, kc.name AS clave, c.name AS columna, ic.key_ordinal
FROM sys.key_constraints kc
JOIN sys.tables t ON t.object_id = kc.parent_object_id
JOIN sys.schemas s ON s.schema_id = t.schema_id
JOIN sys.index_columns ic ON ic.object_id = t.object_id AND ic.index_id = kc.unique_index_id
JOIN sys.columns c ON c.object_id = t.object_id AND c.column_id = ic.column_id
WHERE s.name = 'ASISTENTE'
  AND t.name IN ('CLIENTE','FACTURA','FACTURA_LINEA','PEDIDO','PEDIDO_LINEA')
ORDER BY t.name, kc.name, ic.key_ordinal;

-- Opcional: ejecutar individualmente en entorno autorizado para ver ejemplos:
-- SELECT TOP (10) * FROM ASISTENTE.CLIENTE;
-- SELECT TOP (10) * FROM ASISTENTE.FACTURA;
-- SELECT TOP (10) * FROM ASISTENTE.FACTURA_LINEA;
-- SELECT TOP (10) * FROM ASISTENTE.PEDIDO;
-- SELECT TOP (10) * FROM ASISTENTE.PEDIDO_LINEA;
