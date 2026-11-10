# VeriFactu en este proyecto

## Contexto normativo

- **Ley 11/2021** (antifraude): obliga a que el software de facturación garantice la integridad, conservación, trazabilidad e inalterabilidad de los registros.
- **Real Decreto 1007/2023**: Reglamento de los Sistemas Informáticos de Facturación (SIF).
- **Orden HAC/1177/2024**: especificaciones técnicas (formato de los registros, huella, QR y servicios web).
- **Plazos**: aplazados por el Real Decreto-ley 15/2025 (diciembre de 2025). La obligación empieza el **1 de enero de 2027** para quienes tributan por el Impuesto sobre Sociedades y el **1 de julio de 2027** para el resto (autónomos incluidos). Conviene confirmar las fechas vigentes en la web de la AEAT.

## Qué cubre el código

| Requisito | Dónde | Estado |
|---|---|---|
| Registro de alta por factura emitida | `verifactu/registro.py` → `registrar_alta` | ✅ |
| Registro de anulación | `registrar_anulacion` | ✅ |
| Huella SHA-256 encadenada con el registro anterior | `verifactu/huella.py` | ✅ Coincide con el ejemplo oficial de la AEAT (test `test_huella_ejemplo_oficial_aeat`) |
| Inalterabilidad | Triggers SQLite que bloquean `UPDATE`/`DELETE` + `verificar_cadena()` | ✅ |
| Detección de manipulaciones | `verificar_cadena()`, agente Revisor y `agentes-conta verificar` | ✅ |
| QR tributario con URL de cotejo | `verifactu/qr.py` (PNG con el extra `[qr]`) | ✅ |
| Numeración correlativa sin huecos por serie | Agente Emisor + Revisor | ✅ |
| XML `RegistroAlta` / `RegistroAnulacion` / `RegFactuSistemaFacturacion` | `registro.py` | ⚠️ Estructura basada en los XSD; falta validarla contra los XSD oficiales |
| Remisión a la AEAT con certificado | `connectors/aeat.py` → `AEATSoap` | ⚠️ Esqueleto: envía, pero falta interpretar la respuesta. Endpoints por confirmar en el WSDL |
| Control de flujo (espera entre envíos que indica la AEAT) | — | ❌ Pendiente |
| Subsanación de registros rechazados | — | ❌ Pendiente |
| Rectificativas (R1–R5) con referencia a la factura rectificada | Tipos definidos en `models.TipoFactura` | ❌ Falta el bloque `FacturasRectificadas` |
| Declaración responsable del productor del software | — | ❌ Trámite legal, no de código |

## Cómo se calcula la huella

```
IDEmisorFactura=89890001K&NumSerieFactura=12345678/G33&FechaExpedicionFactura=01-01-2024&TipoFactura=F1&CuotaTotal=12.35&ImporteTotal=123.45&Huella=&FechaHoraHusoGenRegistro=2024-01-01T19:20:30+01:00
→ SHA-256 → 3C464DAF61ACB827C65FDA19F352A4E3BDC2C640E9E9FC4CC058073F38F12F60
```

`Huella=` va vacío en el primer registro del sistema y, en los siguientes, lleva la huella del registro anterior. Por eso, si se modifica cualquier factura pasada, cambia su huella y deja de coincidir con la que guardó el registro siguiente.

## Antes de producción

1. Validar el XML generado contra los XSD vigentes (`SuministroLR.xsd`, `SuministroInformacion.xsd`).
2. Probar en el entorno de pruebas de la AEAT (`entorno_verifactu: "pruebas"`) con un certificado de pruebas.
3. Implementar la lectura de `RespuestaRegFactuSistemaFacturacion` y el control de flujo.
4. Que un asesor fiscal revise el flujo y los tipos impositivos de tu actividad.
