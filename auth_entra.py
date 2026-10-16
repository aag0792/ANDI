"""Validación de access tokens Entra para ANDI; no almacena secretos OAuth."""
import asyncio
import logging
import jwt
from jwt import PyJWKClient
from starlette.responses import JSONResponse
try:
    from . import config
except ImportError:
    import config

log = logging.getLogger('andi.auth')

class EntraAuth:
    def __init__(self, app):
        self.app = app
        self.keys = PyJWKClient(
            f'https://login.microsoftonline.com/{config.ENTRA_TENANT_ID}/discovery/v2.0/keys',
            timeout=10,
        )

    def validate(self, token):
        # La versión solo elige entre dos políticas fijas; no se confía en claims
        # hasta que se hayan verificado firma, issuer, audience y fechas.
        unverified = jwt.decode(token, options={'verify_signature': False})
        version = unverified.get('ver')
        if version == '2.0':
            issuer = f'https://login.microsoftonline.com/{config.ENTRA_TENANT_ID}/v2.0'
            audience = config.ENTRA_CLIENT_ID
        elif version == '1.0':
            issuer = f'https://sts.windows.net/{config.ENTRA_TENANT_ID}/'
            audience = config.ENTRA_AUDIENCE_V1
        else:
            raise jwt.InvalidTokenError('version_no_admitida')
        key = self.keys.get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token, key, algorithms=['RS256'], audience=audience, issuer=issuer,
            options={'require': ['exp', 'iat', 'nbf', 'iss', 'aud', 'tid', 'sub']},
            leeway=30,
        )
        if claims.get('tid') != config.ENTRA_TENANT_ID:
            raise jwt.InvalidTokenError('tenant_incorrecto')
        if config.ENTRA_REQUIRED_SCOPE not in str(claims.get('scp', '')).split():
            raise PermissionError('scope_requerido')
        if config.ENTRA_ALLOWED_CLIENTS:
            client = str(claims.get('azp') if version == '2.0' else claims.get('appid', '')).lower()
            if client not in config.ENTRA_ALLOWED_CLIENTS:
                raise PermissionError('cliente_no_permitido')
        if config.ENTRA_ALLOWED_USERS:
            identities = {str(claims.get(k, '')).lower() for k in
                          ('oid', 'preferred_username', 'upn', 'email')}
            if not identities.intersection(config.ENTRA_ALLOWED_USERS):
                raise PermissionError('usuario_no_permitido')
        return claims

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        path = scope['path']
        public = {'/', '/health', '/terms', '/condiciones-generales',
                  '/assets/Andi blanco.jpeg',
                  '/.well-known/oauth-protected-resource',
                  '/.well-known/oauth-protected-resource/mcp'}
        if path in public:
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', []))
        value = headers.get(b'authorization', b'').decode('latin-1')
        scheme, _, token = value.partition(' ')
        challenge = {'WWW-Authenticate':
            f'Bearer resource_metadata="{config.PUBLIC_BASE_URL}/.well-known/oauth-protected-resource"'}
        if scheme.lower() != 'bearer' or not token.strip():
            return await JSONResponse({'error': 'no autorizado'}, status_code=401,
                                      headers=challenge)(scope, receive, send)
        try:
            claims = await asyncio.to_thread(self.validate, token.strip())
        except PermissionError as exc:
            log.warning('Acceso Entra denegado: %s', str(exc))
            return await JSONResponse({'error': 'permisos insuficientes'}, status_code=403)(scope, receive, send)
        except jwt.PyJWKClientConnectionError:
            log.warning('No se pudieron obtener las claves de Entra')
            return await JSONResponse({'error': 'autenticacion temporalmente no disponible'},
                                      status_code=503)(scope, receive, send)
        except (jwt.PyJWTError, ValueError, TypeError) as exc:
            log.warning('Token Entra rechazado: %s', type(exc).__name__)
            return await JSONResponse({'error': 'token invalido o vencido'}, status_code=401,
                                      headers=challenge)(scope, receive, send)
        scope.setdefault('state', {})['entra_claims'] = claims
        return await self.app(scope, receive, send)
