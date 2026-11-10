# Roadmap

## v0.1 — MVP
- [x] Bus de mensajes y 8 agentes especializados + orquestador
- [x] Núcleo VeriFactu: huella encadenada (validada con el ejemplo de la AEAT), QR, registros inalterables, XML
- [x] Conectores: carpeta local, Google Drive, IMAP, banco CSV, SMTP, AEAT simulada
- [x] Detección de facturas que faltan, reclamaciones con reintentos y escalado
- [x] Envío de facturas y recordatorios de cobro
- [x] Revisor (NIF, totales, IVA, duplicados, numeración, cadena)
- [x] Borrador del modelo 303 y aviso de plazos
- [x] CLI, persistencia entre ejecuciones, 21 tests y CI en GitHub Actions

## v0.2 — La Oficina (actual)
- [x] Panel visual: los agentes como personas en una oficina, con el tráfico de mensajes animado
- [x] Modo en directo (`agentes-conta web`) y grabación reproducible sin servidor
- [x] Desde el panel: lanzar jornadas, emitir ventas, recibir facturas y revisar las notas de tu mesa
- [x] 24 tests (incluida la API del panel)

## v0.3 — VeriFactu real
- [ ] Validar el XML contra los XSD oficiales
- [ ] Cliente SOAP completo: respuesta, control de flujo, reintentos y subsanación
- [ ] Facturas rectificativas (R1–R5) y en sustitución de simplificadas (F3)
- [ ] PDF de factura con el QR y la leyenda «VERI*FACTU»

## v0.4 — Más integraciones
- [ ] Bandeja de entrada de Gmail y Outlook (API) con respuestas automáticas de proveedores
- [ ] Bancos vía agregador PSD2 y ficheros Norma 43
- [ ] OneDrive, Dropbox y exportación a programas de la asesoría (A3, Sage, Contasol)
- [ ] Lectura de tickets y fotos de facturas con Claude (visión)

## v0.5 — Producto
- [ ] Libro en SQLite/PostgreSQL en lugar de pickle
- [ ] Autenticación y acceso remoto al panel (hoy solo escucha en este ordenador)
- [ ] Modo asesoría: varias empresas en una instalación
- [ ] Modelos 111, 115, 130, 347 y 390
- [ ] Agente «Asesor» que conversa con el dueño por chat o WhatsApp
