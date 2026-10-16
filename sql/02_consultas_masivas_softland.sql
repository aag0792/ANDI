-- Consultas Softland: ejecutar en copia de pruebas primero.
-- Procedimientos de solo lectura; las columnas tecnicas se excluyen por metadatos.
-- IMPORTANTE: conceder EXECUTE solamente a estos procedimientos.
CREATE OR ALTER PROCEDURE andi.sp_listar_clientes
 @pagina int=1,@tamano int=100,@correo nvarchar(249)=NULL,@nombre nvarchar(150)=NULL
AS
BEGIN
 SET NOCOUNT ON;
 IF @pagina<1 OR @tamano NOT BETWEEN 1 AND 200 THROW 50001,'Paginacion invalida',1;
 DECLARE @cols nvarchar(max),@sql nvarchar(max);
 SELECT @cols=STRING_AGG(CONVERT(nvarchar(max),'c.'+QUOTENAME(name)),',') WITHIN GROUP(ORDER BY column_id)
 FROM sys.columns WHERE object_id=OBJECT_ID(N'ASISTENTE.CLIENTE')
 AND UPPER(REPLACE(name,'_','')) NOT IN ('ROWPOINTER','CREATEDATE','CREATEDDATE','RECORDATE','RECORDDATE','NOTEXISTFLAG','UPDATEBY','UPDATEDBY');
 SET @sql=N'SELECT '+@cols+N', COUNT_BIG(*) OVER() AS _total_registros FROM ASISTENTE.CLIENTE c
 WHERE (@nombre IS NULL OR c.NOMBRE LIKE ''%''+@nombre+''%'')
 AND (@correo IS NULL OR c.E_MAIL LIKE ''%''+@correo+''%'' OR c.EMAIL_DOC_ELECTRONICO LIKE ''%''+@correo+''%''
 OR c.EMAIL_DOC_ELECTRONICO_COPIA LIKE ''%''+@correo+''%'')
 ORDER BY c.CLIENTE OFFSET (@pagina-1)*@tamano ROWS FETCH NEXT @tamano ROWS ONLY';
 EXEC sp_executesql @sql,N'@pagina int,@tamano int,@correo nvarchar(249),@nombre nvarchar(150)',@pagina,@tamano,@correo,@nombre;
END;
GO
CREATE OR ALTER PROCEDURE andi.sp_listar_facturas
 @pagina int=1,@tamano int=100,@desde date=NULL,@hasta date=NULL,@cliente varchar(20)=NULL
AS
BEGIN
 SET NOCOUNT ON;
 IF @pagina<1 OR @tamano NOT BETWEEN 1 AND 200 THROW 50001,'Paginacion invalida',1;
 DECLARE @min date=DATEADD(year,-2,CONVERT(date,GETDATE()));
 IF @desde IS NOT NULL AND @desde<@min THROW 50002,'Rango mayor a dos anos',1;
 IF @hasta IS NOT NULL AND (@hasta<@min OR @hasta>CONVERT(date,GETDATE())) THROW 50003,'Fecha fuera de rango',1;
 IF @desde IS NOT NULL AND @hasta IS NOT NULL AND @desde>@hasta THROW 50004,'Rango invertido',1;
 DECLARE @cols nvarchar(max),@sql nvarchar(max);
 SELECT @cols=STRING_AGG(CONVERT(nvarchar(max),'f.'+QUOTENAME(name)),',') WITHIN GROUP(ORDER BY column_id)
 FROM sys.columns WHERE object_id=OBJECT_ID(N'ASISTENTE.FACTURA')
 AND UPPER(REPLACE(name,'_','')) NOT IN ('ROWPOINTER','CREATEDATE','CREATEDDATE','RECORDATE','RECORDDATE','NOTEXISTFLAG','UPDATEBY','UPDATEDBY');
 SET @sql=N'SELECT '+@cols+N', COUNT_BIG(*) OVER() AS _total_registros FROM ASISTENTE.FACTURA f
 WHERE f.FECHA>=@min AND f.FECHA>=COALESCE(@desde,@min)
 AND f.FECHA<DATEADD(day,1,COALESCE(@hasta,CONVERT(date,GETDATE())))
 AND (@cliente IS NULL OR f.CLIENTE=@cliente)
 ORDER BY f.FECHA DESC,f.TIPO_DOCUMENTO,f.FACTURA
 OFFSET (@pagina-1)*@tamano ROWS FETCH NEXT @tamano ROWS ONLY';
 EXEC sp_executesql @sql,N'@pagina int,@tamano int,@min date,@desde date,@hasta date,@cliente varchar(20)',@pagina,@tamano,@min,@desde,@hasta,@cliente;
END;
GO
CREATE OR ALTER PROCEDURE andi.sp_listar_pedidos
 @pagina int=1,@tamano int=100,@desde date=NULL,@hasta date=NULL,@cliente varchar(20)=NULL
AS
BEGIN
 SET NOCOUNT ON;
 IF @pagina<1 OR @tamano NOT BETWEEN 1 AND 200 THROW 50001,'Paginacion invalida',1;
 DECLARE @min date=DATEADD(year,-2,CONVERT(date,GETDATE()));
 IF @desde IS NOT NULL AND @desde<@min THROW 50002,'Rango mayor a dos anos',1;
 IF @hasta IS NOT NULL AND (@hasta<@min OR @hasta>CONVERT(date,GETDATE())) THROW 50003,'Fecha fuera de rango',1;
 IF @desde IS NOT NULL AND @hasta IS NOT NULL AND @desde>@hasta THROW 50004,'Rango invertido',1;
 DECLARE @cols nvarchar(max),@sql nvarchar(max);
 SELECT @cols=STRING_AGG(CONVERT(nvarchar(max),'p.'+QUOTENAME(name)),',') WITHIN GROUP(ORDER BY column_id)
 FROM sys.columns WHERE object_id=OBJECT_ID(N'ASISTENTE.PEDIDO')
 AND UPPER(REPLACE(name,'_','')) NOT IN ('ROWPOINTER','CREATEDATE','CREATEDDATE','RECORDATE','RECORDDATE','NOTEXISTFLAG','UPDATEBY','UPDATEDBY');
 SET @sql=N'SELECT '+@cols+N', COUNT_BIG(*) OVER() AS _total_registros FROM ASISTENTE.PEDIDO p
 WHERE p.FECHA_PEDIDO>=@min AND p.FECHA_PEDIDO>=COALESCE(@desde,@min)
 AND p.FECHA_PEDIDO<DATEADD(day,1,COALESCE(@hasta,CONVERT(date,GETDATE())))
 AND (@cliente IS NULL OR p.CLIENTE=@cliente)
 ORDER BY p.FECHA_PEDIDO DESC,p.PEDIDO
 OFFSET (@pagina-1)*@tamano ROWS FETCH NEXT @tamano ROWS ONLY';
 EXEC sp_executesql @sql,N'@pagina int,@tamano int,@min date,@desde date,@hasta date,@cliente varchar(20)',@pagina,@tamano,@min,@desde,@hasta,@cliente;
END;
GO
CREATE OR ALTER PROCEDURE andi.sp_factura_lineas
 @tipo_documento varchar(10),@factura varchar(50)
AS
BEGIN
 SET NOCOUNT ON;
 DECLARE @cols nvarchar(max),@sql nvarchar(max);
 SELECT @cols=STRING_AGG(CONVERT(nvarchar(max),'l.'+QUOTENAME(name)),',') WITHIN GROUP(ORDER BY column_id)
 FROM sys.columns WHERE object_id=OBJECT_ID(N'ASISTENTE.FACTURA_LINEA')
 AND UPPER(REPLACE(name,'_','')) NOT IN ('ROWPOINTER','CREATEDATE','CREATEDDATE','RECORDATE','RECORDDATE','NOTEXISTFLAG','UPDATEBY','UPDATEDBY');
 SET @sql=N'SELECT '+@cols+N' FROM ASISTENTE.FACTURA_LINEA l
 JOIN ASISTENTE.FACTURA f ON f.FACTURA=l.FACTURA AND f.TIPO_DOCUMENTO=l.TIPO_DOCUMENTO
 WHERE f.FECHA>=DATEADD(year,-2,CONVERT(date,GETDATE())) AND f.FECHA<DATEADD(day,1,CONVERT(date,GETDATE()))
 AND l.TIPO_DOCUMENTO=@tipo_documento AND l.FACTURA=@factura ORDER BY l.LINEA';
 EXEC sp_executesql @sql,N'@tipo_documento varchar(10),@factura varchar(50)',@tipo_documento,@factura;
END;
GO
CREATE OR ALTER PROCEDURE andi.sp_pedido_lineas
 @pedido varchar(50)
AS
BEGIN
 SET NOCOUNT ON;
 DECLARE @cols nvarchar(max),@sql nvarchar(max);
 SELECT @cols=STRING_AGG(CONVERT(nvarchar(max),'l.'+QUOTENAME(name)),',') WITHIN GROUP(ORDER BY column_id)
 FROM sys.columns WHERE object_id=OBJECT_ID(N'ASISTENTE.PEDIDO_LINEA')
 AND UPPER(REPLACE(name,'_','')) NOT IN ('ROWPOINTER','CREATEDATE','CREATEDDATE','RECORDATE','RECORDDATE','NOTEXISTFLAG','UPDATEBY','UPDATEDBY');
 SET @sql=N'SELECT '+@cols+N' FROM ASISTENTE.PEDIDO_LINEA l
 JOIN ASISTENTE.PEDIDO p ON p.PEDIDO=l.PEDIDO
 WHERE p.FECHA_PEDIDO>=DATEADD(year,-2,CONVERT(date,GETDATE())) AND p.FECHA_PEDIDO<DATEADD(day,1,CONVERT(date,GETDATE()))
 AND l.PEDIDO=@pedido ORDER BY l.PEDIDO_LINEA';
 EXEC sp_executesql @sql,N'@pedido varchar(50)',@pedido;
END;
GO
