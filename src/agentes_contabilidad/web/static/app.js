/* Agentes Contabilidad — centro de control.
 *
 * Dos modos:
 *  - En directo: servido por `agentes-conta web`, lee /api/eventos y permite
 *    ejecutar jornadas, emitir facturas y marcar avisos como hechos.
 *  - Demostración: sin servidor, reproduce window.TRAZA_DEMO
 *    (generado con `agentes-conta traza --demo -o traza_demo.js`).
 *
 * Sin dependencias: HTML, CSS y un SVG animado.
 */
(function () {
  "use strict";

  const NS = "http://www.w3.org/2000/svg";
  const $ = (s, r = document) => r.querySelector(s);
  const reducido = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);

  // ------------------------------------------------------------- el equipo
  const AGENTES = {
    orquestador:      { nombre: "Olga",   rol: "Coordinación",          color: "#0e7c66" },
    recepcion:        { nombre: "Rosa",   rol: "Recepción", color: "#4f8dff", x: 330, y: 140 },
    conciliador:      { nombre: "Carlos", rol: "Conciliación", color: "#1fa9c0", x: 330, y: 300 },
    emisor_verifactu: { nombre: "Vera",   rol: "Emisión VeriFactu",     color: "#22b47b", x: 330, y: 460 },
    revisor:          { nombre: "Rubén",  rol: "Control de calidad",    color: "#7b8aa3", x: 570, y: 64 },
    detective:        { nombre: "Dani",   rol: "Facturas que faltan",   color: "#f07b2c", x: 570, y: 220 },
    cobros:           { nombre: "Coral",  rol: "Cobros",                color: "#e2558f", x: 570, y: 410 },
    reclamador:       { nombre: "Ramón",  rol: "Reclamaciones",         color: "#8f6cf0", x: 810, y: 220 },
    fiscal:           { nombre: "Fátima", rol: "Impuestos",             color: "#6574f0", x: 810, y: 64 },
  };
  const EXTERNOS = {
    buzon:       { nombre: "Buzón",       sub: "Facturas recibidas", x: 100,  y: 140, ico: "bandeja" },
    banco:       { nombre: "Banco",       sub: "Movimientos",         x: 100,  y: 300, ico: "banco" },
    tu:          { nombre: "Tus ventas",  sub: "TPV y facturas",    x: 100,  y: 460, ico: "ticket" },
    proveedores: { nombre: "Proveedores", sub: "Emails enviados",     x: 1010, y: 220, ico: "camion" },
    clientes:    { nombre: "Clientes",    sub: "Facturas y avisos",   x: 1010, y: 410, ico: "personas" },
    aeat:        { nombre: "Hacienda",    sub: "AEAT · VeriFactu",    x: 1010, y: 530, ico: "edificio" },
  };
  // Conexiones habituales: se dibujan desde el principio
  const RUTAS = [
    ["buzon", "recepcion"], ["banco", "conciliador"], ["tu", "emisor_verifactu"],
    ["recepcion", "conciliador"], ["recepcion", "detective"], ["recepcion", "revisor"],
    ["conciliador", "detective"], ["detective", "reclamador"], ["reclamador", "proveedores"],
    ["emisor_verifactu", "conciliador"], ["emisor_verifactu", "cobros"], ["emisor_verifactu", "aeat"],
    ["cobros", "clientes"],
  ];

  const TIPOS = {
    documento: { nombre: "Documento", v: "--t-documento" },
    banco:     { nombre: "Banco",     v: "--t-banco" },
    falta:     { nombre: "Falta",     v: "--t-falta" },
    email:     { nombre: "Email",     v: "--t-email" },
    verifactu: { nombre: "VeriFactu", v: "--t-verifactu" },
    alerta:    { nombre: "Error",     v: "--t-alerta" },
    aviso:     { nombre: "Aviso",     v: "--t-aviso" },
    fiscal:    { nombre: "Impuestos", v: "--t-fiscal" },
    exito:     { nombre: "Resuelto",  v: "--t-exito" },
    fase:      { nombre: "Fase",      v: "--t-fase" },
    jornada:   { nombre: "Jornada",   v: "--t-fase" },
    sistema:   { nombre: "Sistema",   v: "--t-fase" },
  };
  const colorTipo = (t) => `var(${(TIPOS[t] || TIPOS.sistema).v})`;

  // Hora simulada según la fase del día
  const RELOJ = { inicio: "08:00", ingesta: "08:30", banco: "09:30", deteccion: "10:30", reclamaciones: "11:30",
    cobros: "12:30", envio_aeat: "13:30", revision: "16:00", informe: "17:30", fin: "19:00" };

  // Qué hacer con cada tipo de aviso (lenguaje de dueño de negocio)
  const QUE_HACER = {
    FACTURA_DUPLICADA: "No tienes que hacer nada: Rosa ha descartado la copia para que no se contabilice dos veces.",
    DOC_NO_RECONOCIDO: "Si era una factura, comprueba que el documento se lee bien (PDF con texto, no una foto borrosa).",
    TOTAL_INCOHERENTE: "Pide al proveedor una factura corregida antes de pagarla: los importes no cuadran.",
    FALTANTE_ESCALADA: "Busca el justificante de este pago o añade el email del proveedor para que Ramón pueda reclamarlo.",
    EMISION_RECHAZADA: "Revisa los datos del cliente (sobre todo el NIF) y vuelve a crear la factura.",
    COBRO_VENCIDO: "Coral ya ha enviado un recordatorio al cliente. Si sigue sin pagar, llámale.",
    RECEPTOR_INCORRECTO: "La factura no está a tu nombre: pide al proveedor que la rehaga con tu NIF.",
    SIN_NIF_RECEPTOR: "Pide al proveedor una factura completa con tu NIF para poder deducir el IVA.",
    NIF_PROVEEDOR_INVALIDO: "Confirma el NIF con el proveedor: tal como está, Hacienda no lo daría por bueno.",
    IVA_INUSUAL: "Comprueba el tipo de IVA con el proveedor o con tu asesoría.",
    CADENA_VERIFACTU_ROTA: "Avisa a tu asesoría: alguien ha modificado un registro de facturación.",
    AEAT_RECHAZO: "Hacienda ha rechazado un registro. Revisa los datos de la factura y vuelve a enviarla.",
  };

  // ----------------------------------------------------------------- estado
  const E = {
    modo: "cargando", info: null, eventos: [], cursor: 0, reproduciendo: false, velocidad: 1,
    generacion: 0, base: null, d: null, filtro: null, ocupado: false, ia: false, kpiPrevio: {},
  };

  function estadoVacio(base) {
    const m = { faltantes: new Map(), incidencias: new Map(), cadena: new Map(), cobrar: new Map(), informe: null, integra: true };
    if (base) {
      (base.faltantes || []).forEach((f) => m.faltantes.set(f.id, f));
      (base.incidencias || []).forEach((i) => m.incidencias.set(i.id, i));
      ((base.verifactu && base.verifactu.cadena) || []).forEach((r) => m.cadena.set(r.numero, r));
      (base.por_cobrar || []).forEach((f) => m.cobrar.set(f.numero, f));
      m.informe = base.informe || null;
      m.integra = base.verifactu ? base.verifactu.integra : true;
    }
    return { mesa: m, cuenta: {}, rutas: new Map(), dia: null, fase: null, hechas: new Set(),
      fin: false, trabajando: new Set(), enJornada: false, hoy: { docs: 0, movs: 0, emails: 0, faltas: 0, emitidas: 0 } };
  }

  // -------------------------------------------------------------- utilidades
  function el(tag, attrs, padre) {
    const n = document.createElementNS(NS, tag);
    if (attrs) for (const k in attrs) n.setAttribute(k, attrs[k]);
    if (padre) padre.appendChild(n);
    return n;
  }
  const esperar = (ms) => new Promise((r) => setTimeout(r, ms));
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const nodo = (id) => AGENTES[id] || EXTERNOS[id] || null;
  const nombre = (id) => (id === "tu" ? "Tú" : (AGENTES[id] || EXTERNOS[id] || { nombre: id }).nombre);
  const rolDe = (id) => (AGENTES[id] ? AGENTES[id].rol : EXTERNOS[id] ? EXTERNOS[id].sub : "");
  const iniciales = (id) => (AGENTES[id] ? AGENTES[id].nombre.slice(0, 2).toUpperCase() : "");
  // 1210.5 -> "1.210,50 €" (Intl no agrupa los miles en números de 4 cifras en español)
  const eur = (n) => {
    const v = Number(n) || 0, [e, dec] = Math.abs(v).toFixed(2).split(".");
    return `${v < 0 ? "-" : ""}${e.replace(/\B(?=(\d{3})+(?!\d))/g, ".")},${dec} €`;
  };
  const plural = (n, s, p) => `${n} ${n === 1 ? s : p || s + "s"}`;
  const fechaLarga = (iso) => {
    if (!iso) return "";
    const s = new Date(iso + "T12:00:00").toLocaleDateString("es-ES", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
    return s.charAt(0).toUpperCase() + s.slice(1);
  };
  const fechaCorta = (iso) => new Date(iso + "T12:00:00").toLocaleDateString("es-ES", { day: "numeric", month: "short" });
  const diasHasta = (iso, desde) => Math.round((new Date(iso + "T12:00:00") - new Date((desde || iso) + "T12:00:00")) / 864e5);
  const textoEv = (ev) => esc(ev.texto).replace(/\{(\w+)\}/g, (_, id) => `<b>${esc(nombre(id))}</b>`);

  function avatarHtml(id, tam) {
    tam = tam || 28;
    const a = AGENTES[id];
    if (a) return `<span class="av" style="background:${a.color};width:${tam}px;height:${tam}px">${esc(iniciales(id))}</span>`;
    const x = EXTERNOS[id];
    const fondo = id === "tu" ? "var(--accent)" : "#5b6b84";
    return `<span class="av" style="background:${fondo};width:${tam}px;height:${tam}px">${x ? icono(x.ico, "#fff") : ""}</span>`;
  }

  function icono(n, color) {
    const s = `fill="none" stroke="${color || "currentColor"}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"`;
    const p = {
      bandeja: `<path ${s} d="M2.5 9.5h3l1 2h3l1-2h3M2.5 9.5 4.5 3.5h7l2 6v3h-11z"/>`,
      banco: `<path ${s} d="M2.5 6 8 3l5.5 3M3.5 6.5v5M6.5 6.5v5M9.5 6.5v5M12.5 6.5v5M2.5 13h11"/>`,
      ticket: `<path ${s} d="M4 2.5h8v11l-2-1.2-2 1.2-2-1.2-2 1.2zM6 6h4M6 8.5h4"/>`,
      camion: `<path ${s} d="M1.8 4.5h7.5v6H1.8zM9.3 6.5h2.6l2.3 2.3v1.7H9.3"/><circle ${s} cx="4.5" cy="11.5" r="1.3"/><circle ${s} cx="11.5" cy="11.5" r="1.3"/>`,
      personas: `<circle ${s} cx="6" cy="5.5" r="2.2"/><path ${s} d="M2.2 13c.5-2.3 2-3.5 3.8-3.5s3.3 1.2 3.8 3.5M10.5 3.5a2 2 0 0 1 0 4M12 9.8c1 .5 1.7 1.5 2 3.2"/>`,
      edificio: `<path ${s} d="M2.5 6 8 3l5.5 3H2.5M4 6.5v5M8 6.5v5M12 6.5v5M2.5 13h11"/>`,
    }[n] || "";
    return `<svg viewBox="0 0 16 16" aria-hidden="true">${p}</svg>`;
  }

  function tostada(msg, mal) {
    const t = $("#tostada");
    t.textContent = msg;
    t.className = "tostada" + (mal ? " mal" : "");
    t.hidden = false;
    clearTimeout(tostada._t);
    tostada._t = setTimeout(() => (t.hidden = true), 3800);
  }

  // ------------------------------------------------------------------ mapa
  const M = { bordes: new Map(), nodos: {} };
  const tam = (id) => (AGENTES[id] ? { hw: 92, hh: 30 } : { hw: 80, hh: 28 });

  function camino(a, b) {
    const A = nodo(a), B = nodo(b);
    if (!A || !B || A.x === undefined || B.x === undefined) return null;
    const ta = tam(a), tb = tam(b);
    const dx = B.x - A.x, dy = B.y - A.y;
    if (Math.abs(dx) > 40) {
      const s = Math.sign(dx);
      const sx = A.x + s * ta.hw, ex = B.x - s * tb.hw, m = (ex - sx) / 2;
      return `M${sx},${A.y} C${sx + m},${A.y} ${ex - m},${B.y} ${ex},${B.y}`;
    }
    const s = Math.sign(dy) || 1;
    const sy = A.y + s * ta.hh, ey = B.y - s * tb.hh, m = (ey - sy) / 2;
    return `M${A.x},${sy} C${A.x},${sy + m} ${B.x},${ey - m} ${B.x},${ey}`;
  }

  function borde(de, a) {
    const k = de + ">" + a;
    if (M.bordes.has(k)) return M.bordes.get(k);
    const d = camino(de, a);
    if (!d) return null;
    const p = el("path", { class: "borde", d }, M.capaBordes);
    M.bordes.set(k, p);
    return p;
  }

  function construirMapa() {
    const svg = $("#mapa");
    svg.innerHTML = `
      <defs>
        <pattern id="puntos" width="22" height="22" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="1" style="fill:var(--map-dot)"/></pattern>
        <filter id="brillo" x="-200%" y="-200%" width="500%" height="500%"><feGaussianBlur stdDeviation="3.2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
      </defs>
      <rect width="1100" height="580" fill="url(#puntos)"/>
      <text class="columna-txt" x="100" y="22" text-anchor="middle">ENTRADAS</text>
      <text class="columna-txt" x="570" y="22" text-anchor="middle">TU EQUIPO</text>
      <text class="columna-txt" x="1010" y="22" text-anchor="middle">SALIDAS</text>
      <g id="capa-bordes"></g><g id="capa-nodos"></g><g id="capa-pulsos"></g><g id="capa-globos"></g>`;
    M.svg = svg;
    M.capaBordes = $("#capa-bordes", svg);
    M.capaNodos = $("#capa-nodos", svg);
    M.capaPulsos = $("#capa-pulsos", svg);
    M.capaGlobos = $("#capa-globos", svg);
    RUTAS.forEach(([a, b]) => borde(a, b));

    for (const id in EXTERNOS) {
      const x = EXTERNOS[id];
      const g = el("g", { class: "nodo ext", transform: `translate(${x.x},${x.y})`, tabindex: "0", role: "button", "aria-label": `${x.nombre}: ver su actividad` }, M.capaNodos);
      g.innerHTML = `<rect class="fondo" x="-80" y="-28" width="160" height="56" rx="28"/>
        <circle class="anillo" cx="-52" cy="0" r="22" style="stroke:var(--accent)"/>
        <circle class="ico-fondo" cx="-52" cy="0" r="18"/>
        <g transform="translate(-61,-9) scale(1.15)" style="color:var(--map-ink)">${icono(x.ico).replace("<svg", '<svg width="16" height="16"')}</g>
        <text class="nombre" x="-26" y="-3">${esc(x.nombre)}</text><text class="rol" x="-26" y="13">${esc(x.sub)}</text>`;
      enlazarNodo(g, id);
      M.nodos[id] = g;
    }
    for (const id in AGENTES) {
      const a = AGENTES[id];
      if (a.x === undefined) continue;
      const g = el("g", { class: "nodo", transform: `translate(${a.x},${a.y})`, tabindex: "0", role: "button", "aria-label": `${a.nombre}, ${a.rol}` }, M.capaNodos);
      g.innerHTML = `<rect class="fondo" x="-92" y="-30" width="184" height="60" rx="14"/>
        <circle class="anillo" cx="-62" cy="0" r="22" style="stroke:${a.color}"/>
        <circle cx="-62" cy="0" r="17" style="fill:${a.color}"/>
        <text class="ini" x="-62" y="4.2" text-anchor="middle">${esc(iniciales(id))}</text>
        <text class="nombre" x="-36" y="-3">${esc(a.nombre)}</text><text class="rol" x="-36" y="13">${esc(a.rol)}</text>
        <circle class="halo-punto" cx="78" cy="-15" r="3.5" stroke-width="1.5"/><circle class="punto" cx="78" cy="-15" r="3.5"/>
        <g class="aviso-rojo" transform="translate(-80,-24)"><circle r="7.5" style="fill:var(--t-alerta)"/><text y="3.8" text-anchor="middle" font-size="10" font-weight="800" fill="#fff">!</text></g>`;
      enlazarNodo(g, id);
      M.nodos[id] = g;
    }
  }

  function enlazarNodo(g, id) {
    g.addEventListener("click", () => abrirPersona(id));
    g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); abrirPersona(id); } });
  }

  // Globo con lo que acaba de hacer un agente
  const globos = {};
  function globo(id, txt, tipo, ms) {
    const n = nodo(id);
    if (!n || n.x === undefined || !txt) return;
    if (globos[id]) globos[id].remove();
    const corto = txt.length > 32 ? txt.slice(0, 31) + "…" : txt;
    const ancho = Math.max(70, corto.length * 6.5 + 34);
    const x = Math.min(Math.max(n.x, ancho / 2 + 6), 1100 - ancho / 2 - 6);
    const y = n.y - (AGENTES[id] ? 48 : 46);
    const fuera = el("g", { class: "globo", transform: `translate(${x},${y})` }, M.capaGlobos);
    const g = el("g", { class: "entra" }, fuera);
    el("rect", { x: -ancho / 2, y: -13, width: ancho, height: 26, rx: 13 }, g);
    el("circle", { cx: -ancho / 2 + 14, cy: 0, r: 4, style: `fill:${colorTipo(tipo)}` }, g);
    const t = el("text", { x: -ancho / 2 + 24, y: 4 }, g);
    t.textContent = corto;
    globos[id] = fuera;
    setTimeout(() => { if (globos[id] === fuera) { fuera.remove(); delete globos[id]; } }, ms);
  }
  function limpiarGlobos() { for (const k in globos) { globos[k].remove(); delete globos[k]; } }

  // Pulso de luz que recorre la conexión
  function pulso(de, a, tipo, dur, gen) {
    return new Promise((fin) => {
      const p = borde(de, a);
      if (!p) return fin();
      const largo = p.getTotalLength();
      const color = colorTipo(tipo);
      p.classList.add("activo");
      p.style.stroke = color;
      clearTimeout(p._t);
      p._t = setTimeout(() => { p.classList.remove("activo"); p.style.stroke = ""; }, dur + 700);
      const g = el("g", { class: "pulso" }, M.capaPulsos);
      const cola = [0.09, 0.06, 0.03].map((d, i) => ({ d, c: el("circle", { r: 2.4 + i * 0.6, style: `fill:${color}`, opacity: 0.25 + i * 0.2 }, g) }));
      const cabeza = el("circle", { r: 5, style: `fill:${color}`, filter: "url(#brillo)" }, g);
      if (reducido) dur = 1;
      const t0 = performance.now();
      const paso = (ahora) => {
        if (gen !== E.generacion) { g.remove(); return fin(); }
        const t = Math.min(1, (ahora - t0) / dur);
        const e = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
        const pt = p.getPointAtLength(e * largo);
        cabeza.setAttribute("cx", pt.x); cabeza.setAttribute("cy", pt.y);
        cola.forEach(({ d, c }) => { const q = p.getPointAtLength(Math.max(0, e - d) * largo); c.setAttribute("cx", q.x); c.setAttribute("cy", q.y); });
        if (t < 1) requestAnimationFrame(paso);
        else { g.remove(); fin(); }
      };
      requestAnimationFrame(paso);
    });
  }

  // Aviso que sube del agente hacia "Necesita tu atención"
  function subida(de, tipo) {
    const n = nodo(de);
    if (!n || n.x === undefined || reducido) return;
    const g = el("g", { class: "subida", transform: `translate(${n.x + 70},${n.y - 26})` }, M.capaPulsos);
    g.innerHTML = `<rect x="-9" y="-9" width="18" height="18" rx="5" style="fill:${colorTipo(tipo)}"/><path d="M-4 -2h8M-4 2.5h5" stroke="#fff" stroke-width="1.6" stroke-linecap="round"/>`;
    g.animate([{ transform: `translate(${n.x + 70}px,${n.y - 26}px)`, opacity: 1 }, { transform: `translate(${n.x + 96}px,${n.y - 70}px)`, opacity: 0 }],
      { duration: 1100, easing: "cubic-bezier(.2,.7,.3,1)" }).onfinish = () => g.remove();
  }

  function recibe(id) {
    const g = M.nodos[id];
    if (!g || reducido) return;
    g.classList.remove("recibe"); void g.getBBox(); g.classList.add("recibe");
  }

  // ------------------------------------------------ estado derivado (sin animar)
  function aplicar(ev) {
    const d = E.d, m = d.mesa, det = ev.detalle || {};
    const cuenta = (id, k) => { (d.cuenta[id] = d.cuenta[id] || { env: 0, rec: 0 })[k]++; };
    if (ev.dia && ev.dia !== d.dia) { d.dia = ev.dia; d.hoy = { docs: 0, movs: 0, emails: 0, faltas: 0, emitidas: 0 }; }

    if (ev.tema === "ciclo.iniciado") { d.enJornada = true; d.fin = false; d.fase = null; d.hechas = new Set(); d.trabajando = new Set(); }
    else if (ev.tema === "ciclo.terminado") { d.enJornada = false; d.fin = true; d.fase = null; d.trabajando = new Set(); E.info.fases.forEach((f) => d.hechas.add(f.id)); }
    else if (ev.tipo === "fase") {
      if (d.enJornada) { if (d.fase) d.hechas.add(d.fase); d.fase = det.fase; }
      d.trabajando = new Set(ev.a);
    }

    if (ev.tipo !== "jornada") {
      cuenta(ev.de, "env");
      (ev.a || []).forEach((a) => {
        cuenta(a, "rec");
        if (ev.tipo !== "fase" && a !== "tu") { const k = ev.de + ">" + a; d.rutas.set(k, (d.rutas.get(k) || 0) + 1); }
      });
    }

    switch (ev.tema) {
      case "documento.recibido": d.hoy.docs++; break;
      case "banco.movimiento": d.hoy.movs++; break;
      case "factura.faltante": d.hoy.faltas++; if (det.faltante) m.faltantes.set(det.faltante.id, det.faltante); break;
      case "reclamacion.enviada": if (det.faltante) m.faltantes.set(det.faltante.id, det.faltante); break;
      case "escalado.humano": if (det.faltante) m.faltantes.set(det.faltante.id, Object.assign({}, det.faltante, { estado: "escalada" })); break;
      case "factura.faltante_resuelta": if (det.faltante) m.faltantes.delete(det.faltante.id); break;
      case "revision.incidencia": if (det.incidencia) m.incidencias.set(det.incidencia.id, det.incidencia); break;
      case "revision.resuelta": if (det.incidencia) m.incidencias.delete(det.incidencia.id); break;
      case "factura.emitida":
        d.hoy.emitidas++;
        if (det.registro && det.factura) m.cadena.set(det.factura.numero, { numero: det.factura.numero, huella: det.registro.huella, total: det.factura.total, envio: "pendiente", cliente: det.factura.receptor });
        if (det.factura) m.cobrar.set(det.factura.numero, det.factura);
        break;
      case "banco.conciliado": if (det.factura && det.factura.direccion === "emitida") m.cobrar.delete(det.factura.numero); break;
      case "cobro.recordatorio": if (det.factura && m.cobrar.has(det.factura.numero)) m.cobrar.get(det.factura.numero).recordado = true; break;
      case "aeat.envio": ((det.aeat && det.aeat.registros) || []).forEach((n) => { const r = m.cadena.get(n); if (r) r.envio = "aceptado"; }); break;
      case "fiscal.informe": if (det.informe) m.informe = det.informe; break;
    }
    if (ev.tipo === "email") d.hoy.emails++;
  }

  // ------------------------------------------------------------- pintar
  function pintarTodo() { pintarMapa(); pintarCabecera(); pintarKpis(); pintarAtencion(); }

  function pintarMapa() {
    const d = E.d;
    for (const id in M.nodos) {
      const g = M.nodos[id];
      g.classList.toggle("trabaja", d.trabajando.has(id));
      const notas = Array.from(d.mesa.incidencias.values()).some((i) => i.agente === id);
      g.classList.toggle("con-nota", notas);
    }
    for (const [k, p] of M.bordes) {
      const n = d.rutas.get(k) || 0;
      p.style.strokeWidth = n ? (1.6 + Math.min(2.6, Math.log2(n + 1) * 0.7)).toFixed(2) : "";
      p.style.opacity = n ? "1" : ".55";
    }
  }

  function pintarCabecera() {
    const d = E.d, fases = (E.info && E.info.fases) || [];
    const cont = $("#fases");
    if (cont.childElementCount !== fases.length) cont.innerHTML = fases.map((f) => `<span class="seg" data-f="${f.id}"></span>`).join("");
    cont.querySelectorAll(".seg").forEach((s) => {
      s.classList.toggle("actual", d.fase === s.dataset.f);
      s.classList.toggle("hecha", d.hechas.has(s.dataset.f) && d.fase !== s.dataset.f);
    });
    const clave = d.fase || (d.fin ? "fin" : d.enJornada ? "inicio" : null);
    $("#reloj").textContent = clave ? RELOJ[clave] : "--:--";
    const idx = fases.findIndex((f) => f.id === d.fase);
    const quien = Array.from(d.trabajando).filter((x) => AGENTES[x]).map(nombre);
    $("#fase-txt").innerHTML = d.fase
      ? `Fase ${idx + 1} de ${fases.length} · <b>${esc(fases[idx].nombre)}</b>${quien.length ? ` · ${esc(quien.join(" y "))} ${quien.length > 1 ? "están" : "está"} en ello` : ""}`
      : d.fin ? "Jornada terminada. Todo el trabajo del día está hecho." : d.enJornada ? "Empieza la jornada" : "Esperando a que empiece la jornada";
    $("#lider-txt").innerHTML = d.fase ? `<b>Olga</b> coordina: ${esc(fases[idx].nombre.toLowerCase())}` : `<b>Olga</b> coordina la jornada`;

    // saludo y resumen del día
    const hora = clave ? parseInt(RELOJ[clave], 10) : 9;
    const negocio = ((E.info && E.info.empresa && E.info.empresa.nombre) || "").replace(/,?\s+(S\.?L\.?U?\.?|S\.?A\.?)$/i, "");
    $("#saludo").textContent = `${hora < 13 ? "Buenos días" : hora < 19 ? "Buenas tardes" : "Buenas noches"}${negocio ? ", " + negocio : ""}`;
    $("#fecha-larga").textContent = fechaLarga(d.dia);
    const h = d.hoy, partes = [];
    if (h.docs) partes.push(`ha leído ${plural(h.docs, "documento")}`);
    if (h.movs) partes.push(`ha revisado ${plural(h.movs, "movimiento")} del banco`);
    if (h.emitidas) partes.push(`ha emitido ${plural(h.emitidas, "factura")}`);
    if (h.emails) partes.push(`ha enviado ${plural(h.emails, "email")}`);
    const pend = d.mesa.incidencias.size;
    let txt;
    if (partes.length) {
      const lista = partes.length > 1 ? partes.slice(0, -1).join(", ") + " y " + partes[partes.length - 1] : partes[0];
      txt = `Hoy tu equipo ${lista}. ${pend ? `Hay ${plural(pend, "cosa")} que ${pend === 1 ? "necesita" : "necesitan"} tu decisión.` : "No hay nada que necesite tu decisión."}`;
    } else if (E.modo === "directo") txt = "Tu equipo está listo. Pulsa «Ejecutar jornada» para que revise facturas, banco e impuestos.";
    else txt = "Así trabaja tu equipo de contabilidad durante un día normal.";
    $("#resumen-dia").textContent = txt;
  }

  function kpi(id, valor, sub, chips) {
    const k = $("#" + id);
    const v = k.querySelector("[data-v]");
    if (E.kpiPrevio[id] !== undefined && E.kpiPrevio[id] !== valor && !reducido) { k.classList.remove("cambio"); void k.offsetWidth; k.classList.add("cambio"); }
    E.kpiPrevio[id] = valor;
    v.innerHTML = valor;
    k.querySelector("[data-s]").textContent = sub;
    k.querySelector("[data-c]").innerHTML = chips.map(([t, c]) => `<span class="chip ${c}">${esc(t)}</span>`).join("");
  }

  function pintarKpis() {
    const m = E.d.mesa;
    // Facturas que faltan
    const f = Array.from(m.faltantes.values());
    const sumF = f.reduce((s, x) => s + (x.importe_num || 0), 0);
    const recl = f.filter((x) => x.estado === "reclamada").length, esca = f.filter((x) => x.estado === "escalada").length;
    kpi("kpi-faltan", String(f.length), f.length ? `≈ ${eur(sumF)} en gastos sin justificante` : "Todos tus pagos tienen su factura",
      f.length ? [recl && [`${recl} reclamada${recl > 1 ? "s" : ""}`, ""], esca && [`${esca} te necesita${esca > 1 ? "n" : ""}`, "bad"]].filter(Boolean) : [["Al día", "ok"]]);
    // Pendiente de cobro
    const c = Array.from(m.cobrar.values());
    const sumC = c.reduce((s, x) => s + (x.importe || 0), 0);
    const hoy = E.d.dia;
    const venc = c.filter((x) => x.recordado || (x.vencimiento_iso && hoy && x.vencimiento_iso < hoy)).length;
    kpi("kpi-cobrar", eur(sumC), c.length ? plural(c.length, "factura") + " sin cobrar" : "Nadie te debe nada",
      venc ? [[`${venc} vencida${venc > 1 ? "s" : ""}`, "bad"]] : c.length ? [["En plazo", "ok"]] : []);
    // IVA
    const inf = m.informe;
    if (inf) {
      const res = inf.resultado_num !== undefined ? inf.resultado_num : parseFloat(String(inf.resultado).replace(/\./g, "").replace(",", "."));
      $("#kpi-iva-titulo").textContent = `IVA ${inf.trimestre}T ${inf.anio} · borrador`;
      const dias = inf.plazo_iso && hoy ? diasHasta(inf.plazo_iso, hoy) : null;
      kpi("kpi-iva", `${eur(Math.abs(res))}<small>${res > 0 ? "a pagar" : "a compensar"}</small>`,
        `Presentar antes del ${inf.plazo_iso ? fechaCorta(inf.plazo_iso) : inf.plazo}${dias !== null && dias >= 0 ? ` · quedan ${dias} días` : ""}`,
        [f.length && ["Faltan facturas: puede bajar", "warn"], dias !== null && dias <= 15 && dias >= 0 && ["Plazo cerca", "warn"]].filter(Boolean));
    } else kpi("kpi-iva", "—", "Fátima lo calcula al cerrar la jornada", []);
    // VeriFactu
    const r = Array.from(m.cadena.values());
    const env = r.filter((x) => x.envio === "aceptado").length;
    if (!r.length) kpi("kpi-verifactu", "—", "Aún no has emitido facturas", []);
    else if (!m.integra) kpi("kpi-verifactu", `<span style="color:var(--bad)">Revisar</span>`, "La cadena de registros está rota", [["Avisa a tu asesoría", "bad"]]);
    else kpi("kpi-verifactu", env === r.length ? `<span style="color:var(--ok)">Al día</span>` : "Por enviar",
      `${plural(r.length, "factura")} registrada${r.length > 1 ? "s" : ""} · ${env} en Hacienda`, [["Cadena íntegra", "ok"]]);
  }

  const SEV = { error: ["Error", "var(--t-alerta)", 0], aviso: ["Aviso", "var(--t-aviso)", 1], info: ["Nota", "var(--t-documento)", 2] };
  function pintarAtencion(nuevaId) {
    const incs = Array.from(E.d.mesa.incidencias.values()).sort((a, b) => (SEV[a.severidad] || SEV.info)[2] - (SEV[b.severidad] || SEV.info)[2]);
    const n = $("#n-atencion");
    n.textContent = incs.length;
    n.className = "cuenta" + (incs.some((i) => i.severidad === "error") ? " bad" : "");
    const lista = $("#lista-atencion");
    if (!incs.length) { lista.innerHTML = `<div class="vacio">Nada por ahora. Tu equipo te avisará aquí solo cuando necesite una decisión tuya.</div>`; return; }
    lista.innerHTML = incs.map((i) => {
      const [et, c] = SEV[i.severidad] || SEV.info;
      return `<div class="tarea${i.id === nuevaId ? " nueva" : ""}" style="--c:${c}" role="button" tabindex="0" data-inc="${esc(i.id)}">
        <span class="barra"></span>
        <span><span class="que" style="display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden">${esc(i.mensaje)}</span>
        <span class="quien">${et} · ${esc(nombre(i.agente))} (${esc(rolDe(i.agente))})</span></span>
        ${E.modo === "directo" ? `<button class="hecho" type="button" data-resolver="${esc(i.id)}">Hecho</button>` : "<span></span>"}</div>`;
    }).join("");
    lista.querySelectorAll("[data-inc]").forEach((t) => {
      const abrir = () => abrirIncidencia(E.d.mesa.incidencias.get(t.dataset.inc));
      t.addEventListener("click", (e) => { if (!e.target.closest("[data-resolver]")) abrir(); });
      t.addEventListener("keydown", (e) => { if (e.key === "Enter") abrir(); });
    });
    lista.querySelectorAll("[data-resolver]").forEach((b) => b.addEventListener("click", () => resolver(b.dataset.resolver, b)));
  }

  // ------------------------------------------------------------ actividad
  let diaLista = null;
  function filaActividad(ev, nueva) {
    const lista = $("#lista-actividad");
    $("#actividad-vacia") && ($("#actividad-vacia").hidden = true);
    if (ev.dia && ev.dia !== diaLista) {
      diaLista = ev.dia;
      const s = document.createElement("div");
      s.className = "dia-sep";
      s.textContent = fechaLarga(ev.dia);
      lista.appendChild(s);
    }
    const sistema = ev.tipo === "fase" || ev.tipo === "jornada";
    const hora = ev.fase ? RELOJ[ev.fase] : ev.tema === "ciclo.iniciado" ? RELOJ.inicio : ev.tema === "ciclo.terminado" ? RELOJ.fin : (ev.momento || "").slice(11, 16);
    const row = document.createElement("div");
    row.className = "act" + (sistema ? " sistema" : "") + (nueva ? " nueva" : "");
    row.dataset.id = ev.id;
    row.tabIndex = 0;
    row.innerHTML = `<time>${esc(hora || "")}</time>${avatarHtml(ev.de, 28)}
      <div style="min-width:0"><p>${textoEv(ev)}</p>${sistema ? "" : `<div class="etq"><span class="chip" style="--c:${colorTipo(ev.tipo)}">${esc((TIPOS[ev.tipo] || TIPOS.sistema).nombre)}</span></div>`}</div>`;
    row.addEventListener("click", () => abrirEvento(ev));
    row.addEventListener("keydown", (e) => { if (e.key === "Enter") abrirEvento(ev); });
    row.hidden = !!E.filtro && !(ev.de === E.filtro || (ev.a || []).includes(E.filtro));
    lista.appendChild(row);
  }
  function reiniciarActividad() {
    $("#lista-actividad").innerHTML = `<div class="vacio" id="actividad-vacia">Cuando el equipo empiece a trabajar, aquí verás cada paso explicado.</div>`;
    diaLista = null;
  }
  function bajarActividad() { const l = $("#lista-actividad"); l.scrollTop = l.scrollHeight; }
  function marcarActivo(id) {
    $("#lista-actividad").querySelectorAll(".act.activo").forEach((n) => n.classList.remove("activo"));
    const n = $(`#lista-actividad .act[data-id="${id}"]`);
    if (n) n.classList.add("activo");
  }
  function filtrarPor(id) {
    E.filtro = id;
    $("#filtro").hidden = false;
    $("#filtro-txt").innerHTML = `Actividad de <b>${esc(nombre(id))}</b>`;
    $("#lista-actividad").querySelectorAll(".act").forEach((r) => {
      const ev = E.eventos[+r.dataset.id];
      r.hidden = !(ev && (ev.de === id || (ev.a || []).includes(id)));
    });
    for (const k in M.nodos) M.nodos[k].classList.toggle("seleccionado", k === id);
    $("#lista-actividad").scrollTop = 0;
  }
  function quitarFiltro() {
    E.filtro = null;
    $("#filtro").hidden = true;
    $("#lista-actividad").querySelectorAll(".act").forEach((r) => (r.hidden = false));
    for (const k in M.nodos) M.nodos[k].classList.remove("seleccionado");
    bajarActividad();
  }

  // ----------------------------------------------------------- reproducción
  async function reproducir(ev, gen) {
    const dur = (ms) => (reducido ? 40 : ms / E.velocidad);
    aplicar(ev);
    filaActividad(ev, true);
    marcarActivo(ev.id);
    if (!E.filtro) bajarActividad();
    pintarCabecera();

    if (ev.tipo === "jornada" || ev.tipo === "fase") {
      limpiarGlobos();
      pintarMapa();
      if (ev.tipo === "fase") (ev.a || []).forEach((a) => { recibe(a); globo(a, "En ello", "fase", dur(1300)); });
      pintarKpis();
      await esperar(dur(ev.tipo === "fase" ? 900 : 1100));
      return;
    }

    if (AGENTES[ev.de]) { M.nodos[ev.de].classList.add("trabaja"); globo(ev.de, ev.titulo, ev.tipo, dur(2400)); }
    else recibe(ev.de);
    await esperar(dur(140));
    const destinos = ev.a || [];
    await Promise.all(destinos.map((a, i) => esperar(i * dur(110)).then(() => {
      if (a === "tu") {
        subida(ev.de, ev.tipo);
        return esperar(dur(500)).then(() => { if (gen === E.generacion) pintarAtencion(ev.detalle && ev.detalle.incidencia && ev.detalle.incidencia.id); });
      }
      return pulso(ev.de, a, ev.tipo, dur(950), gen).then(() => { if (gen === E.generacion) recibe(a); });
    })));
    if (gen !== E.generacion) return;
    pintarMapa();
    pintarKpis();
    if (!destinos.includes("tu")) pintarAtencion();
    await esperar(dur(240));
  }

  async function bucle() {
    for (;;) {
      if (!E.reproduciendo || E.cursor >= E.eventos.length) {
        if (E.reproduciendo && E.cursor >= E.eventos.length && E.modo === "demo") pausar();
        if (E.cursor >= E.eventos.length && !E.d.enJornada && E.d.trabajando.size) {
          await esperar(900);
          if (E.cursor >= E.eventos.length && !E.d.enJornada) { E.d.trabajando = new Set(); pintarMapa(); }
        }
        await esperar(150);
        continue;
      }
      const gen = E.generacion;
      const ev = E.eventos[E.cursor++];
      actualizarLinea();
      await reproducir(ev, gen);
      if (gen === E.generacion) actualizarLinea();
    }
  }

  function irA(n) {
    E.generacion++;
    M.capaPulsos.innerHTML = "";
    limpiarGlobos();
    E.d = estadoVacio(E.base);
    E.kpiPrevio = {};
    reiniciarActividad();
    E.cursor = Math.max(0, Math.min(n, E.eventos.length));
    for (let i = 0; i < E.cursor; i++) { aplicar(E.eventos[i]); filaActividad(E.eventos[i], false); }
    if (E.cursor) marcarActivo(E.eventos[E.cursor - 1].id);
    pintarTodo();
    bajarActividad();
    actualizarLinea();
  }

  function reproducirPausar() {
    if (E.reproduciendo) return pausar();
    if (E.cursor >= E.eventos.length && E.modo === "demo") irA(0);
    E.reproduciendo = true;
    pintarPlay();
  }
  function pausar() { E.reproduciendo = false; pintarPlay(); }
  function pintarPlay() {
    const b = $("#btn-play");
    b.setAttribute("aria-label", E.reproduciendo ? "Pausar" : "Reproducir");
    b.innerHTML = E.reproduciendo
      ? `<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="4" y="3" width="2.8" height="10" rx="1" fill="currentColor"/><rect x="9.2" y="3" width="2.8" height="10" rx="1" fill="currentColor"/></svg>`
      : `<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M5 3v10l8-5z" fill="currentColor"/></svg>`;
  }

  function actualizarLinea() {
    const r = $("#deslizador");
    r.max = E.eventos.length;
    r.value = E.cursor;
    $("#contador").textContent = `${E.cursor}/${E.eventos.length}`;
    pintarLienzo();
  }
  function pintarLienzo() {
    const c = $("#lienzo");
    const dpr = window.devicePixelRatio || 1, w = c.clientWidth, h = c.clientHeight;
    if (!w) return;
    if (c.width !== Math.round(w * dpr)) { c.width = Math.round(w * dpr); c.height = Math.round(h * dpr); }
    const x = c.getContext("2d");
    x.setTransform(dpr, 0, 0, dpr, 0, 0);
    x.clearRect(0, 0, w, h);
    const cs = getComputedStyle(document.documentElement);
    x.fillStyle = cs.getPropertyValue("--map-node").trim();
    x.fillRect(0, h / 2 - 3, w, 6);
    const n = E.eventos.length;
    if (!n) return;
    const paso = w / n;
    E.eventos.forEach((ev, i) => {
      if (ev.tipo === "fase" || ev.tipo === "jornada") return;
      x.globalAlpha = i < E.cursor ? 1 : 0.28;
      x.fillStyle = cs.getPropertyValue((TIPOS[ev.tipo] || TIPOS.sistema).v).trim();
      x.fillRect(i * paso + paso * 0.2, h / 2 - 6, Math.max(1.5, paso * 0.6), 12);
    });
    x.globalAlpha = 1;
    x.fillStyle = cs.getPropertyValue("--map-ink").trim();
    x.fillRect(E.cursor * paso - 1, 1, 2, h - 2);
  }

  // ------------------------------------------------------------ hoja lateral
  let focoPrevio = null;
  function abrirHoja(titulo, iconoHtml, html) {
    focoPrevio = document.activeElement;
    $("#hoja-titulo").textContent = titulo;
    $("#hoja-icono").innerHTML = iconoHtml || "";
    $("#hoja-contenido").innerHTML = html;
    $("#capa").hidden = false;
    $("#hoja-cerrar").focus();
  }
  function cerrarHoja() { $("#capa").hidden = true; if (focoPrevio && focoPrevio.focus) focoPrevio.focus(); }
  const kv = (pares) => `<dl class="kv">${pares.filter((p) => p[1] != null && p[1] !== "").map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v}</dd>`).join("")}</dl>`;
  const ficha = (t, cuerpo, extra) => `<div class="ficha"><div class="ficha-cab"><span>${esc(t)}</span>${extra ? `<span>${extra}</span>` : ""}</div><div class="ficha-cuerpo">${cuerpo}</div></div>`;

  function fichaFactura(f) {
    const lineas = f.lineas && f.lineas.length ? `<table class="tabla"><thead><tr><th>Concepto</th><th>Cant.</th><th>IVA</th><th class="d">Precio</th></tr></thead><tbody>
      ${f.lineas.map((l) => `<tr><td>${esc(l.descripcion)}</td><td>${esc(l.cantidad)}</td><td>${esc(l.iva)}</td><td class="d">${esc(l.precio)}</td></tr>`).join("")}</tbody></table>` : "";
    return ficha(`Factura ${f.numero}`, kv([["Emite", esc(f.emisor)], ["Cliente", esc(f.receptor)], ["Fecha", esc(f.fecha)], ["Vence", esc(f.vencimiento)],
      ["Base", esc(f.base)], ["IVA", esc(f.iva)], ["Total", `<b>${esc(f.total)}</b>`]]) + lineas, esc(f.estado));
  }

  function abrirEvento(ev) {
    const d = ev.detalle || {}, partes = [`<p class="frase" style="margin:0">${textoEv(ev)}</p>`];
    if (d.email) partes.push(ficha("Email", kv([["Para", esc(d.email.para)], ["Asunto", esc(d.email.asunto)]]) + `<div class="carta">${esc(d.email.cuerpo)}</div>`));
    if (d.factura) partes.push(fichaFactura(d.factura));
    if (d.registro) {
      const r = d.registro;
      partes.push(ficha("Registro VeriFactu", `${kv([["Registro nº", esc(r.secuencia)], ["Fecha y hora", esc(new Date(r.fecha_hora).toLocaleString("es-ES"))]])}
        <div><div class="nota-txt" style="margin-bottom:4px">Huella de esta factura</div><div class="huella">${esc(r.huella)}</div></div>
        <div><div class="nota-txt" style="margin-bottom:4px">Encadenada con la huella anterior</div><div class="huella">${r.huella_anterior ? esc(r.huella_anterior) : "Primer registro de la cadena"}</div></div>
        <div class="nota-txt">La huella se calcula con los datos de esta factura y la de la anterior. Si alguien modifica una factura pasada, la cadena deja de cuadrar y Hacienda lo detecta.</div>
        ${r.qr ? `<div style="font-size:13.5px">Código QR impreso en la factura: <a href="${esc(r.qr)}" target="_blank" rel="noopener">comprobar en la AEAT</a></div>` : ""}`, "Hacienda"));
    }
    if (d.movimiento) partes.push(ficha("Movimiento del banco", kv([["Fecha", esc(d.movimiento.fecha)], ["Concepto", esc(d.movimiento.concepto)], ["Importe", `<b>${esc(d.movimiento.importe)}</b>`]])));
    if (d.faltante) partes.push(ficha("Factura que falta", kv([["Proveedor", esc(d.faltante.proveedor)], ["Por qué", esc(d.faltante.motivo)], ["Importe", esc(d.faltante.importe)], ["Periodo", esc(d.faltante.periodo)], ["Reclamaciones", esc(d.faltante.intentos)]])));
    if (d.incidencia) partes.push(fichaIncidencia(d.incidencia));
    if (d.informe) partes.push(fichaInforme(d.informe));
    if (d.documento) partes.push(ficha("Documento recibido", kv([["Archivo", esc(d.documento.nombre)], ["Llega por", esc(d.documento.origen)]]) + `<div class="extracto">${esc(d.documento.extracto)}</div>`));
    if (d.aeat) partes.push(ficha("Envío a Hacienda", kv([["Aceptados", esc(d.aeat.aceptados)], ["Rechazados", esc(d.aeat.rechazados)], ["Facturas", esc((d.aeat.registros || []).join(", "))], ["Justificante", `<code>${esc(d.aeat.csv)}</code>`]])));
    if (d.resumen) partes.push(ficha("Resumen del día", kv(Object.entries(d.resumen).map(([k, v]) => [k.charAt(0).toUpperCase() + k.slice(1).replace(/_/g, " "), esc(v)]))));
    abrirHoja(ev.titulo || "Detalle", avatarHtml(ev.de, 32), partes.join(""));
  }

  function fichaIncidencia(i) {
    return ficha(`${(SEV[i.severidad] || SEV.info)[0]} · ${nombre(i.agente)}`, `<p style="margin:0">${esc(i.mensaje)}</p>
      ${QUE_HACER[i.codigo] ? `<div style="padding:10px 12px;border-radius:10px;background:var(--accent-soft);font-size:13.5px"><b>Qué hacer:</b> ${esc(QUE_HACER[i.codigo])}</div>` : ""}`);
  }
  function fichaInforme(i) {
    return ficha(`Modelo 303 · ${i.trimestre}T ${i.anio}`, kv([["IVA que cobras", esc(i.repercutido)], ["IVA que pagas", esc(i.soportado)], ["Resultado", `<b>${esc(i.resultado)}</b>`], ["Plazo", esc(i.plazo)]]) +
      (i.avisos || []).map((a) => `<div style="color:var(--warn);font-size:13px;font-weight:600">${esc(a)}</div>`).join("") +
      `<div class="nota-txt">Es un borrador orientativo. Tu asesoría lo revisa antes de presentarlo.</div>`, "Borrador");
  }

  function abrirIncidencia(i) {
    if (!i) return;
    const boton = E.modo === "directo" ? `<button class="btn primario" type="button" id="h-resolver" style="justify-self:start">Marcar como hecho</button>` : "";
    abrirHoja("Necesita tu atención", avatarHtml(i.agente, 32), fichaIncidencia(i) + boton);
    if (boton) $("#h-resolver").addEventListener("click", (e) => { cerrarHoja(); resolver(i.id, e.currentTarget); });
  }

  function abrirPersona(id) {
    const c = E.d.cuenta[id] || { env: 0, rec: 0 };
    const part = E.info && E.info.participantes ? E.info.participantes.find((x) => x.id === id) : null;
    const ext = !AGENTES[id];
    const estado = E.d.trabajando.has(id) ? "Trabajando" : E.d.fin ? "Terminado" : "En espera";
    const desc = ext ? { buzon: "Por aquí llegan las facturas de tus proveedores: email, Google Drive o una carpeta.", banco: "Los movimientos de tu cuenta. Carlos los casa con cada factura.",
      tu: "Las facturas que emites, desde tu TPV o con el botón «Nueva factura».", proveedores: "Ramón les escribe cuando falta una factura.",
      clientes: "Coral les envía tus facturas y les recuerda los pagos vencidos.", aeat: "Vera remite a Hacienda cada factura registrada con VeriFactu." }[id] : (part && part.rol) || "";
    abrirHoja(nombre(id), "", `
      <div class="persona-cab">${avatarHtml(id, 52)}<div><div style="font-weight:700;font-size:15px">${esc(rolDe(id))}</div><div class="nota-txt">${esc(desc)}</div></div></div>
      <div class="cifras"><div class="cifra"><b>${c.env}</b><span>enviados</span></div><div class="cifra"><b>${c.rec}</b><span>recibidos</span></div>
      <div class="cifra"><b style="font-size:15px;padding-block:3px">${ext ? "—" : estado}</b><span>ahora</span></div></div>
      <button class="btn primario" type="button" id="h-filtrar" style="justify-self:start">Ver su actividad</button>`);
    $("#h-filtrar").addEventListener("click", () => { cerrarHoja(); filtrarPor(id); });
  }

  function abrirKpi(cual) {
    const m = E.d.mesa;
    if (cual === "faltan") {
      const f = Array.from(m.faltantes.values());
      const est = { detectada: ["Detectada", ""], reclamada: ["Reclamada", ""], escalada: ["Te necesita", "bad"] };
      abrirHoja("Facturas que faltan", "", f.length ? `<p class="nota-txt" style="margin:0">Pagos sin factura y proveedores habituales que no han enviado la del mes. Ramón las reclama por email cada 7 días; a la tercera, te avisa.</p>
        <table class="tabla"><thead><tr><th>Proveedor</th><th>Estado</th><th class="d">Importe</th></tr></thead><tbody>
        ${f.map((x) => `<tr><td><b>${esc(x.proveedor)}</b><div class="nota-txt">${esc(x.periodo || "")}${x.intentos ? ` · ${plural(x.intentos, "reclamación", "reclamaciones")}` : ""}</div></td>
          <td><span class="chip ${(est[x.estado] || ["", ""])[1]}">${esc((est[x.estado] || [x.estado])[0])}</span></td><td class="d">${esc(x.importe || "—")}</td></tr>`).join("")}</tbody></table>`
        : `<p class="frase" style="margin:0">Todos tus pagos tienen su factura. Dani lo comprueba en cada jornada.</p>`);
    } else if (cual === "cobrar") {
      const c = Array.from(m.cobrar.values());
      abrirHoja("Pendiente de cobro", "", c.length ? `<table class="tabla"><thead><tr><th>Factura</th><th>Vence</th><th class="d">Importe</th></tr></thead><tbody>
        ${c.map((x) => { const v = x.recordado || (x.vencimiento_iso && E.d.dia && x.vencimiento_iso < E.d.dia);
          return `<tr><td><b>${esc(x.numero)}</b><div class="nota-txt">${esc(x.receptor)}</div></td><td>${esc(x.vencimiento || "")} ${v ? '<span class="chip bad">Vencida</span>' : ""}</td><td class="d">${esc(x.total)}</td></tr>`; }).join("")}</tbody></table>
        <p class="nota-txt" style="margin:0">Cuando el cobro aparece en el banco, Carlos lo casa con la factura y desaparece de esta lista.</p>`
        : `<p class="frase" style="margin:0">Nadie te debe nada ahora mismo.</p>`);
    } else if (cual === "iva") {
      abrirHoja("IVA del trimestre", "", m.informe ? fichaInforme(m.informe) : `<p class="frase" style="margin:0">Fátima prepara el borrador del modelo 303 al final de cada jornada.</p>`);
    } else {
      const r = Array.from(m.cadena.values());
      abrirHoja("VeriFactu", "", `<p class="nota-txt" style="margin:0">Cada factura que emites queda registrada con una huella encadenada a la anterior y se envía a Hacienda. Así se demuestra que ninguna se ha modificado después.</p>
        ${r.length ? `<div class="cadena">${r.slice().reverse().map((x, i) => `<div class="eslabon"><span class="bola">✓</span><span><b>${esc(x.numero)}</b> · ${esc(x.cliente || "")} · ${esc(x.total || "")}<br><code>${esc((x.huella || "").slice(0, 24))}…</code></span>
          <span class="chip ${x.envio === "aceptado" ? "ok" : "warn"}">${x.envio === "aceptado" ? "En Hacienda" : "Pendiente"}</span></div>`).join("")}</div>` : `<p class="frase" style="margin:0">Aún no has emitido facturas.</p>`}`);
    }
  }

  function abrirAyuda() {
    const punto = (t) => `<span class="ico"><i style="background:${colorTipo(t)}"></i></span>`;
    abrirHoja("Cómo funciona", "", `
      <ol class="pasos">
        <li><span class="ico">${icono("bandeja")}</span><div><b>Llega la información.</b> Facturas de proveedores (email, Drive o carpeta), movimientos del banco y tus ventas.</div></li>
        <li><span class="ico">${avatarHtml("detective", 26)}</span><div><b>Tu equipo trabaja.</b> Ocho agentes, cada uno con una tarea: leer facturas, casar el banco, buscar las que faltan, reclamarlas, emitir con VeriFactu, cobrar, revisar y preparar el IVA.</div></li>
        <li><span class="ico">${avatarHtml("orquestador", 26)}</span><div><b>Olga coordina la jornada</b> por fases. La barra del mapa muestra en cuál está el equipo.</div></li>
        <li><span class="ico" style="color:var(--bad)">!</span><div><b>Solo te avisan cuando hace falta.</b> Lo que necesita tu decisión aparece en «Necesita tu atención», con lo que tienes que hacer.</div></li>
      </ol>
      ${ficha("Colores de los mensajes", `<ol class="pasos">
        <li>${punto("documento")}<div>Documentos y facturas recibidas</div></li><li>${punto("banco")}<div>Movimientos del banco</div></li>
        <li>${punto("falta")}<div>Facturas que faltan</div></li><li>${punto("email")}<div>Emails a proveedores y clientes</div></li>
        <li>${punto("verifactu")}<div>Facturas emitidas y registros VeriFactu</div></li><li>${punto("alerta")}<div>Errores y avisos para ti</div></li></ol>`)}
      <p class="nota-txt" style="margin:0">Pulsa cualquier tarjeta, persona o línea de actividad para ver el detalle: el email enviado, la factura o la huella VeriFactu.</p>`);
  }

  function abrirVenta() {
    const clientes = (E.info && E.info.clientes) || [];
    abrirHoja("Nueva factura", "", `
      <form class="formulario" id="form-venta" novalidate>
        <label for="v-cliente">Cliente<select id="v-cliente">${clientes.map((c) => `<option value="${esc(c.nif)}">${esc(c.nombre)} · ${esc(c.nif)}</option>`).join("")}<option value="">Otro cliente…</option></select></label>
        <div id="v-otro" hidden style="display:grid;gap:10px;grid-template-columns:minmax(0,1fr) 140px">
          <label for="v-nombre">Nombre o razón social<input id="v-nombre" autocomplete="off"></label>
          <label for="v-nif">NIF<input id="v-nif" autocomplete="off" placeholder="B12345674"></label></div>
        <div id="v-lineas" style="display:grid;gap:8px"></div>
        <button class="btn" type="button" id="v-mas" style="justify-self:start">Añadir línea</button>
        <div class="total-venta"><span>Total con IVA</span><span id="v-total" class="num">0,00 €</span></div>
        <div class="error-form" id="v-error" hidden></div>
        <button class="btn primario" type="submit" id="v-enviar">Emitir factura</button>
        <p class="nota-txt" style="margin:0">Vera la numera, la registra con VeriFactu y Coral se la envía al cliente.</p>
      </form>`);
    const lineas = $("#v-lineas");
    let n = 0;
    const num = (s) => parseFloat(String(s || "0").replace(/\./g, "").replace(",", ".")) || 0;
    const total = () => {
      let t = 0;
      lineas.querySelectorAll(".linea-venta").forEach((l) => { t += num(l.querySelector(".c").value) * num(l.querySelector(".p").value) * (1 + num(l.querySelector(".i").value) / 100); });
      $("#v-total").textContent = eur(t);
    };
    const nueva = (desc, cant, precio, iva) => {
      n++;
      const div = document.createElement("div");
      div.className = "linea-venta";
      div.innerHTML = `<label for="v-d${n}">Concepto<input id="v-d${n}" class="d" value="${esc(desc || "")}"></label>
        <label for="v-c${n}">Cant.<input id="v-c${n}" class="c" inputmode="decimal" value="${cant || 1}"></label>
        <label for="v-p${n}">Precio<input id="v-p${n}" class="p" inputmode="decimal" value="${precio || ""}" placeholder="0,00"></label>
        <label for="v-i${n}">IVA<select id="v-i${n}" class="i">${[21, 10, 4, 0].map((t) => `<option value="${t}" ${t === (iva || 21) ? "selected" : ""}>${t}%</option>`).join("")}</select></label>
        <button type="button" class="quitar" aria-label="Quitar línea">✕</button>`;
      div.querySelector(".quitar").addEventListener("click", () => { div.remove(); total(); });
      div.querySelectorAll("input,select").forEach((i) => i.addEventListener("input", total));
      lineas.appendChild(div);
    };
    nueva("Desayunos de empresa", 1, "250,00", 10);
    total();
    $("#v-mas").addEventListener("click", () => nueva());
    $("#v-cliente").addEventListener("change", (e) => ($("#v-otro").hidden = !!e.target.value));
    $("#form-venta").addEventListener("submit", async (e) => {
      e.preventDefault();
      const sel = $("#v-cliente").value, cli = clientes.find((c) => c.nif === sel);
      const datos = { cliente_nif: sel || $("#v-nif").value.trim(), cliente_nombre: cli ? cli.nombre : $("#v-nombre").value.trim(),
        lineas: Array.from(lineas.querySelectorAll(".linea-venta")).map((l) => ({ descripcion: l.querySelector(".d").value, cantidad: num(l.querySelector(".c").value),
          precio_unitario: String(num(l.querySelector(".p").value)), tipo_iva: +l.querySelector(".i").value })) };
      $("#v-enviar").disabled = true;
      const r = await api("/api/venta", datos);
      $("#v-enviar").disabled = false;
      if (r && r.ok) { cerrarHoja(); tostada(`Factura ${r.numero} emitida: ${r.total}`); seguirEnDirecto(); }
      else { const er = $("#v-error"); er.hidden = false; er.textContent = (r && r.error) || "No se ha podido emitir la factura."; }
    });
  }

  // --------------------------------------------------------------- directo
  async function api(ruta, cuerpo) {
    try {
      const r = await fetch(ruta, cuerpo === undefined ? { cache: "no-store" } : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cuerpo) });
      if (!r.ok && r.status !== 500) throw new Error(String(r.status));
      return await r.json();
    } catch (e) { return null; }
  }
  function estadoVivo(clase, txt) { const s = $("#estado-vivo"); s.className = "estado-vivo " + clase; s.lastElementChild.textContent = txt; }

  function seguirEnDirecto() {
    if (E.cursor < E.eventos.length) irA(E.eventos.length);
    E.reproduciendo = true;
    pintarPlay();
    sondear();
  }
  let sondeando = false;
  async function sondear() {
    if (sondeando) return;
    sondeando = true;
    const r = await api("/api/eventos?desde=" + E.eventos.length);
    sondeando = false;
    if (!r) return estadoVivo("error", "Sin conexión");
    estadoVivo("vivo", "En directo");
    r.eventos.forEach((ev) => { if (ev.id === E.eventos.length) E.eventos.push(ev); });
    if (r.eventos.length) actualizarLinea();
  }
  async function refrescar() {
    const st = await api("/api/estado");
    if (!st) return;
    $("#num-llega").textContent = st.por_llegar || 0;
    $("#btn-llega").disabled = !st.por_llegar || E.ocupado;
    const inp = $("#fecha-jornada");
    if (st.hoy && !inp.dataset.tocada) inp.value = st.hoy;
    if (!E.d.dia && st.hoy) { E.d.dia = st.hoy; pintarCabecera(); }
  }
  async function accion(boton, ruta, cuerpo, ok) {
    if (E.ocupado) return;
    E.ocupado = true; boton.disabled = true;
    const r = await api(ruta, cuerpo);
    E.ocupado = false; boton.disabled = false;
    if (r && r.ok) { if (ok) ok(r); seguirEnDirecto(); }
    else tostada((r && r.error) || "No hay conexión con tu equipo. Comprueba que «agentes-conta web» sigue abierto.", true);
    refrescar();
  }
  async function resolver(id, boton) {
    if (boton) boton.disabled = true;
    const r = await api("/api/resolver", { id });
    if (r && r.ok) { tostada("Marcado como hecho"); seguirEnDirecto(); }
    else { if (boton) boton.disabled = false; tostada((r && r.error) || "No se ha podido marcar.", true); }
  }
  function prepararDirecto() {
    $("#acciones").hidden = false;
    $("#btn-llega").hidden = E.info.modo !== "demo";
    const inp = $("#fecha-jornada");
    inp.value = E.info.hoy;
    inp.addEventListener("input", () => (inp.dataset.tocada = "1"));
    $("#btn-jornada").addEventListener("click", (e) => accion(e.currentTarget, "/api/jornada", { fecha: inp.value || E.info.hoy }, (r) => {
      inp.value = r.siguiente; delete inp.dataset.tocada; tostada(`Jornada del ${fechaCorta(r.jornada)} en marcha`);
    }));
    $("#btn-venta").addEventListener("click", abrirVenta);
    $("#btn-llega").addEventListener("click", (e) => accion(e.currentTarget, "/api/llega-factura", {}, (r) => tostada(`Ha llegado «${r.documento}»`)));
    setInterval(sondear, 900);
    setInterval(refrescar, 5000);
  }

  // ----------------------------------------------------------------- inicio
  function enlazar() {
    $("#btn-play").addEventListener("click", reproducirPausar);
    $("#btn-reiniciar").addEventListener("click", () => { irA(0); E.reproduciendo = true; pintarPlay(); });
    document.querySelectorAll(".velocidad button").forEach((b) => b.addEventListener("click", () => {
      E.velocidad = parseFloat(b.dataset.vel);
      document.querySelectorAll(".velocidad button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    }));
    $("#deslizador").addEventListener("input", (e) => { pausar(); irA(+e.target.value); });
    $("#kpi-faltan").addEventListener("click", () => abrirKpi("faltan"));
    $("#kpi-cobrar").addEventListener("click", () => abrirKpi("cobrar"));
    $("#kpi-iva").addEventListener("click", () => abrirKpi("iva"));
    $("#kpi-verifactu").addEventListener("click", () => abrirKpi("verifactu"));
    $("#quitar-filtro").addEventListener("click", quitarFiltro);
    $("#btn-ayuda").addEventListener("click", abrirAyuda);
    $("#hoja-cerrar").addEventListener("click", cerrarHoja);
    $("#capa").addEventListener("click", (e) => { if (e.target.id === "capa") cerrarHoja(); });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !$("#capa").hidden) cerrarHoja();
      else if (e.key === " " && e.target === document.body) { e.preventDefault(); reproducirPausar(); }
    });
    window.addEventListener("resize", pintarLienzo);
  }

  function pintarNegocio() {
    const emp = (E.info && E.info.empresa) || {};
    $("#negocio-nombre").textContent = emp.nombre || "Tu negocio";
    $("#negocio-nif").textContent = emp.nif ? "NIF " + emp.nif : "";
    $("#negocio-ini").textContent = (emp.nombre || "TN").split(/\s+/).filter((w) => /^[A-ZÁÉÍÓÚÑ]/i.test(w) && !/^(S\.?L|S\.?A|de|la|el)\.?$/i.test(w)).slice(0, 2).map((w) => w[0].toUpperCase()).join("");
    $("#lider-av").outerHTML = avatarHtml("orquestador", 26);
  }

  async function iniciar() {
    construirMapa();
    enlazar();
    E.d = estadoVacio(null);
    const info = location.protocol.startsWith("http") ? await api("/api/info") : null;
    if (info && info.participantes) {
      E.modo = "directo"; E.info = info; E.ia = !!info.ia;
      const [estado, evs] = await Promise.all([api("/api/estado"), api("/api/eventos?desde=0")]);
      E.base = estado;
      E.eventos = (evs && evs.eventos) || [];
      pintarNegocio();
      estadoVivo("vivo", "En directo");
      prepararDirecto();
      irA(E.eventos.length > 40 ? E.eventos.length : 0);
      if (!E.d.dia) E.d.dia = info.hoy;
      pintarTodo();
      refrescar();
      E.reproduciendo = true;
    } else if (window.TRAZA_DEMO) {
      E.modo = "demo"; E.info = window.TRAZA_DEMO.info; E.eventos = window.TRAZA_DEMO.eventos;
      pintarNegocio();
      estadoVivo("", "Demostración");
      $("#banda-demo").hidden = false;
      irA(0);
      setTimeout(() => { E.reproduciendo = true; pintarPlay(); }, 600);
    } else {
      E.modo = "vacio"; E.info = { fases: [], participantes: [] };
      estadoVivo("error", "Sin datos");
      pintarTodo();
      $("#resumen-dia").textContent = "Abre el panel con «agentes-conta web --demo» o con tu configuración.";
    }
    pintarPlay();
    bucle();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", iniciar);
  else iniciar();
})();
