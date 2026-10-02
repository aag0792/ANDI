# Acceso de ANDI desde ChatGPT con Microsoft Entra

El gateway verifica tokens con PyJWT y las claves públicas de Microsoft. El SDK
MCP publica discovery y desafíos de autenticación. No se guardan tokens ni
secretos en el repo. El login completo requiere configurar Entra y crear la
conexión en ChatGPT; las pruebas locales no confirman ese recorrido.

## 1. Registro de la API: ANDI Gateway

En Entra, abrir el registro de aplicación destinado al gateway:

1. En **Manifiesto**, dentro de **api**, establecer **requestedAccessTokenVersion**
   en **2**, conservando los otros campos.
2. En **Exponer una API**, establecer la URI de identificador en
   **https://andi.and.cr/mcp**. Debe coincidir exactamente con la URL del recurso.
3. Agregar el ámbito **andi.access**, habilitado, con consentimiento **solo de
   administradores**. Nombre visible: **Consultar ANDI**. Descripción:
   **Permite usar las herramientas de ANDI y consultar Softland con los permisos del gateway.**

El ámbito completo será **https://andi.and.cr/mcp/andi.access**.
Si Entra rechaza la URI, revisar el error y la configuración del tenant antes
de cambiar la URL del recurso. No sustituirla por otra URI solo en un lado.

## 2. Registro del cliente: ANDI ChatGPT

Crear otro registro de aplicación con cuentas solo del tenant:

1. En **Permisos de API → Agregar un permiso → Mis API**, seleccionar
   **ANDI Gateway**, permisos delegados y **andi.access**.
2. Conceder consentimiento de administrador para ese permiso.
3. En **Autenticación**, agregar plataforma **Web** y la URI de redirección exacta
   que muestre la conexión de ChatGPT. No registrar una URI de ejemplo.
4. Si ChatGPT solicita un secreto OAuth, crearlo en **Certificados y secretos**
   de **ANDI ChatGPT** y copiar su valor directamente al formulario de ChatGPT.
   No compartirlo por chat, incluirlo en Git ni guardarlo en el .env del gateway.
   Anotar su vencimiento para renovarlo.

Microsoft Entra no ofrece registro dinámico de clientes para este flujo.
Usar el cliente OAuth predefinido, con el ID del registro **ANDI ChatGPT**.
El ID de **ANDI Gateway** es la audiencia de los tokens, no el cliente del conector.

## 3. Configuración del server

Actualizar la misma rama de trabajo, instalar requirements.txt y agregar al
archivo de configuración activo (.env o conexion.env):

```dotenv
GATEWAY_AUTH_MODE=entra
PUBLIC_BASE_URL=https://andi.and.cr
ENTRA_TENANT_ID=UUID_DEL_TENANT
ENTRA_CLIENT_ID=UUID_DEL_REGISTRO_ANDI_GATEWAY
ENTRA_ALLOWED_USER_IDS=UUID_DEL_USUARIO_ANDRES
ENTRA_ALLOWED_CLIENT_IDS=UUID_DEL_REGISTRO_ANDI_CHATGPT
```

Usar el **ID de objeto del usuario**, no el de una aplicación. Se exige una lista
no vacía de usuarios y clientes; no se concede acceso a todo el tenant.
Reiniciar la tarea/servicio del gateway después de detener la instancia anterior.

En modo entra el token fijo anterior ya no es válido, aunque permanezca en el
archivo. En modo token se conserva el flujo local anterior y, si se configura
PUBLIC_BASE_URL, se admite el host público sin desactivar protección de Host/Origin.
Los logs de auditoría y las credenciales SQL siguen configurándose como antes.

## 4. Verificación y conexión

Desde fuera del server:

- **https://andi.and.cr/health** debe devolver status ok.
- **https://andi.and.cr/.well-known/oauth-protected-resource/mcp** debe devolver
  resource **https://andi.and.cr/mcp**, el issuer del tenant y el ámbito completo.
- Una llamada a **/mcp** sin token debe devolver **401** y un encabezado
  **WWW-Authenticate** con esa URL de metadatos.
- El logo debe funcionar; **/assets/.env**, **/assets/conexion.env** y archivos
  del repo deben ser inaccesibles. El gateway solo sirve el logo en assets.

En ChatGPT web, crear una conexión MCP a **https://andi.and.cr/mcp** con OAuth y
el ID del cliente **ANDI ChatGPT**, siguiendo el formulario disponible en la cuenta.
Copiar la URI de redirección que muestra ChatGPT al registro Web en Entra.
Iniciar sesión con el usuario permitido y seleccionar la conexión en un chat.

Si el formulario pide endpoints manualmente, los de Microsoft son:

- Autorización: **https://login.microsoftonline.com/TENANT_ID/oauth2/v2.0/authorize**
- Token: **https://login.microsoftonline.com/TENANT_ID/oauth2/v2.0/token**
- Ámbito: **https://andi.and.cr/mcp/andi.access**

Reemplazar TENANT_ID por el UUID del tenant. El servidor identifica a Microsoft
mediante el issuer **https://login.microsoftonline.com/TENANT_ID/v2.0**; no publica
un servidor de autorización propio ni almacena un secreto de cliente.
Si la conexión no descubre Entra o rechaza la combinación resource/scope,
recoger el código de error sin tokens ni secretos y resolverlo antes de declararla
validada. No permitir acceso anónimo como alternativa.

Probar tools/list y cliente_360 para un cliente real desde la compu y el teléfono.
Una respuesta local con datos simulados no sustituye esta prueba.

## Comportamiento y límites

Se validan firma RSA, issuer, audiencia, tiempo de validez, versión v2, tenant,
usuario, aplicación cliente y ámbito delegado. Tokens de Graph, tokens de ID,
tokens de aplicaciones sin usuario, otros usuarios y clientes se rechazan.
Las claves públicas se consultan en Microsoft con timeout y caché; si no se pueden
obtener o el token no se valida, se rechaza el acceso. La validación se realiza
fuera del event loop del gateway.

Cloudflare Tunnel apunta a **http://127.0.0.1:1992**. La autenticación se mantiene
en el gateway. Una pantalla de login adicional del proxy no sustituye OAuth MCP.

Fuentes:
- [Microsoft: proteger MCP con Entra](https://learn.microsoft.com/en-us/entra/agent-id/secure-mcp-server-with-entra-id)
- [Microsoft: validación de claims](https://learn.microsoft.com/en-us/entra/identity-platform/claims-validation)
- [OpenAI: autenticación MCP](https://developers.openai.com/plugins/build/auth)
