/* =====================================================================
   ANDI Gateway - Paso 1: usuario de solo lectura + procedimiento
   ---------------------------------------------------------------------
   ANTES DE EJECUTAR, AJUSTA:
     1. [SOFTLAND_DB]   -> nombre real de tu base de datos
     2. [EMPRESA]       -> esquema de tu compañía en Softland (ej. el
                           nombre de la compañía). Míralo en SSMS.
     3. Columnas de la tabla CLIENTE -> verifica con:
           SELECT TOP 5 * FROM [EMPRESA].CLIENTE;
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

-- 3) Esquema propio para todo lo que Andi puede ejecutar
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'andi')
    EXEC('CREATE SCHEMA [andi] AUTHORIZATION [dbo]');
GO

-- 4) Procedimiento: busca por código o nombre, máximo 10 filas
CREATE OR ALTER PROCEDURE [andi].[sp_buscar_cliente]
    @termino NVARCHAR(60)
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
    FROM asistente.[CLIENTE] AS c          -- <== AJUSTAR esquema/tabla/columnas
    WHERE c.CLIENTE LIKE @t + N'%'
       OR c.NOMBRE  LIKE N'%' + @t + N'%'
    ORDER BY c.NOMBRE;
END
GO

-- 5) Único permiso que tiene Andi: ejecutar ESE procedimiento
GRANT EXECUTE ON OBJECT::[andi].[sp_buscar_cliente] TO [andi_gateway];
GO

/* ---------------------------------------------------------------------
   PRUEBAS (ejecútalas como administrador):

   -- Debe funcionar:
   EXECUTE AS USER = 'andi_gateway';
   EXEC andi.sp_buscar_cliente @termino = N'prueba';
   REVERT;

   -- Debe FALLAR con "permiso denegado" (si no falla, hay un permiso de más):
   EXECUTE AS USER = 'andi_gateway';
   SELECT TOP 1 * FROM [EMPRESA].CLIENTE;
   REVERT;
   --------------------------------------------------------------------- */
