# Arquitectura

## Principios

1. **Un agente, un trabajo.** Cada agente tiene una responsabilidad pequeña y comprobable. Así se pueden probar, sustituir o mejorar uno a uno.
2. **Nadie se llama directamente.** Los agentes se comunican publicando eventos en el `Bus` (`bus.py`). El catálogo `Temas` es el contrato entre ellos.
3. **Reglas primero, IA donde aporta.** Lo que tiene respuesta exacta (huella, IVA, NIF, conciliación por importe) se hace con código determinista. Claude se usa para lo ambiguo: leer facturas en texto libre, redactar correos y responder preguntas. Sin API key, todo sigue funcionando.
4. **Conectores intercambiables.** Los agentes dependen de interfaces (`connectors/base.py`), no de servicios concretos. Google Drive es un conector más.
5. **Escalar a una persona.** Cuando un agente no puede resolver algo (proveedor que no contesta, NIF erróneo, total incoherente), abre una incidencia o publica `escalado.humano` en lugar de inventar.

## Dos formas de reaccionar

- **Reactiva:** el agente se suscribe a un evento (`escuchar(Temas.X, …)`). Ejemplo: cuando llega `factura.recibida`, el conciliador busca su pago y el revisor la audita.
- **Programada:** el agente declara `fases = ("deteccion",)` y el orquestador le da paso en cada ciclo. Ejemplo: el detective revisa cada día qué pagos siguen sin factura.

Ejemplo de conversación entre agentes cuando llega una factura que faltaba:

```
recepcion   → factura.recibida        (TPV-10-5531, 48,40 €)
conciliador → banco.conciliado        (cargo del 03/10 ↔ TPV-10-5531)
detective   → factura.faltante_resuelta
```

## Estado

- `Libro`: terceros, facturas, movimientos, faltantes, incidencias y correos. Se guarda en `datos_runtime/libro.pkl` tras cada ciclo para no reprocesar documentos ni repetir correos.
- `SistemaVeriFactu`: registros de facturación en SQLite con *triggers* que impiden borrar o modificar registros. Ver [verifactu.md](verifactu.md).

## Añadir un agente

```python
from agentes_contabilidad.agents.base import Agente
from agentes_contabilidad.bus import Temas

class AgenteGastosAnomalos(Agente):
    nombre = "anomalias"
    rol = "Avisa de gastos muy superiores a la media del proveedor."
    fases = ("revision",)

    def suscribir(self):
        self.escuchar(Temas.FACTURA_RECIBIDA, self._on_factura)

    def _on_factura(self, msg):
        f = msg.datos["factura"]
        historico = self.libro.recibidas_de(f.emisor_nif)
        ...
        self.incidencia("GASTO_ANOMALO", f"{f.emisor_nombre}: {f.importe_total} €")
```

Y se registra en el orquestador: `Orquestador(ctx, agentes=AGENTES_POR_DEFECTO + [AgenteGastosAnomalos])`.

## Añadir un conector

Implementa el protocolo correspondiente de `connectors/base.py`:

| Protocolo | Método | Ejemplos posibles |
|---|---|---|
| `FuenteDocumentos` | `nuevos_documentos() -> list[Documento]` | OneDrive, Dropbox, Holded, WhatsApp Business |
| `FuenteBancaria` | `movimientos() -> list[MovimientoBancario]` | Agregadores PSD2, Norma 43 |
| `Correo` | `enviar(EmailSaliente)` | Gmail API, Microsoft Graph |
| `ClienteAEAT` | `enviar_registros(xml, secuencias)` | SOAP VeriFactu con certificado |

Después, añádelo a `crear_documentos` (o equivalente) en `config.py` para poder activarlo desde el JSON.

## Escalar a más negocios

Para que una asesoría gestione varios clientes, se instancia un `Orquestador` por empresa, cada uno con su propia carpeta de datos. El bus en proceso se puede sustituir por Redis o NATS sin tocar los agentes, porque solo usan `publicar` y `suscribir`.
