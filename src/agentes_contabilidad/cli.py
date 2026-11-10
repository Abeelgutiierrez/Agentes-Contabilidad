"""Línea de comandos: ``agentes-conta <comando>``."""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="agentes-conta", description="Ecosistema de agentes contables (VeriFactu)")
    p.add_argument("-v", "--verbose", action="store_true", help="Muestra la conversación entre agentes")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("demo", help="Ejecuta la demostración con datos de ejemplo")
    sub.add_parser("agentes", help="Lista los agentes y su rol")

    c = sub.add_parser("ciclo", help="Ejecuta un ciclo diario completo")
    c.add_argument("--config", required=True)
    c.add_argument("--fecha", help="AAAA-MM-DD (por defecto hoy)")
    c.add_argument("--exportar", help="Ruta JSON donde volcar el estado")

    e = sub.add_parser("emitir", help="Emite una factura de venta VeriFactu desde un JSON")
    e.add_argument("--config", required=True)
    e.add_argument("--factura", required=True, help="JSON: {cliente_nif, cliente_nombre, fecha?, serie?, lineas:[...]}")

    v = sub.add_parser("verificar", help="Verifica la integridad de la cadena VeriFactu")
    v.add_argument("--db", required=True, help="Ruta a verifactu.sqlite")

    w = sub.add_parser("web", help="Abre La Oficina: el panel visual con los agentes trabajando")
    gw = w.add_mutually_exclusive_group(required=True)
    gw.add_argument("--demo", action="store_true", help="Con los datos de ejemplo de la cafetería")
    gw.add_argument("--config", help="Con tu configuración")
    w.add_argument("--puerto", type=int, default=8765)
    w.add_argument("--no-abrir", action="store_true", help="No abrir el navegador automáticamente")

    t = sub.add_parser("traza", help="Guarda el tráfico entre agentes en un JSON (para el panel sin servidor)")
    gt = t.add_mutually_exclusive_group(required=True)
    gt.add_argument("--demo", action="store_true")
    gt.add_argument("--config")
    t.add_argument("--fecha", help="AAAA-MM-DD (con --config)")
    t.add_argument("-o", "--salida", required=True, help="Fichero .json o .js (el .js lo carga el panel sin servidor)")

    q = sub.add_parser("preguntar", help="Pregunta en lenguaje natural (requiere ANTHROPIC_API_KEY)")
    q.add_argument("--config", required=True)
    q.add_argument("pregunta")

    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING,
                        format="%(name)-28s %(message)s")

    if a.cmd == "demo":
        from .demo import ejecutar

        ejecutar()
    elif a.cmd == "agentes":
        from .agents.orquestador import AGENTES_POR_DEFECTO

        for cls in AGENTES_POR_DEFECTO:
            print(f"{cls.nombre:<18} fases={','.join(cls.fases) or '-':<14} {cls.rol}")
    elif a.cmd == "ciclo":
        from .config import crear_ecosistema

        orq = crear_ecosistema(a.config)
        orq.ciclo(date.fromisoformat(a.fecha) if a.fecha else None)
        print(orq.panel())
        if a.exportar:
            orq.ctx.libro.exportar_json(a.exportar)
    elif a.cmd == "emitir":
        import json
        from decimal import Decimal

        from .config import crear_ecosistema
        from .models import Direccion, Factura, LineaFactura

        with open(a.factura, encoding="utf-8") as fh:
            d = json.load(fh)
        orq = crear_ecosistema(a.config)
        f = Factura(
            numero="", serie=d.get("serie", ""), fecha=date.fromisoformat(d["fecha"]) if d.get("fecha") else date.today(),
            direccion=Direccion.EMITIDA, emisor_nif="", emisor_nombre="",
            receptor_nif=d.get("cliente_nif"), receptor_nombre=d.get("cliente_nombre"),
            lineas=[LineaFactura(l["descripcion"], Decimal(str(l.get("cantidad", 1))), Decimal(str(l["precio_unitario"])),
                                 Decimal(str(l.get("tipo_iva", 21)))) for l in d["lineas"]],
        )
        if orq.emitir_factura(f):
            reg = orq.ctx.verifactu.ultimo()
            print(f"Emitida {f.num_serie}: {f.importe_total} €\nHuella: {reg.huella}\nQR: {reg.url_qr}")
        else:
            print(orq.panel())
            return 1
    elif a.cmd == "verificar":
        from .verifactu.registro import SistemaVeriFactu

        vf = SistemaVeriFactu(a.db)
        errores = vf.verificar_cadena()
        print(f"{len(vf.registros())} registros. " + ("Cadena íntegra ✔" if not errores else "ERRORES:"))
        for e in errores:
            print("  ✘", e)
        return 1 if errores else 0
    elif a.cmd == "web":
        from .web.servidor import arrancar

        if a.demo:
            from .demo import emitir_historicas, preparar

            orq, trabajo = preparar()
            # Historia previa (ventas de septiembre y octubre): se ve al abrir el panel
            arrancar(orq, "demo", trabajo, a.puerto, not a.no_abrir,
                     preparar=lambda s: emitir_historicas(orq, s.trazador.fijar_dia))
        else:
            from .config import crear_ecosistema

            arrancar(crear_ecosistema(a.config), "real", None, a.puerto, not a.no_abrir)
    elif a.cmd == "traza":
        from .web.traza import guardar_traza

        n = guardar_traza(a.salida, demo=a.demo, config=a.config, fecha=a.fecha)
        print(f"{n} eventos guardados en {a.salida}")
    elif a.cmd == "preguntar":
        from .config import crear_ecosistema

        orq = crear_ecosistema(a.config)
        orq.ciclo()
        print(orq.preguntar(a.pregunta))
    return 0


if __name__ == "__main__":
    sys.exit(main())
