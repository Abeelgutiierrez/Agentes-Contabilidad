"""Traza del tráfico entre agentes, pensada para verla en el panel visual.

El ``Trazador`` escucha todo lo que pasa por el bus y lo convierte en
"eventos de tráfico": quién habla con quién, de qué tipo es el mensaje,
una frase en castellano llano y los detalles (la factura, el email, la
huella VeriFactu…) para poder abrirlos con un clic.

En los textos, ``{agente}`` es un hueco que el panel sustituye por el
nombre del personaje (y la consola por el nombre del puesto).
"""
from __future__ import annotations

import threading
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from .bus import Bus, Mensaje, Temas

# Participantes que no son agentes: el exterior y el dueño del negocio
EXTERNOS = {
    "buzon": "Buzón de facturas",
    "banco": "Banco",
    "proveedores": "Proveedores",
    "clientes": "Clientes",
    "aeat": "Hacienda (AEAT)",
    "tu": "Tú",
}

PUESTOS = {
    "orquestador": "Orquestador",
    "recepcion": "Recepción",
    "conciliador": "Conciliador",
    "detective": "Detective",
    "reclamador": "Reclamador",
    "emisor_verifactu": "Emisor VeriFactu",
    "cobros": "Cobros",
    "revisor": "Revisor",
    "fiscal": "Fiscal",
    **EXTERNOS,
}

NOMBRES_FASE = {
    "ingesta": "Recoger documentos",
    "banco": "Revisar el banco",
    "deteccion": "Buscar facturas que faltan",
    "reclamaciones": "Reclamar a proveedores",
    "cobros": "Enviar facturas y cobrar",
    "envio_aeat": "Enviar a Hacienda",
    "revision": "Revisar todo",
    "informe": "Preparar impuestos",
}


def eur(v: Any) -> str:
    """1210.5 -> '1.210,50 €'"""
    d = Decimal(str(v or 0)).quantize(Decimal("0.01"))
    signo = "-" if d < 0 else ""
    entero, dec = f"{abs(d):.2f}".split(".")
    grupos = []
    while len(entero) > 3:
        grupos.insert(0, entero[-3:])
        entero = entero[:-3]
    grupos.insert(0, entero)
    return f"{signo}{'.'.join(grupos)},{dec} €"


def _fecha(d: Optional[date]) -> Optional[str]:
    return d.strftime("%d/%m/%Y") if d else None


def _factura(f) -> Dict[str, Any]:
    return {
        "numero": f.num_serie,
        "emisor": f.emisor_nombre,
        "receptor": f.receptor_nombre,
        "nif_emisor": f.emisor_nif,
        "nif_receptor": f.receptor_nif,
        "fecha": _fecha(f.fecha),
        "vencimiento": _fecha(f.vencimiento),
        "base": eur(f.base_imponible),
        "iva": eur(f.cuota_total),
        "total": eur(f.importe_total),
        "estado": f.estado.value,
        "lineas": [
            {"descripcion": l.descripcion, "cantidad": str(l.cantidad), "precio": eur(l.precio_unitario),
             "iva": f"{format(Decimal(l.tipo_iva).normalize(), 'f')} %"}
            for l in f.lineas
        ],
    }


def _email(e) -> Dict[str, Any]:
    return {"para": e.para, "asunto": e.asunto, "cuerpo": e.cuerpo}


def _incidencia(i) -> Dict[str, Any]:
    return {"id": i.id, "codigo": i.codigo, "mensaje": i.mensaje, "severidad": i.severidad.value,
            "agente": i.agente, "resuelta": i.resuelta}


def _faltante(x) -> Dict[str, Any]:
    return {"id": x.id, "proveedor": x.proveedor_nombre, "motivo": x.motivo,
            "importe": eur(x.importe_estimado) if x.importe_estimado else None,
            "periodo": x.periodo, "intentos": x.intentos, "estado": x.estado.value}


def describir(msg: Mensaje, bus: Bus) -> Optional[Dict[str, Any]]:
    """Convierte un mensaje del bus en un evento de tráfico (o None si no interesa)."""
    t, d, de = msg.tema, msg.datos, msg.emisor
    a: List[str] = [x for x in bus.destinatarios(t) if x != de]
    ev: Dict[str, Any] = {"tema": t, "de": de, "a": a, "tipo": "sistema", "titulo": "", "texto": "", "detalle": {}}

    if t == Temas.CICLO_INICIADO:
        ev.update(a=[], tipo="jornada", titulo="Empieza la jornada",
                  texto=f"Empieza la jornada del {_fecha(d['hoy'])}. {{orquestador}} reparte el trabajo.",
                  detalle={"dia": d["hoy"].isoformat()})
    elif t.startswith("fase."):
        fase = d["fase"]
        nombre = NOMBRES_FASE.get(fase, fase)
        quien = ["{" + x + "}" for x in a]
        lista = " y ".join(quien) if len(quien) <= 2 else ", ".join(quien[:-1]) + " y " + quien[-1]
        verbo = "Se pone a ello" if len(quien) == 1 else "Se ponen a ello"
        ev.update(tipo="fase", titulo=nombre,
                  texto=f"{{orquestador}}: «Toca {nombre[0].lower() + nombre[1:]}». " + (f"{verbo} {lista}." if quien else ""),
                  detalle={"fase": fase})
    elif t == Temas.DOCUMENTO_RECIBIDO:
        doc = d["documento"]
        ev.update(de="buzon", a=["recepcion"], tipo="documento", titulo=f"📄 {doc.nombre}",
                  texto=f"Llega «{doc.nombre}» al buzón y {{recepcion}} lo recoge.",
                  detalle={"documento": {"nombre": doc.nombre, "origen": doc.origen, "extracto": doc.texto[:600]}})
    elif t == Temas.FACTURA_RECIBIDA:
        f = d["factura"]
        ev.update(tipo="documento", titulo=f"Factura {f.num_serie}",
                  texto=f"{{recepcion}} registra la factura {f.num_serie} de {f.emisor_nombre} por {eur(f.importe_total)} y avisa al equipo.",
                  detalle={"factura": _factura(f)})
    elif t == Temas.MOVIMIENTO_BANCARIO:
        m = d["movimiento"]
        tipo_mov = "cobro" if m.importe > 0 else "pago"
        ev.update(de="banco", a=["conciliador"], tipo="banco", titulo=f"{'＋' if m.importe > 0 else '−'}{eur(abs(m.importe))}",
                  texto=f"El banco informa de un {tipo_mov} de {eur(abs(m.importe))}: «{m.concepto}».",
                  detalle={"movimiento": {"fecha": _fecha(m.fecha), "concepto": m.concepto, "importe": eur(m.importe)}})
    elif t == Temas.MOVIMIENTO_CONCILIADO:
        m, f = d["movimiento"], d["factura"]
        ev.update(tipo="banco", titulo="Pago ↔ factura",
                  texto=f"{{conciliador}} casa el movimiento de {eur(abs(m.importe))} con la factura {f.num_serie}. Ya está pagada.",
                  detalle={"movimiento": {"fecha": _fecha(m.fecha), "concepto": m.concepto, "importe": eur(m.importe)},
                           "factura": _factura(f)})
    elif t == Temas.FACTURA_FALTANTE:
        x = d["faltante"]
        importe = f" ({eur(x.importe_estimado)})" if x.importe_estimado else ""
        ev.update(tipo="falta", titulo=f"Falta: {x.proveedor_nombre[:28]}",
                  texto=f"{{detective}} descubre que falta una factura de {x.proveedor_nombre}{importe} y se lo pasa a {{reclamador}}.",
                  detalle={"faltante": _faltante(x)})
    elif t == Temas.FACTURA_FALTANTE_RESUELTA:
        x, f = d["faltante"], d["factura"]
        ev.update(a=["tu"], tipo="exito", titulo="¡Falta resuelta!",
                  texto=f"{{detective}} tacha de la lista la factura de {x.proveedor_nombre}: ya ha llegado ({f.num_serie}).",
                  detalle={"faltante": _faltante(x), "factura": _factura(f)})
    elif t == Temas.RECLAMACION_ENVIADA:
        x, e = d["faltante"], d["email"]
        ev.update(a=["proveedores"], tipo="email", titulo=f"✉ {x.proveedor_nombre[:26]}",
                  texto=f"{{reclamador}} escribe a {x.proveedor_nombre} ({e.para}) pidiendo la factura. Intento {x.intentos}.",
                  detalle={"email": _email(e), "faltante": _faltante(x)})
    elif t == Temas.ESCALADO_HUMANO:
        det = {"motivo": d["motivo"]}
        if d.get("faltante") is not None:
            det["faltante"] = _faltante(d["faltante"])
        ev.update(a=["tu"], tipo="alerta", titulo="Necesito tu ayuda",
                  texto=f"{{{de}}} te pide ayuda: {d['motivo'][0].lower() + d['motivo'][1:]}.", detalle=det)
    elif t == Temas.INCIDENCIA:
        i = d["incidencia"]
        ev.update(a=["tu"], tipo="alerta" if i.severidad.value == "error" else "aviso",
                  titulo={"error": "Error", "aviso": "Aviso", "info": "Nota"}[i.severidad.value],
                  texto=f"{{{de}}} deja una nota en tu mesa: {i.mensaje}", detalle={"incidencia": _incidencia(i)})
    elif t == Temas.INCIDENCIA_RESUELTA:
        i = d["incidencia"]
        ev.update(a=[], tipo="exito", titulo="Revisado",
                  texto=f"Marcas como revisada la nota: {i.mensaje}", detalle={"incidencia": _incidencia(i)})
    elif t == Temas.FACTURA_A_EMITIR:
        f = d["factura"]
        ev.update(tipo="verifactu", titulo=f"Venta a {(f.receptor_nombre or '')[:22]}",
                  texto=f"Pides a {{emisor_verifactu}} una factura para {f.receptor_nombre} por {eur(f.importe_total)}.",
                  detalle={"factura": _factura(f)})
    elif t == Temas.FACTURA_EMITIDA:
        f, r = d["factura"], d["registro"]
        ev.update(tipo="verifactu", titulo=f"Emitida {f.num_serie}",
                  texto=f"{{emisor_verifactu}} emite la factura {f.num_serie} ({eur(f.importe_total)}), la sella con su huella VeriFactu y se la pasa a {{cobros}}.",
                  detalle={"factura": _factura(f), "registro": {
                      "secuencia": r.secuencia, "huella": r.huella, "huella_anterior": r.huella_anterior,
                      "qr": r.url_qr, "fecha_hora": r.fecha_hora_huso.isoformat()}})
    elif t == Temas.FACTURA_ENVIADA:
        f = d["factura"]
        ev.update(a=["clientes"], tipo="email", titulo=f"✉ {f.num_serie} al cliente",
                  texto=f"{{cobros}} envía la factura {f.num_serie} a {f.receptor_nombre}.",
                  detalle={"factura": _factura(f), **({"email": _email(d["email"])} if d.get("email") else {})})
    elif t == Temas.RECORDATORIO_COBRO:
        f = d["factura"]
        ev.update(a=["clientes"], tipo="email", titulo="Recordatorio de pago",
                  texto=f"{{cobros}} recuerda a {f.receptor_nombre} que la factura {f.num_serie} ({eur(f.importe_total)}) venció hace {d.get('dias', '?')} días.",
                  detalle={"factura": _factura(f), "email": _email(d["email"])})
    elif t == Temas.AEAT_ENVIO:
        n = d["aceptados"]
        ev.update(a=["aeat"], tipo="verifactu", titulo=f"{n} registro{'s' if n != 1 else ''} a Hacienda",
                  texto=f"{{emisor_verifactu}} remite {n} registro{'s' if n != 1 else ''} a Hacienda. Aceptados: {n}, rechazados: {d['rechazados']}.",
                  detalle={"aeat": {"aceptados": n, "rechazados": d["rechazados"], "csv": d.get("csv"),
                                    "registros": d.get("registros", [])}})
    elif t == Temas.INFORME_FISCAL:
        inf = d["informe"]
        res = inf.resultado_303
        ev.update(a=["tu"], tipo="fiscal", titulo=f"303: {eur(res)}",
                  texto=f"{{fiscal}} te deja el borrador del modelo 303 ({inf.trimestre}T {inf.anio}): "
                        f"{eur(abs(res))} {'a pagar' if res > 0 else 'a compensar'}. Plazo: {_fecha(inf.plazo)}.",
                  detalle={"informe": {
                      "trimestre": inf.trimestre, "anio": inf.anio, "repercutido": eur(inf.total_repercutido),
                      "soportado": eur(inf.total_soportado), "resultado": eur(res), "plazo": _fecha(inf.plazo),
                      "avisos": list(inf.avisos)}})
    elif t == Temas.CICLO_TERMINADO:
        ev.update(a=[], tipo="jornada", titulo="Fin de la jornada",
                  texto="Se acaba la jornada. Todo el equipo recoge.", detalle={"resumen": d.get("resumen", {})})
    else:
        return None
    return ev


class Trazador:
    """Graba el tráfico del bus. Es seguro leerlo desde otro hilo (servidor web)."""

    def __init__(self, bus: Bus, dia: Optional[date] = None) -> None:
        self.bus = bus
        self.eventos: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._fase: Optional[str] = None
        self._dia: Optional[str] = dia.isoformat() if dia else None
        bus.suscribir("*", self._on_mensaje)

    def _on_mensaje(self, msg: Mensaje) -> None:
        if msg.tema == Temas.CICLO_INICIADO:
            self._dia = msg.datos["hoy"].isoformat()
            self._fase = None
        elif msg.tema.startswith("fase."):
            self._fase = msg.datos["fase"]
        elif msg.tema == Temas.CICLO_TERMINADO:
            self._fase = None
        ev = describir(msg, self.bus)
        if ev is None:
            return
        with self._lock:
            ev.update(id=len(self.eventos), momento=msg.momento.isoformat(timespec="seconds"),
                      dia=self._dia, fase=self._fase)
            self.eventos.append(ev)

    def fijar_dia(self, dia: date) -> None:
        self._dia = dia.isoformat()

    def desde(self, n: int) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self.eventos[n:])


def texto_plano(ev: Dict[str, Any]) -> str:
    """Rellena los huecos {agente} con el nombre del puesto (para consola)."""
    txt = ev["texto"]
    for k, v in PUESTOS.items():
        txt = txt.replace("{" + k + "}", v)
    return txt


def participantes(orquestador) -> List[Dict[str, str]]:
    agentes = [{"id": "orquestador", "puesto": "Orquestador", "rol": "Reparte el trabajo del día por fases.", "tipo": "agente"}]
    agentes += [{"id": a.nombre, "puesto": PUESTOS.get(a.nombre, a.nombre), "rol": a.rol, "tipo": "agente"}
                for a in orquestador.agentes.values()]
    agentes += [{"id": k, "puesto": v, "rol": "", "tipo": "externo"} for k, v in EXTERNOS.items()]
    return agentes


def ahora_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
