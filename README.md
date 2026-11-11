# SERVILUJOS LA PRIMERA - Sistema administrativo

## Incluye
- Inicio de sesión local.
- Clientes y productos.
- Ventas con varios productos y cálculo configurable de IVA por producto.
- Comprobante PDF interno.
- Envío SMTP opcional del comprobante.
- Historial y configuración del establecimiento.
- Base de datos SQLite local.

## Instalación en Windows (PowerShell)
1. Instala Python 3.11 o superior.
2. Descomprime el ZIP y abre esa carpeta en VS Code.
3. Abre Terminal > Nueva terminal y ejecuta:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

4. Abre `.env` y cambia `SECRET_KEY`, `ADMIN_USER` y `ADMIN_PASSWORD`.
5. Ejecuta:

```powershell
python app.py
```

6. Abre http://127.0.0.1:5000

Inicio predeterminado si no modificas .env:
- Usuario: admin
- Clave: Cambiar123!

Cámbialos antes de usar el sistema. Si PowerShell bloquea la activación:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## Correo
Configura SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD y SMTP_FROM en `.env`.
Para Gmail se requiere configurar una contraseña de aplicación en la cuenta correspondiente; no uses la contraseña normal. Nunca compartas el `.env`.

## IMPORTANTE - DIAN
Este proyecto es un sistema administrativo y genera comprobantes internos de prueba. NO genera XML UBL firmado, NO transmite a los servicios DIAN y NO recibe CUFE/CUDE ni validación previa. Por tanto, sus PDF NO son facturas electrónicas legales ni sustituyen la factura exigible.
Para operar como software propio se debe implementar el Anexo Técnico vigente, firma digital, integración de servicios web, set de pruebas y habilitación DIAN; además se requieren numeración y asociación de prefijos. Revisa la documentación oficial:
https://micrositios.dian.gov.co/sistema-de-facturacion-electronica/documentacion-tecnica/
https://micrositios.dian.gov.co/sistema-de-facturacion-electronica/requerimientos-para-ser-facturador-electronico/

Antes de producción: agrega protección CSRF, roles, auditoría, backups, HTTPS, gestión segura de secretos, validaciones tributarias y pruebas automatizadas. Mantén este servidor solo en localhost mientras no esté endurecido.
