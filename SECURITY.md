# Política de Seguridad

## Reportar Vulnerabilidades

Si descubres una vulnerabilidad de seguridad, por favor repórtala de manera responsable.

**NO** crees issues públicos para vulnerabilidades de seguridad.

### Contacto

- **Email**: security@kinnycode.com
- **GitHub**: Usa la función de reporte de seguridad de GitHub

### Información a Incluir

- Descripción de la vulnerabilidad
- Pasos para reproducir
- Potencial impacto
- Sugiere una fix (si es posible)

### Respuesta

- **Acknowledgment**: Dentro de 48 horas
- **Assessment**: Dentro de 1 semana
- **Fix**: Dependiendo de la severidad

## Politicas

### Soporte de Seguridad

| Versión | Soporte |
|---------|---------|
| 1.0.x | ✅ Soporte activo |
| 0.9.x | ⚠️ Solo fixes críticos |
| < 0.9 | ❌ Sin soporte |

### Actualizaciones de Seguridad

- Publicaremos advisories para vulnerabilidades críticas
- Los fixes serán lanzados lo antes posible
- Notificaremos a los usuarios afectados

## Mejores Prácticas

### Para Usuarios

1. **Mantén actualizado** el software
2. **No expongas** el servidor directamente a internet
3. **Usa firewalls** para limitar acceso
4. **Monitorea** logs para actividad sospechosa
5. **Usa HTTPS** en producción

### Para Desarrolladores

1. **Valida** todos los inputs
2. **Sanitiza** datos de usuario
3. **Usa parameterized queries**
4. **No hardcodees** secrets
5. **Sigue** OWASP Top 10

## Configuración Segura

### Variables de Entorno

```bash
# Nunca commitees .env
# Usa un gestor de secrets en producción

# Configuración mínima de seguridad
KINNYCODE_HOST=127.0.0.1  # Solo localhost
KINNYCODE_PORT=8007
```

### Firewall

```bash
# Solo permitir localhost
iptables -A INPUT -p tcp --dport 8007 -s 127.0.0.1 -j ACCEPT
iptables -A INPUT -p tcp --dport 8007 -j DROP
```

### Reverse Proxy (Nginx)

```nginx
server {
    listen 443 ssl;
    server_name memory.tudominio.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://127.0.0.1:8007;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Dependencias

- Revisamos regularmente las dependencias por vulnerabilidades
- Usamos `safety check` para detectar problemas
- Actualizamos promptamente cuando hay fixes

## Agradecimientos

Gracias a los investigadores de seguridad que reportan vulnerabilidades de manera responsable.
