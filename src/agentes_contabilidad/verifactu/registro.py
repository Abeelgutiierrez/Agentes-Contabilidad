"""Registros de facturación VeriFactu y su almacenamiento inalterable.

Cada factura emitida genera un *registro de alta*; cada anulación, un *registro
de anulación*. Todos se encadenan mediante la huella del registro anterior, de
modo que cualquier modificación posterior rompe la cadena y es detectable.

El almacén es SQLite en modo "solo añadir": no se exponen operaciones de
actualización ni borrado de registros (solo el estado de envío a la AEAT).
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from xml.sax.saxutils import escape

from ..models import Factura
from .huella import (
    formatear_fecha,
    formatear_fecha_hora_huso,
    formatear_importe,
    huella_alta,
    huella_anulacion,
)
from .qr import url_qr

SISTEMA_INFORMATICO = {
    "NombreRazon": "Agentes Contabilidad (proyecto open source)",
    "NombreSistemaInformatico": "AgentesContabilidad",
    "IdSistemaInformatico": "AC",
    "Version": "0.1.0",
    "NumeroInstalacion": "1",
    "TipoUsoPosibleSoloVerifactu": "S",
    "TipoUsoPosibleMultiOT": "N",
    "IndicadorMultiplesOT": "N",
}


@dataclass
class RegistroFacturacion:
    secuencia: int
    tipo_registro: str  # "alta" | "anulacion"
    nif_emisor: str
    nombre_emisor: str
    num_serie: str
    fecha_expedicion: date
    tipo_factura: Optional[str]
    cuota_total: Decimal
    importe_total: Decimal
    huella_anterior: Optional[str]
    huella: str
    fecha_hora_huso: datetime
    url_qr: Optional[str]
    xml: str
    estado_envio: str = "pendiente"  # pendiente | aceptado | rechazado
    factura_id: Optional[str] = None


class CadenaRota(Exception):
    pass


class SistemaVeriFactu:
    """Sistema Informático de Facturación (SIF) en modalidad VeriFactu."""

    def __init__(self, ruta_db: str = ":memory:", entorno: str = "pruebas", tz=None) -> None:
        # check_same_thread=False: el panel web lo consulta desde otros hilos
        # (siempre bajo el cerrojo de la sesión, nunca en paralelo).
        self.conn = sqlite3.connect(ruta_db, check_same_thread=False)
        self.entorno = entorno
        self.tz = tz or datetime.now().astimezone().tzinfo
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS registros (
                secuencia INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo_registro TEXT NOT NULL,
                nif_emisor TEXT NOT NULL,
                nombre_emisor TEXT NOT NULL,
                num_serie TEXT NOT NULL,
                fecha_expedicion TEXT NOT NULL,
                tipo_factura TEXT,
                cuota_total TEXT NOT NULL,
                importe_total TEXT NOT NULL,
                huella_anterior TEXT,
                huella TEXT NOT NULL UNIQUE,
                fecha_hora_huso TEXT NOT NULL,
                url_qr TEXT,
                xml TEXT NOT NULL,
                estado_envio TEXT NOT NULL DEFAULT 'pendiente',
                factura_id TEXT
            )"""
        )
        # Inalterabilidad a nivel de base de datos: prohibido borrar o tocar
        # cualquier campo salvo el estado de envío.
        self.conn.executescript(
            """
            CREATE TRIGGER IF NOT EXISTS no_borrar BEFORE DELETE ON registros
            BEGIN SELECT RAISE(ABORT, 'Los registros VeriFactu no se pueden borrar'); END;
            CREATE TRIGGER IF NOT EXISTS no_modificar BEFORE UPDATE ON registros
            WHEN NEW.huella != OLD.huella OR NEW.importe_total != OLD.importe_total
              OR NEW.num_serie != OLD.num_serie OR NEW.xml != OLD.xml
            BEGIN SELECT RAISE(ABORT, 'Los registros VeriFactu son inalterables'); END;
            """
        )
        self.conn.commit()

    # ------------------------------------------------------------------ util
    def _ahora(self) -> datetime:
        return datetime.now(self.tz).replace(microsecond=0)

    def ultimo(self) -> Optional[RegistroFacturacion]:
        fila = self.conn.execute("SELECT * FROM registros ORDER BY secuencia DESC LIMIT 1").fetchone()
        return self._fila(fila) if fila else None

    def registros(self) -> List[RegistroFacturacion]:
        return [self._fila(f) for f in self.conn.execute("SELECT * FROM registros ORDER BY secuencia")]

    def existe_alta(self, nif: str, num_serie: str) -> bool:
        q = "SELECT 1 FROM registros WHERE tipo_registro='alta' AND nif_emisor=? AND num_serie=?"
        return self.conn.execute(q, (nif, num_serie)).fetchone() is not None

    def _fila(self, f) -> RegistroFacturacion:
        return RegistroFacturacion(
            secuencia=f[0], tipo_registro=f[1], nif_emisor=f[2], nombre_emisor=f[3],
            num_serie=f[4], fecha_expedicion=date.fromisoformat(f[5]), tipo_factura=f[6],
            cuota_total=Decimal(f[7]), importe_total=Decimal(f[8]), huella_anterior=f[9],
            huella=f[10], fecha_hora_huso=datetime.fromisoformat(f[11]), url_qr=f[12],
            xml=f[13], estado_envio=f[14], factura_id=f[15],
        )

    def _insertar(self, r: RegistroFacturacion) -> RegistroFacturacion:
        cur = self.conn.execute(
            """INSERT INTO registros (tipo_registro, nif_emisor, nombre_emisor, num_serie,
               fecha_expedicion, tipo_factura, cuota_total, importe_total, huella_anterior,
               huella, fecha_hora_huso, url_qr, xml, estado_envio, factura_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                r.tipo_registro, r.nif_emisor, r.nombre_emisor, r.num_serie,
                r.fecha_expedicion.isoformat(), r.tipo_factura, str(r.cuota_total),
                str(r.importe_total), r.huella_anterior, r.huella,
                formatear_fecha_hora_huso(r.fecha_hora_huso), r.url_qr, r.xml,
                r.estado_envio, r.factura_id,
            ),
        )
        self.conn.commit()
        r.secuencia = cur.lastrowid
        return r

    # --------------------------------------------------------------- altas
    def registrar_alta(self, factura: Factura, momento: Optional[datetime] = None) -> RegistroFacturacion:
        if self.existe_alta(factura.emisor_nif, factura.num_serie):
            raise ValueError(f"La factura {factura.num_serie} ya tiene registro de alta")
        momento = momento or self._ahora()
        anterior = self.ultimo()
        h_ant = anterior.huella if anterior else None
        h = huella_alta(
            factura.emisor_nif, factura.num_serie, factura.fecha, factura.tipo.value,
            factura.cuota_total, factura.importe_total, h_ant, momento,
        )
        qr = url_qr(factura.emisor_nif, factura.num_serie, factura.fecha, factura.importe_total, self.entorno)
        xml = xml_registro_alta(factura, anterior, h, momento)
        reg = RegistroFacturacion(
            secuencia=0, tipo_registro="alta", nif_emisor=factura.emisor_nif,
            nombre_emisor=factura.emisor_nombre, num_serie=factura.num_serie,
            fecha_expedicion=factura.fecha, tipo_factura=factura.tipo.value,
            cuota_total=factura.cuota_total, importe_total=factura.importe_total,
            huella_anterior=h_ant, huella=h, fecha_hora_huso=momento, url_qr=qr,
            xml=xml, factura_id=factura.id,
        )
        return self._insertar(reg)

    def registrar_anulacion(self, factura: Factura, momento: Optional[datetime] = None) -> RegistroFacturacion:
        if not self.existe_alta(factura.emisor_nif, factura.num_serie):
            raise ValueError(f"No existe alta de {factura.num_serie} que anular")
        momento = momento or self._ahora()
        anterior = self.ultimo()
        h_ant = anterior.huella if anterior else None
        h = huella_anulacion(factura.emisor_nif, factura.num_serie, factura.fecha, h_ant, momento)
        xml = xml_registro_anulacion(factura, anterior, h, momento)
        reg = RegistroFacturacion(
            secuencia=0, tipo_registro="anulacion", nif_emisor=factura.emisor_nif,
            nombre_emisor=factura.emisor_nombre, num_serie=factura.num_serie,
            fecha_expedicion=factura.fecha, tipo_factura=None,
            cuota_total=Decimal(0), importe_total=Decimal(0), huella_anterior=h_ant,
            huella=h, fecha_hora_huso=momento, url_qr=None, xml=xml, factura_id=factura.id,
        )
        return self._insertar(reg)

    def marcar_envio(self, secuencia: int, estado: str) -> None:
        self.conn.execute("UPDATE registros SET estado_envio=? WHERE secuencia=?", (estado, secuencia))
        self.conn.commit()

    def pendientes_envio(self) -> List[RegistroFacturacion]:
        return [r for r in self.registros() if r.estado_envio == "pendiente"]

    # ---------------------------------------------------------- integridad
    def verificar_cadena(self) -> List[str]:
        """Recalcula todas las huellas. Devuelve lista de errores (vacía = OK)."""
        errores: List[str] = []
        previa: Optional[str] = None
        for r in self.registros():
            if r.huella_anterior != previa:
                errores.append(f"Registro {r.secuencia} ({r.num_serie}): huella anterior no coincide")
            if r.tipo_registro == "alta":
                calc = huella_alta(r.nif_emisor, r.num_serie, r.fecha_expedicion, r.tipo_factura or "",
                                   r.cuota_total, r.importe_total, r.huella_anterior, r.fecha_hora_huso)
            else:
                calc = huella_anulacion(r.nif_emisor, r.num_serie, r.fecha_expedicion,
                                        r.huella_anterior, r.fecha_hora_huso)
            if calc != r.huella:
                errores.append(f"Registro {r.secuencia} ({r.num_serie}): huella alterada")
            previa = r.huella
        return errores


# ------------------------------------------------------------------- XML
# Estructura basada en SuministroLR.xsd / SuministroInformacion.xsd de la AEAT.
# IMPORTANTE: validar contra los XSD oficiales vigentes antes de producción.
NS_SUM = "https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/tike/cont/ws/SuministroLR.xsd"
NS_SUM1 = "https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/tike/cont/ws/SuministroInformacion.xsd"


def _t(tag: str, valor) -> str:
    return f"<sum1:{tag}>{escape(str(valor))}</sum1:{tag}>"


def _encadenamiento(anterior: Optional[RegistroFacturacion]) -> str:
    if anterior is None:
        return "<sum1:Encadenamiento>" + _t("PrimerRegistro", "S") + "</sum1:Encadenamiento>"
    return (
        "<sum1:Encadenamiento><sum1:RegistroAnterior>"
        + _t("IDEmisorFactura", anterior.nif_emisor)
        + _t("NumSerieFactura", anterior.num_serie)
        + _t("FechaExpedicionFactura", formatear_fecha(anterior.fecha_expedicion))
        + _t("Huella", anterior.huella)
        + "</sum1:RegistroAnterior></sum1:Encadenamiento>"
    )


def _sistema() -> str:
    return "<sum1:SistemaInformatico>" + "".join(_t(k, v) for k, v in SISTEMA_INFORMATICO.items()) + "</sum1:SistemaInformatico>"


def xml_registro_alta(f: Factura, anterior: Optional[RegistroFacturacion], huella: str, momento: datetime) -> str:
    desglose = "".join(
        "<sum1:DetalleDesglose>"
        + _t("Impuesto", "01") + _t("ClaveRegimen", "01") + _t("CalificacionOperacion", "S1")
        + _t("TipoImpositivo", formatear_importe(tipo))
        + _t("BaseImponibleOimporteNoSujeto", formatear_importe(v["base"]))
        + _t("CuotaRepercutida", formatear_importe(v["cuota"]))
        + "</sum1:DetalleDesglose>"
        for tipo, v in sorted(f.desglose_iva().items())
    )
    destinatario = ""
    if f.receptor_nif:
        destinatario = (
            "<sum1:Destinatarios><sum1:IDDestinatario>"
            + _t("NombreRazon", f.receptor_nombre or "") + _t("NIF", f.receptor_nif)
            + "</sum1:IDDestinatario></sum1:Destinatarios>"
        )
    descripcion = "; ".join(l.descripcion for l in f.lineas)[:500] or "Prestación de servicios"
    return (
        "<sum1:RegistroAlta>"
        + _t("IDVersion", "1.0")
        + "<sum1:IDFactura>" + _t("IDEmisorFactura", f.emisor_nif) + _t("NumSerieFactura", f.num_serie)
        + _t("FechaExpedicionFactura", formatear_fecha(f.fecha)) + "</sum1:IDFactura>"
        + _t("NombreRazonEmisor", f.emisor_nombre)
        + _t("TipoFactura", f.tipo.value)
        + _t("DescripcionOperacion", descripcion)
        + destinatario
        + "<sum1:Desglose>" + desglose + "</sum1:Desglose>"
        + _t("CuotaTotal", formatear_importe(f.cuota_total))
        + _t("ImporteTotal", formatear_importe(f.importe_total))
        + _encadenamiento(anterior)
        + _sistema()
        + _t("FechaHoraHusoGenRegistro", formatear_fecha_hora_huso(momento))
        + _t("TipoHuella", "01")
        + _t("Huella", huella)
        + "</sum1:RegistroAlta>"
    )


def xml_registro_anulacion(f: Factura, anterior: Optional[RegistroFacturacion], huella: str, momento: datetime) -> str:
    return (
        "<sum1:RegistroAnulacion>"
        + _t("IDVersion", "1.0")
        + "<sum1:IDFactura>" + _t("IDEmisorFacturaAnulada", f.emisor_nif)
        + _t("NumSerieFacturaAnulada", f.num_serie)
        + _t("FechaExpedicionFacturaAnulada", formatear_fecha(f.fecha)) + "</sum1:IDFactura>"
        + _encadenamiento(anterior)
        + _sistema()
        + _t("FechaHoraHusoGenRegistro", formatear_fecha_hora_huso(momento))
        + _t("TipoHuella", "01")
        + _t("Huella", huella)
        + "</sum1:RegistroAnulacion>"
    )


def sobre_suministro(nif_obligado: str, nombre: str, registros: List[RegistroFacturacion]) -> str:
    """Envuelve registros en el mensaje RegFactuSistemaFacturacion (SOAP body)."""
    cuerpo = "".join(f"<sum:RegistroFactura>{r.xml}</sum:RegistroFactura>" for r in registros)
    return (
        f'<sum:RegFactuSistemaFacturacion xmlns:sum="{NS_SUM}" xmlns:sum1="{NS_SUM1}">'
        "<sum:Cabecera><sum1:ObligadoEmision>"
        + _t("NombreRazon", nombre) + _t("NIF", nif_obligado)
        + "</sum1:ObligadoEmision></sum:Cabecera>"
        + cuerpo
        + "</sum:RegFactuSistemaFacturacion>"
    )
