/* =====================================================================
   ANDI Gateway - Paso 1: usuario de solo lectura + procedimiento
   ---------------------------------------------------------------------
   ANTES DE EJECUTAR, AJUSTA:
     1. [SOFTLAND]   -> nombre real de tu base de datos
     2. [ASISTENTE]       -> esquema de tu compañía en Softland (ej. el
                           nombre de la compañía). Míralo en SSMS.
     3. Columnas de la tabla CLIENTE -> verifica con:
           SELECT TOP 5 * FROM [ASISTENTE].CLIENTE;
     4. Define la contraseña real únicamente al ejecutar/configurar localmente; nunca la guardes en Git.

   RECOMENDACIÓN: ejecútalo primero en una COPIA restaurada de la base,
   no en producción.
   ===================================================================== */

USE [master];
GO

-- 1) Login a nivel de servidor (solo autenticación SQL, sin permisos extra)
IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'andi_gateway')
    CREATE LOGIN [andi_gateway]
        WITH PASSWORD = N'CAMBIAR_POR_CONTRASENA_SEGURA_LOCAL',
             CHECK_POLICY = ON,
             DEFAULT_DATABASE = [SOFTLAND];
GO

USE [SOFTLAND];
GO

-- 2) Usuario en la base, SIN roles (ni db_datareader)
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'andi_gateway')
    CREATE USER [andi_gateway] FOR LOGIN [andi_gateway];
GO

-- 3) Contexto de lectura interno, sin login ni roles amplios.
-- andi_gateway NO recibe SELECT ni IMPERSONATE sobre este usuario.
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'andi_reader')
    CREATE USER [andi_reader] WITHOUT LOGIN;
GO

GRANT SELECT ON OBJECT::[ASISTENTE].[CLIENTE] TO [andi_reader];
GRANT SELECT ON OBJECT::[ASISTENTE].[DOCUMENTOS_CC] TO [andi_reader];
GRANT SELECT ON OBJECT::[ASISTENTE].[FACTURA] TO [andi_reader];
GRANT SELECT ON OBJECT::[ASISTENTE].[FACTURA_LINEA] TO [andi_reader];
GRANT SELECT ON OBJECT::[ASISTENTE].[CENTRO_COSTO] TO [andi_reader];
GO

-- Esquema propio para todo lo que Andi puede ejecutar
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'andi')
    EXEC('CREATE SCHEMA [andi] AUTHORIZATION [dbo]');
GO

-- 4) Procedimiento: busca por código o nombre, máximo 10 filas
CREATE OR ALTER PROCEDURE [andi].[sp_buscar_cliente]
    @termino NVARCHAR(60)
WITH EXECUTE AS 'andi_reader'
AS
BEGIN
    SET NOCOUNT ON;

    IF @termino IS NULL OR LEN(LTRIM(RTRIM(@termino))) < 2
        RETURN;

    -- Escapar comodines de LIKE para que el término se trate como texto
    DECLARE @t NVARCHAR(130) =
        REPLACE(REPLACE(REPLACE(LTRIM(RTRIM(@termino)), N'[', N'[[]'), N'%', N'[%]'), N'_', N'[_]');

    SELECT TOP (10)
        c.CLIENTE      AS codigo,
        c.NOMBRE       AS nombre,
        c.CONTACTO     AS contacto,
        c.TELEFONO1    AS telefono,
        c.E_MAIL       AS correo,
        c.SALDO        AS saldo
    FROM [ASISTENTE].[CLIENTE] AS c          -- <== AJUSTAR esquema/tabla/columnas
    WHERE c.CLIENTE LIKE @t + N'%'
       OR c.NOMBRE  LIKE N'%' + @t + N'%'
    ORDER BY c.NOMBRE;
END
GO

-- 5) Gateway: permisos de ejecución por procedimiento, nunca SELECT libre
GRANT EXECUTE ON OBJECT::[andi].[sp_buscar_cliente] TO [andi_gateway];
GO


-- 6) Cliente 360: ficha, cuentas por cobrar e historial de compras
CREATE OR ALTER PROCEDURE [andi].[sp_cliente_360]
    @cliente NVARCHAR(40)
WITH EXECUTE AS 'andi_reader'
AS
BEGIN
    SET NOCOUNT ON;

    IF @cliente IS NULL OR LEN(LTRIM(RTRIM(@cliente))) = 0
        RETURN;

    DECLARE @codigo NVARCHAR(40) = LTRIM(RTRIM(@cliente));

    -- Result set 1: ficha completa del cliente
    SELECT TOP (1) A.*
    FROM ASISTENTE.CLIENTE AS A
    WHERE A.CLIENTE = @codigo;

    -- Result set 2: cuentas por cobrar abiertas
    SELECT
        A.CLIENTE,
        A.NOMBRE,
        A.CONDICION_PAGO AS CONDICION_DEFECTO,
        CC.DOCUMENTO,
        CC.APLICACION,
        CC.SALDO_DOLAR,
        CC.SALDO_LOCAL,
        CC.FECHA_VENCE,
        CC.CONDICION_PAGO
    FROM ASISTENTE.CLIENTE AS A
    INNER JOIN ASISTENTE.DOCUMENTOS_CC AS CC
        ON A.CLIENTE = CC.CLIENTE
    WHERE A.CLIENTE = @codigo
      AND CC.SALDO_DOLAR > 0
    ORDER BY CC.FECHA_VENCE, CC.DOCUMENTO;

    -- Result set 3: historial de compras / detalle facturado
    SELECT
        F.FACTURA,
        F.FECHA,
        FL.ARTICULO,
        F.ORDEN_COMPRA,
        FL.DESCRIPCION,
        F.MULTIPLICADOR_EV * FL.CANTIDAD AS CANTIDAD,
        CASE
            WHEN F.MONEDA_FACTURA = 'L'
                THEN (FL.MULTIPLICADOR_EV * FL.PRECIO_TOTAL) / NULLIF(F.TIPO_CAMBIO, 0)
            ELSE (FL.MULTIPLICADOR_EV * FL.PRECIO_TOTAL)
        END AS TOTAL_LINEA,
        F.OBSERVACIONES,
        F.NOMBRE_CLIENTE,
        F.CLIENTE,
        CC.CENTRO_COSTO,
        CC.DESCRIPCION AS DESCRIPCION_CC,
        FL.U_INFORME
    FROM ASISTENTE.FACTURA AS F
    INNER JOIN ASISTENTE.FACTURA_LINEA AS FL
        ON F.FACTURA = FL.FACTURA
    INNER JOIN ASISTENTE.CENTRO_COSTO AS CC
        ON CC.CENTRO_COSTO = FL.CENTRO_COSTO
    WHERE F.CLIENTE = @codigo
    ORDER BY F.FECHA DESC, F.FACTURA DESC;
END
GO

GRANT EXECUTE ON OBJECT::[andi].[sp_cliente_360] TO [andi_gateway];
GO

/* ---------------------------------------------------------------------
   PRUEBAS (ejecútalas como administrador, con un cliente real):
   Los dos procedimientos deben funcionar usando solo andi_gateway.
   El SELECT directo y la suplantación de andi_reader deben FALLAR.
   Siempre ejecutar REVERT después de cada prueba, incluso si falla.

   EXECUTE AS USER = 'andi_gateway';
   EXEC andi.sp_buscar_cliente @termino = N'prueba';
   EXEC andi.sp_cliente_360 @cliente = N'C0090';
   REVERT;

   EXECUTE AS USER = 'andi_gateway';
   SELECT TOP 1 * FROM [ASISTENTE].[CLIENTE];
   REVERT;

   EXECUTE AS USER = 'andi_gateway';
   EXECUTE AS USER = 'andi_reader';
   REVERT;
   -- Si la suplantación inesperadamente funciona, ejecutar otro REVERT.

   Verificar además que ninguno de los dos usuarios tenga roles/permisos
   amplios heredados de instalaciones anteriores (db_owner, db_datareader,
   CONTROL, SELECT de base/esquema o IMPERSONATE).
   --------------------------------------------------------------------- */
