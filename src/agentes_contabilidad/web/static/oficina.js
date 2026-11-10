/* La Oficina — panel visual de Agentes Contabilidad.
 *
 * Funciona de dos maneras:
 *  - En directo: servido por `agentes-conta web`, lee /api/eventos y deja
 *    lanzar jornadas, ventas y facturas que llegan.
 *  - Grabación: si no hay servidor, reproduce window.TRAZA_DEMO
 *    (generado con `agentes-conta traza --demo -o traza_demo.js`).
 *
 * Sin dependencias. Todo se dibuja en un único SVG.
 */
(function () {
  "use strict";

  const NS = "http://www.w3.org/2000/svg";
  const $ = (s, r = document) => r.querySelector(s);
  const reducido = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ------------------------------------------------------------ personajes
  // Cada agente es una persona con nombre propio que recuerda a su puesto.
  const PERSONAS = {
    orquestador:      { nombre: "Olga",   puesto: "Orquestadora",     color: "#2f6b5a", piel: "#e9b994", pelo: "#3a2a20", peinado: "mono",      accesorio: "campana" },
    recepcion:        { nombre: "Rosa",   puesto: "Recepción",        color: "#3471d8", piel: "#f3cba8", pelo: "#8c3a1c", peinado: "largo",     accesorio: "cascos",   x: 205, y: 236 },
    revisor:          { nombre: "Rubén",  puesto: "Revisor",          color: "#56646c", piel: "#c98e66", pelo: "#1f1a17", peinado: "corto",     accesorio: "gafas",    x: 470, y: 236 },
    reclamador:       { nombre: "Ramón",  puesto: "Reclamador",       color: "#7650d0", piel: "#f0c4a0", pelo: "#6b6b6b", peinado: "calvo",     accesorio: "megafono", x: 752, y: 236 },
    conciliador:      { nombre: "Carlos", puesto: "Conciliador",      color: "#1a8ca8", piel: "#8d5a3b", pelo: "#151210", peinado: "rizado",    accesorio: "corbata",  x: 205, y: 404 },
    detective:        { nombre: "Dani",   puesto: "Detective",        color: "#e86d1f", piel: "#f2c7a2", pelo: "#d9a441", peinado: "flequillo", accesorio: "lupa",     x: 470, y: 392 },
    cobros:           { nombre: "Coral",  puesto: "Cobros",           color: "#c44a86", piel: "#b67a52", pelo: "#2b1b14", peinado: "coleta",    accesorio: "monedas",  x: 752, y: 392 },
    fiscal:           { nombre: "Fátima", puesto: "Fiscal",           color: "#4d58c9", piel: "#d9a27a", pelo: "#24160f", peinado: "panuelo",   accesorio: "calculadora", x: 250, y: 556 },
    emisor_verifactu: { nombre: "Vera",   puesto: "Emisora VeriFactu", color: "#178a4e", piel: "#f6d2b5", pelo: "#a05a2c", peinado: "media",     accesorio: "sello",    x: 752, y: 550 },
  };
  const OLGA = { x: 676, y: 150 };

  const EXTERIORES = {
    buzon:       { nombre: "Buzón",       puesto: "Facturas que llegan", x: 58,  y: 236, ancla: [70, 214] },
    banco:       { nombre: "Banco",       puesto: "Movimientos",         x: 58,  y: 404, ancla: [70, 392] },
    proveedores: { nombre: "Proveedores", puesto: "Te venden",           x: 962, y: 236, ancla: [944, 222] },
    clientes:    { nombre: "Clientes",    puesto: "Te compran",          x: 962, y: 392, ancla: [944, 378] },
    aeat:        { nombre: "Hacienda",    puesto: "AEAT · VeriFactu",    x: 962, y: 550, ancla: [944, 536] },
    tu:          { nombre: "Tú",          puesto: "Tu mesa",             x: 500, y: 560, ancla: [500, 520] },
  };

  const TIPOS = {
    documento: { nombre: "Documento",  var: "--c-documento" },
    banco:     { nombre: "Banco",      var: "--c-banco" },
    falta:     { nombre: "Falta",      var: "--c-falta" },
    email:     { nombre: "Email",      var: "--c-email" },
    verifactu: { nombre: "VeriFactu",  var: "--c-verifactu" },
    alerta:    { nombre: "Error",      var: "--c-alerta" },
    aviso:     { nombre: "Aviso",      var: "--c-aviso" },
    fiscal:    { nombre: "Impuestos",  var: "--c-fiscal" },
    exito:     { nombre: "Resuelto",   var: "--c-exito" },
    fase:      { nombre: "Fase",       var: "--c-fase" },
    jornada:   { nombre: "Jornada",    var: "--c-jornada" },
    sistema:   { nombre: "Sistema",    var: "--c-fase" },
  };
  const colorTipo = (t) => `var(${(TIPOS[t] || TIPOS.sistema).var})`;

  // Hora del reloj y color del cielo según la fase del día
  const RELOJ = { inicio: [8, 0], ingesta: [8, 30], banco: [9, 30], deteccion: [10, 30], reclamaciones: [11, 30],
    cobros: [12, 30], envio_aeat: [13, 30], revision: [16, 0], informe: [17, 30], fin: [20, 0] };
  const CIELO = { inicio: "#ffd6a6", ingesta: "#ffe3bd", banco: "#cfe9ff", deteccion: "#bfe2ff", reclamaciones: "#b3dcff",
    cobros: "#acd8ff", envio_aeat: "#b5dcfb", revision: "#c3d9f2", informe: "#f6bf91", fin: "#28345a", antes: "#c9dff0" };

  // ---------------------------------------------------------------- estado
  const E = {
    modo: "cargando",       // directo | grabacion | vacio
    info: null,
    eventos: [],
    cursor: 0,              // eventos ya mostrados
    reproduciendo: false,
    velocidad: 1,
    generacion: 0,          // se incrementa al rebobinar: cancela animaciones viejas
    base: null,             // estado de "tu mesa" al cargar (modo directo)
    d: null,                // estado derivado de los eventos
    filtro: null,
    rutasVisibles: false,
    porLlegar: 0,
    ocupado: false,
    ia: false,
  };

  function estadoVacio(base) {
    const m = {
      faltantes: new Map(), incidencias: new Map(), cadena: new Map(), informe: null, integra: true,
      emails: 0,
    };
    if (base) {
      (base.faltantes || []).forEach((f) => m.faltantes.set(f.id, f));
      (base.incidencias || []).forEach((i) => m.incidencias.set(i.id, i));
      ((base.verifactu && base.verifactu.cadena) || []).forEach((r) => m.cadena.set(r.numero, r));
      m.informe = base.informe || null;
      m.integra = base.verifactu ? base.verifactu.integra : true;
      m.emails = base.emails || 0;
    }
    return {
      mesa: m, cuenta: {}, rutas: new Map(), dia: null, fase: null,
      hechas: new Set(), noche: false, trabajando: new Set(), enJornada: false,
    };
  }

  // ------------------------------------------------------------- utilidades
  function el(tag, attrs, padre) {
    const n = document.createElementNS(NS, tag);
    if (attrs) for (const k in attrs) n.setAttribute(k, attrs[k]);
    if (padre) padre.appendChild(n);
    return n;
  }
  const esperar = (ms) => new Promise((r) => setTimeout(r, ms));
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const quien = (id) => PERSONAS[id] || EXTERIORES[id] || { nombre: id, puesto: "" };
  const colorDe = (id) => (PERSONAS[id] ? PERSONAS[id].color : id === "tu" ? "var(--accent)" : "var(--muted)");
  const nombreFase = (id) => {
    const f = E.info && E.info.fases ? E.info.fases.find((x) => x.id === id) : null;
    return f ? f.nombre : id;
  };
  function fechaLarga(iso) {
    if (!iso) return "—";
    const d = new Date(iso + "T12:00:00");
    const s = d.toLocaleDateString("es-ES", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
    return s.charAt(0).toUpperCase() + s.slice(1);
  }
  function fechaCorta(iso) {
    const d = new Date(iso + "T12:00:00");
    return d.toLocaleDateString("es-ES", { weekday: "short", day: "numeric", month: "short" });
  }
  function texto(ev) {
    // {agente} → chip con el nombre del personaje
    return esc(ev.texto).replace(/\{(\w+)\}/g, (_, id) => {
      const q = quien(id);
      return `<span class="chip" style="--c:${colorDe(id)}"><i></i>${esc(q.nombre)}</span>`;
    });
  }
  function tostada(msg, mal) {
    const t = $("#tostada");
    t.textContent = msg;
    t.className = "tostada" + (mal ? " mal" : "");
    t.hidden = false;
    clearTimeout(tostada._t);
    tostada._t = setTimeout(() => (t.hidden = true), 3600);
  }

  // ------------------------------------------------------- dibujo personas
  function pelo(p, capa) {
    const c = `style="fill:${p.pelo}"`;
    const gorra = `<path ${c} d="M-17.5,-65 Q-18,-85 0,-85 Q18,-85 17.5,-65 Q13,-75 0,-76 Q-12,-75 -17.5,-65Z"/>`;
    switch (p.peinado) {
      case "largo":
        return capa === "detras"
          ? `<path ${c} d="M-20,-66 Q-21,-87 0,-87 Q21,-87 20,-66 L22,-38 Q12,-33 0,-35 Q-12,-33 -22,-38Z"/>`
          : `<path ${c} d="M-18.5,-60 Q-20,-86 0,-86 Q20,-86 18.5,-60 Q16,-72 8,-74 Q0,-68 -8,-74 Q-16,-72 -18.5,-60Z"/>`;
      case "media":
        return capa === "detras"
          ? `<path ${c} d="M-19.5,-66 Q-20,-86 0,-86 Q20,-86 19.5,-66 L20,-50 Q10,-47 0,-48 Q-10,-47 -20,-50Z"/>`
          : `<path ${c} d="M-18.5,-62 Q-19,-86 0,-86 Q19,-86 18.5,-62 Q12,-76 -2,-74 Q-12,-72 -18.5,-62Z"/>`;
      case "mono":
        return capa === "detras" ? "" : gorra + `<circle ${c} cx="0" cy="-87" r="8"/>`;
      case "coleta":
        return capa === "detras"
          ? `<ellipse ${c} cx="20" cy="-60" rx="6" ry="13" transform="rotate(-18 20 -60)"/>`
          : gorra;
      case "rizado":
        return capa === "detras" ? "" :
          [[-15, -70], [-10, -79], [-2, -83], [7, -81], [14, -73], [-17, -62], [17, -63]]
            .map(([x, y]) => `<circle ${c} cx="${x}" cy="${y}" r="7.5"/>`).join("");
      case "flequillo":
        return capa === "detras" ? "" :
          `<path ${c} d="M-18,-62 Q-19,-87 0,-86 Q19,-87 18,-62 Q15,-71 9,-72 Q4,-66 -2,-72 Q-8,-66 -13,-71 Q-16,-68 -18,-62Z"/>`;
      case "calvo":
        return capa === "detras" ? "" :
          `<path ${c} d="M-17.5,-58 Q-19,-68 -14,-72 L-13,-64Z M17.5,-58 Q19,-68 14,-72 L13,-64Z"/>` +
          `<path ${c} d="M-11,-55 Q0,-42 11,-55 Q9,-49 0,-47 Q-9,-49 -11,-55Z" opacity=".9"/>`;
      case "panuelo":
        return capa === "detras"
          ? `<path style="fill:#7d3f98" d="M-21,-64 Q-22,-88 0,-88 Q22,-88 21,-64 L23,-44 Q0,-38 -23,-44Z"/>`
          : `<path style="fill:#8e4cad" d="M-19,-60 Q-20,-88 0,-88 Q20,-88 19,-60 Q12,-76 0,-76 Q-12,-76 -19,-60Z"/>`;
      default:
        return capa === "detras" ? "" : gorra;
    }
  }

  function accesorio(p) {
    switch (p.accesorio) {
      case "cascos":
        return `<path d="M-19,-64 A19,19 0 0 1 19,-64" fill="none" stroke="#2a3134" stroke-width="3"/>
          <rect x="-23" y="-69" width="7" height="12" rx="3" fill="#2a3134"/><rect x="16" y="-69" width="7" height="12" rx="3" fill="#2a3134"/>
          <path d="M-19,-58 Q-16,-50 -6,-51" fill="none" stroke="#2a3134" stroke-width="1.8"/><circle cx="-6" cy="-51" r="2" fill="#2a3134"/>`;
      case "gafas":
        return `<g fill="none" stroke="#1d2326" stroke-width="1.7"><circle cx="-6.5" cy="-64" r="5.2"/><circle cx="6.5" cy="-64" r="5.2"/><path d="M-1.3,-64 L1.3,-64"/></g>
          <g transform="translate(38,-22) rotate(8)"><rect x="-9" y="-12" width="18" height="24" rx="2" fill="#f7f2e6" stroke="#8a7a5a" stroke-width="1.2"/>
          <rect x="-4" y="-14" width="8" height="4" rx="1" fill="#8a7a5a"/><path d="M-5,-4 l2,2 l4,-4 M-5,4 l2,2 l4,-4" stroke="#178a4e" stroke-width="1.6" fill="none"/></g>`;
      case "megafono":
        return `<g transform="translate(-40,-36) rotate(-22)"><path d="M0,-5 L14,-11 L14,11 L0,5Z" fill="#f08a3c" stroke="#b5561a" stroke-width="1.2"/>
          <rect x="-6" y="-4" width="7" height="8" rx="2" fill="#555"/><path d="M18,-8 q5,8 0,16" stroke="#f08a3c" stroke-width="1.6" fill="none" opacity=".7"/></g>`;
      case "corbata":
        return `<path d="M0,-45 L-4.5,-39 L0,-20 L4.5,-39Z" fill="#c23b3b"/><path d="M-3,-46 L3,-46 L1.8,-42 L-1.8,-42Z" fill="#9a2a2a"/>`;
      case "lupa":
        return `<g transform="translate(36,-30)"><line x1="-5" y1="8" x2="-12" y2="20" stroke="#6b4b2a" stroke-width="4" stroke-linecap="round"/>
          <circle r="10" fill="rgba(190,225,255,.55)" stroke="#6b4b2a" stroke-width="3"/><path d="M-4,-4 q3,-3 7,-1" stroke="#fff" stroke-width="1.5" fill="none" opacity=".8"/></g>
          <path d="M-20,-79 Q0,-96 20,-79 L23,-76 L-23,-76Z" fill="#8a6a3d" opacity=".95"/>`;
      case "monedas":
        return `<g transform="translate(-44,-8)"><ellipse cx="0" cy="0" rx="9" ry="3.5" fill="#d9a62b"/><rect x="-9" y="-10" width="18" height="10" fill="#e8b93c"/>
          <ellipse cx="0" cy="-10" rx="9" ry="3.5" fill="#f5cf5c" stroke="#c6941f" stroke-width=".8"/><text x="0" y="-8" text-anchor="middle" font-size="6" font-weight="700" fill="#9a6e10">€</text></g>`;
      case "calculadora":
        return `<g transform="translate(-44,-16)"><rect x="-10" y="-13" width="20" height="26" rx="3" fill="#3a4448"/><rect x="-7" y="-10" width="14" height="6" rx="1" fill="#b9e6c9"/>
          ${[0, 1, 2].map((r) => [0, 1, 2].map((c) => `<rect x="${-7 + c * 5}" y="${-1 + r * 4.5}" width="4" height="3" rx=".8" fill="#cfd8db"/>`).join("")).join("")}</g>`;
      case "sello":
        return `<g transform="translate(34,-20)"><rect x="-4" y="-16" width="8" height="12" rx="3" fill="#7a4b2a"/><circle cx="0" cy="-17" r="5" fill="#7a4b2a"/>
          <rect x="-10" y="-5" width="20" height="7" rx="2" fill="#178a4e"/></g>
          <g transform="translate(-44,-6)"><rect x="-9" y="-12" width="18" height="15" rx="1.5" fill="#fff" stroke="#c8d0cc"/><circle cx="0" cy="-4.5" r="4" fill="none" stroke="#178a4e" stroke-width="1.4"/></g>`;
      default:
        return "";
    }
  }

  function svgPersonaSentada(p) {
    const s = p.color, k = p.piel;
    return `
      <ellipse class="foco" cx="0" cy="30" rx="92" ry="26"/>
      <ellipse class="sombra" cx="0" cy="34" rx="70" ry="8"/>
      <rect class="silla" x="-28" y="-82" width="56" height="66" rx="15"/>
      <g class="cuerpo-p">
        ${pelo(p, "detras")}
        <path style="fill:${s}" d="M-26,4 L-26,-26 Q-26,-47 -9,-48 L9,-48 Q26,-47 26,-26 L26,4Z"/>
        <path d="M-7,-48 L0,-40 L7,-48" fill="none" stroke="rgba(0,0,0,.2)" stroke-width="2"/>
        <rect x="-5" y="-53" width="10" height="7" style="fill:${k}"/>
        <circle cx="-17" cy="-63" r="3.6" style="fill:${k}"/><circle cx="17" cy="-63" r="3.6" style="fill:${k}"/>
        <circle cx="0" cy="-65" r="17.5" style="fill:${k}"/>
        ${pelo(p, "delante")}
        <g class="ojos"><circle cx="-6.5" cy="-64" r="2.1" fill="#1d2326"/><circle cx="6.5" cy="-64" r="2.1" fill="#1d2326"/></g>
        <circle cx="-11" cy="-57" r="3.2" fill="#ff7f6e" opacity=".25"/><circle cx="11" cy="-57" r="3.2" fill="#ff7f6e" opacity=".25"/>
        <path d="M-4.5,-56.5 Q0,-52.5 4.5,-56.5" fill="none" stroke="#7a3b2e" stroke-width="1.8" stroke-linecap="round"/>
        ${p.accesorio === "corbata" ? accesorio(p) : ""}
      </g>
      <rect class="madera" x="-66" y="-6" width="132" height="32" rx="7"/>
      <rect class="madera-osc" x="-66" y="19" width="132" height="10" rx="5"/>
      <rect x="-18" y="-28" width="36" height="23" rx="3" fill="#cfd7d9"/>
      <circle cx="0" cy="-16.5" r="2.6" fill="#ffffff" opacity=".85"/>
      <rect x="-22" y="-6" width="44" height="4" rx="2" fill="#a9b3b6"/>
      <g class="mano i"><path d="M-24,-31 Q-35,-14 -28,-3" fill="none" style="stroke:${s}" stroke-width="9.5" stroke-linecap="round"/><circle cx="-27.5" cy="-3" r="5.2" style="fill:${k}"/></g>
      <g class="mano d"><path d="M24,-31 Q35,-14 28,-3" fill="none" style="stroke:${s}" stroke-width="9.5" stroke-linecap="round"/><circle cx="27.5" cy="-3" r="5.2" style="fill:${k}"/></g>
      ${p.accesorio !== "corbata" ? accesorio(p) : ""}
      <g class="placa-nombre"><rect class="placa" x="-50" y="34" width="100" height="31" rx="9"/>
        <text class="txt-nombre" x="0" y="48.5" text-anchor="middle">${esc(p.nombre)}</text>
        <text class="txt-puesto" x="0" y="60" text-anchor="middle">${esc(p.puesto)}</text></g>
      <g class="insignia" transform="translate(56,-78)"><circle r="11" style="fill:${s}" stroke="var(--panel)" stroke-width="2"/>
        <text class="insignia-num" y="3.8" text-anchor="middle" font-size="10.5" font-weight="700" fill="#fff">0</text></g>
      <g class="exclamacion" transform="translate(-34,-92)"><circle r="10" style="fill:var(--c-alerta)"/><text y="4.5" text-anchor="middle" font-size="14" font-weight="800" fill="#fff">!</text></g>
      <g class="zzz" transform="translate(24,-90)"><text font-size="13" font-weight="700" style="fill:var(--muted)">z<tspan dx="2" dy="-5" font-size="10">z</tspan></text></g>`;
  }

  function svgOlga(p) {
    const s = p.color, k = p.piel;
    return `
      <ellipse class="foco" cx="0" cy="2" rx="46" ry="14"/>
      <ellipse class="sombra" cx="0" cy="2" rx="26" ry="6"/>
      <g class="cuerpo-p">
        <rect x="-10" y="-38" width="8" height="38" rx="3" fill="#2b3438"/><rect x="2" y="-38" width="8" height="38" rx="3" fill="#2b3438"/>
        <ellipse cx="-6" cy="0" rx="7" ry="3" fill="#1b2023"/><ellipse cx="6" cy="0" rx="7" ry="3" fill="#1b2023"/>
        <path style="fill:${s}" d="M-18,-34 L-16,-72 Q-15,-84 -4,-85 L4,-85 Q15,-84 16,-72 L18,-34Z"/>
        <rect x="-5" y="-91" width="10" height="7" style="fill:${k}"/>
        <g transform="translate(0,-38)">
          <circle cx="-17" cy="-63" r="3.6" style="fill:${k}"/><circle cx="17" cy="-63" r="3.6" style="fill:${k}"/>
          <circle cx="0" cy="-65" r="17.5" style="fill:${k}"/>
          ${pelo(p, "delante")}
          <g class="ojos"><circle cx="-6.5" cy="-64" r="2.1" fill="#1d2326"/><circle cx="6.5" cy="-64" r="2.1" fill="#1d2326"/></g>
          <circle cx="-11" cy="-57" r="3.2" fill="#ff7f6e" opacity=".25"/><circle cx="11" cy="-57" r="3.2" fill="#ff7f6e" opacity=".25"/>
          <path d="M-4.5,-56.5 Q0,-52 4.5,-56.5" fill="none" stroke="#7a3b2e" stroke-width="1.8" stroke-linecap="round"/>
        </g>
        <g class="brazo-senala"><path d="M-14,-78 Q-30,-92 -42,-104" fill="none" style="stroke:${s}" stroke-width="8.5" stroke-linecap="round"/>
          <circle cx="-43" cy="-105" r="5" style="fill:${k}"/><rect x="-49" y="-117" width="4" height="12" rx="1.5" fill="#d23f3f" transform="rotate(-30 -47 -111)"/></g>
        <path d="M14,-78 Q22,-60 20,-46" fill="none" style="stroke:${s}" stroke-width="8.5" stroke-linecap="round"/>
        <circle cx="20" cy="-45" r="5" style="fill:${k}"/>
        <g class="campana" transform="translate(22,-38)"><path d="M-6,0 Q-6,-10 0,-10 Q6,-10 6,0Z" fill="#e2b23c" stroke="#b98a1a" stroke-width="1"/><circle cy="1.5" r="1.6" fill="#b98a1a"/></g>
      </g>
      <g class="placa-nombre"><rect class="placa" x="-50" y="8" width="100" height="31" rx="9"/>
        <text class="txt-nombre" x="0" y="22.5" text-anchor="middle">${esc(p.nombre)}</text>
        <text class="txt-puesto" x="0" y="34" text-anchor="middle">${esc(p.puesto)}</text></g>
      <g class="insignia" transform="translate(30,-140)"><circle r="11" style="fill:${s}" stroke="var(--panel)" stroke-width="2"/>
        <text class="insignia-num" y="3.8" text-anchor="middle" font-size="10.5" font-weight="700" fill="#fff">0</text></g>
      <g class="exclamacion" transform="translate(-30,-150)"></g>
      <g class="zzz" transform="translate(24,-150)"><text font-size="13" font-weight="700" style="fill:var(--muted)">z<tspan dx="2" dy="-5" font-size="10">z</tspan></text></g>`;
  }

  function svgTu() {
    return `
      <ellipse class="foco" cx="0" cy="30" rx="96" ry="26"/>
      <ellipse class="sombra" cx="0" cy="34" rx="78" ry="8"/>
      <rect x="-28" y="-82" width="56" height="66" rx="15" fill="none" style="stroke:var(--accent)" stroke-width="2" stroke-dasharray="5 5" opacity=".7"/>
      <g class="cuerpo-p" opacity=".75">
        <path d="M-26,4 L-26,-26 Q-26,-47 -9,-48 L9,-48 Q26,-47 26,-26 L26,4Z" style="fill:var(--panel-2);stroke:var(--accent)" stroke-width="2" stroke-dasharray="5 4"/>
        <circle cx="0" cy="-65" r="17.5" style="fill:var(--panel-2);stroke:var(--accent)" stroke-width="2" stroke-dasharray="5 4"/>
        <text x="0" y="-60" text-anchor="middle" font-size="14" font-weight="700" style="fill:var(--accent);font-family:var(--f-display)">Tú</text>
      </g>
      <rect class="madera" x="-76" y="-6" width="152" height="32" rx="7"/>
      <rect class="madera-osc" x="-76" y="19" width="152" height="10" rx="5"/>
      <g class="taza" transform="translate(-56,-8)"><rect x="-6" y="-10" width="12" height="12" rx="2.5" fill="#fff" stroke="#c8d0cc"/>
        <path d="M6,-7 q5,0 5,4 q0,4 -5,4" fill="none" stroke="#c8d0cc" stroke-width="1.6"/><path d="M-2,-14 q2,-3 0,-6 M2,-14 q2,-3 0,-6" stroke="var(--muted)" stroke-width="1.2" fill="none" opacity=".6"/></g>
      <g class="pila" transform="translate(44,-4)"></g>
      <g class="placa-nombre"><rect class="placa" x="-56" y="34" width="112" height="31" rx="9"/>
        <text class="txt-nombre" x="0" y="48.5" text-anchor="middle">Tu mesa</text>
        <text class="txt-puesto pendientes" x="0" y="60" text-anchor="middle">Nada pendiente</text></g>
      <g class="insignia" transform="translate(66,-60)"><circle r="12" style="fill:var(--c-alerta)" stroke="var(--panel)" stroke-width="2"/>
        <text class="insignia-num" y="4" text-anchor="middle" font-size="11" font-weight="700" fill="#fff">0</text></g>`;
  }

  function svgExterior(id) {
    if (id === "buzon") return `
      <rect class="borde-pared" x="-58" y="-62" width="8" height="124" rx="3"/>
      <rect x="-6" y="-8" width="8" height="44" rx="2" fill="#6d5a4a"/>
      <g class="puerta-buzon"><rect x="-28" y="-44" width="52" height="38" rx="12" fill="#cf3f35"/>
      <rect x="-28" y="-44" width="52" height="12" rx="6" fill="#e05a4f"/>
      <rect x="-18" y="-26" width="32" height="4" rx="2" fill="#7a1d18"/>
      <g class="bandera"><rect x="23" y="-48" width="3" height="20" fill="#444"/><rect x="26" y="-48" width="12" height="8" rx="1" fill="#ffd34d"/></g></g>
      <ellipse class="halo" cx="-2" cy="-24" rx="40" ry="30" style="fill:var(--c-documento)"/>
      <g transform="translate(0,46)"><rect class="placa" x="-40" y="0" width="80" height="22" rx="7"/><text class="txt-cartel" x="0" y="14.5" text-anchor="middle">BUZÓN</text></g>`;
    if (id === "banco") return `
      <rect class="borde-pared" x="-58" y="-62" width="8" height="124" rx="3"/>
      <rect x="-36" y="-44" width="72" height="72" rx="10" fill="#7d8e95"/>
      <rect x="-30" y="-38" width="60" height="60" rx="8" fill="#93a4ab"/>
      <g class="puerta"><circle cx="0" cy="-8" r="22" fill="#b4c3c9" stroke="#6b7c83" stroke-width="3"/>
      <g stroke="#6b7c83" stroke-width="3" stroke-linecap="round"><line x1="0" y1="-24" x2="0" y2="8"/><line x1="-16" y1="-8" x2="16" y2="-8"/><line x1="-11" y1="-19" x2="11" y2="3"/><line x1="11" y1="-19" x2="-11" y2="3"/></g>
      <circle cx="0" cy="-8" r="6" fill="#6b7c83"/></g>
      <ellipse class="halo" cx="0" cy="-8" rx="44" ry="44" style="fill:var(--c-banco)"/>
      <g transform="translate(0,40)"><rect class="placa" x="-40" y="0" width="80" height="22" rx="7"/><text class="txt-cartel" x="0" y="14.5" text-anchor="middle">BANCO</text></g>`;
    const etiqueta = { proveedores: "PROVEEDORES", clientes: "CLIENTES", aeat: "HACIENDA" }[id];
    const icono = {
      proveedores: `<g transform="translate(-26,-58)" fill="none" style="stroke:var(--ink)" stroke-width="1.6"><rect x="-7" y="-5" width="10" height="8" rx="1"/><path d="M3,-2 h4 l2,3 v2 h-6z"/><circle cx="-4" cy="4" r="1.6"/><circle cx="6" cy="4" r="1.6"/></g>`,
      clientes: `<g transform="translate(-26,-58)" fill="none" style="stroke:var(--ink)" stroke-width="1.6"><circle cx="0" cy="-3" r="3"/><path d="M-5,5 q5,-6 10,0"/></g>`,
      aeat: `<g transform="translate(-26,-58)" fill="none" style="stroke:var(--ink)" stroke-width="1.4"><path d="M-7,-2 L0,-6 L7,-2Z"/><path d="M-5,-1 v6 M-1.7,-1 v6 M1.7,-1 v6 M5,-1 v6 M-7,5.5 h14"/></g>`,
    }[id];
    return `
      <rect class="borde-pared" x="30" y="-62" width="8" height="124" rx="3"/>
      <rect x="-10" y="-46" width="44" height="84" rx="4" style="fill:var(--wall-edge)"/>
      <rect class="halo" x="-6" y="-42" width="36" height="78" rx="2" fill="#ffe6a1"/>
      <g class="puerta"><rect x="-6" y="-42" width="36" height="78" rx="2" class="madera"/>
        <rect x="-1" y="-36" width="26" height="28" rx="2" class="madera-osc" opacity=".55"/><rect x="-1" y="-2" width="26" height="30" rx="2" class="madera-osc" opacity=".55"/>
        <circle cx="0" cy="0" r="2.8" fill="#e2b23c"/></g>
      <g transform="translate(${30 - (etiqueta.length * 7.4 + 36)},0)"><rect class="placa" x="0" y="-72" width="${etiqueta.length * 7.4 + 36}" height="22" rx="7"/>
      <g transform="translate(38,0)">${icono}</g><text class="txt-cartel" x="26" y="-57" text-anchor="start">${etiqueta}</text></g>`;
  }

  function avatar(id, tam) {
    tam = tam || 30;
    const p = PERSONAS[id];
    if (p) {
      return `<svg viewBox="-24 -92 48 48" width="${tam}" height="${tam}" aria-hidden="true">
        <circle cx="0" cy="-68" r="24" style="fill:${p.color}" opacity=".22"/>
        ${pelo(p, "detras")}<circle cx="0" cy="-65" r="17.5" style="fill:${p.piel}"/>${pelo(p, "delante")}
        <circle cx="-6.5" cy="-64" r="2.1" fill="#1d2326"/><circle cx="6.5" cy="-64" r="2.1" fill="#1d2326"/>
        <path d="M-4.5,-56.5 Q0,-52.5 4.5,-56.5" fill="none" stroke="#7a3b2e" stroke-width="1.8" stroke-linecap="round"/></svg>`;
    }
    const icon = {
      buzon: `<rect x="-9" y="-6" width="18" height="12" rx="2" fill="none" stroke="#fff" stroke-width="2"/><path d="M-9,-5 L0,2 L9,-5" fill="none" stroke="#fff" stroke-width="2"/>`,
      banco: `<text y="6" text-anchor="middle" font-size="17" font-weight="700" fill="#fff">€</text>`,
      proveedores: `<path d="M-10,-5 h11 v9 h-11z M1,-2 h5 l3,3 v3 h-8z" fill="#fff"/><circle cx="-6" cy="6" r="2.4" fill="#fff"/><circle cx="5" cy="6" r="2.4" fill="#fff"/>`,
      clientes: `<circle cx="0" cy="-4" r="4.5" fill="#fff"/><path d="M-8,8 q8,-10 16,0z" fill="#fff"/>`,
      aeat: `<path d="M-9,-3 L0,-9 L9,-3Z M-7,-1 v8 M-2.5,-1 v8 M2.5,-1 v8 M7,-1 v8 M-9,8 h18" fill="#fff" stroke="#fff" stroke-width="1.6"/>`,
      tu: `<text y="5" text-anchor="middle" font-size="12" font-weight="700" fill="#fff">Tú</text>`,
    }[id] || "";
    const fondo = { buzon: "#cf3f35", banco: "#5f747c", proveedores: "#8a6a3d", clientes: "#c44a86", aeat: "#3a4a8c", tu: "var(--accent)" }[id] || "var(--muted)";
    return `<svg viewBox="-15 -15 30 30" width="${tam}" height="${tam}" aria-hidden="true"><circle r="15" style="fill:${fondo}"/>${icon}</svg>`;
  }

  // ---------------------------------------------------------------- escena
  const S = {};   // referencias a nodos de la escena

  function construirEscena() {
    const svg = $("#escena");
    svg.innerHTML = `
      <defs>
        <pattern id="papel" width="16" height="16" patternUnits="userSpaceOnUse">
          <path d="M16 0H0V16" fill="none" class="cuadricula-fina" stroke-width="1"/></pattern>
        <pattern id="papel-grande" width="80" height="80" patternUnits="userSpaceOnUse">
          <rect width="80" height="80" fill="url(#papel)"/><path d="M80 0H0V80" fill="none" class="cuadricula-gruesa" stroke-width="1.2"/></pattern>
        <linearGradient id="luz-ventana" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".55"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
      </defs>
      <g id="capa-fondo"></g>
      <g id="capa-rutas"></g>
      <g id="capa-exteriores"></g>
      <g id="capa-personas"></g>
      <rect class="noche-capa" x="0" y="0" width="1000" height="640"/>
      <g id="capa-vuelos"></g>
      <g id="capa-bocadillos"></g>`;
    S.svg = svg;
    S.fondo = $("#capa-fondo", svg);
    S.rutas = $("#capa-rutas", svg);
    S.vuelos = $("#capa-vuelos", svg);
    S.bocadillos = $("#capa-bocadillos", svg);

    // Suelo de papel cuadriculado (como un libro de cuentas) y pared del fondo
    S.fondo.innerHTML = `
      <rect class="suelo" x="0" y="0" width="1000" height="640"/>
      <rect x="0" y="112" width="1000" height="528" fill="url(#papel-grande)"/>
      <rect class="pared" x="0" y="0" width="1000" height="112"/>
      <rect class="borde-pared" x="0" y="106" width="1000" height="8"/>
      <g id="ventanas">
        ${[48, 838].map((x) => `
          <rect x="${x}" y="18" width="128" height="72" rx="6" style="fill:var(--wall-edge)"/>
          <rect class="cielo" x="${x + 5}" y="23" width="118" height="62" rx="3" fill="${CIELO.antes}"/>
          <circle class="sol" cx="${x + 92}" cy="44" r="10" fill="#ffe08a" opacity=".9"/>
          <rect x="${x + 5}" y="23" width="118" height="62" rx="3" fill="url(#luz-ventana)"/>
          <rect x="${x + 62}" y="23" width="4" height="62" style="fill:var(--wall-edge)"/>
          <rect x="${x + 5}" y="52" width="118" height="3" style="fill:var(--wall-edge)"/>`).join("")}
      </g>
      <g id="reloj" transform="translate(246,58)">
        <circle r="30" class="panel-fill" style="stroke:var(--wall-edge)" stroke-width="4"/>
        ${Array.from({ length: 12 }, (_, i) => `<line x1="0" y1="-24" x2="0" y2="${i % 3 ? -21 : -18}" style="stroke:var(--muted)" stroke-width="${i % 3 ? 1.2 : 2}" transform="rotate(${i * 30})"/>`).join("")}
        <g class="agujas" id="aguja-h"><line x1="0" y1="3" x2="0" y2="-14" style="stroke:var(--ink)" stroke-width="3.2" stroke-linecap="round"/></g>
        <g class="agujas" id="aguja-m"><line x1="0" y1="4" x2="0" y2="-21" style="stroke:var(--accent)" stroke-width="2" stroke-linecap="round"/></g>
        <circle r="2.6" style="fill:var(--ink)"/>
      </g>
      <g id="pizarra" transform="translate(372,14)">
        <rect width="270" height="86" rx="6" fill="#7d8e95"/>
        <rect x="5" y="5" width="260" height="76" rx="3" fill="#fbfdfc"/>
        <text class="txt-pequeno" x="14" y="22">Pizarra · ahora toca</text>
        <text class="txt-pizarra pizarra-texto" id="pizarra-texto" x="135" y="56" text-anchor="middle" style="fill:#18272b">Antes de empezar</text>
        <rect x="190" y="80" width="30" height="5" rx="2" fill="#3471d8"/><rect x="226" y="80" width="22" height="5" rx="2" fill="#d23f3f"/>
      </g>
      <g id="cafetera" transform="translate(330,148)">
        <rect x="-16" y="-28" width="32" height="34" rx="5" fill="#3a4448"/><rect x="-11" y="-22" width="22" height="9" rx="2" fill="#5d6b70"/>
        <rect x="-7" y="-6" width="14" height="10" rx="2" fill="#fff"/><circle cx="8" cy="-17" r="2" fill="#3cc49b"/>
        <rect x="-22" y="6" width="44" height="6" rx="3" class="madera-osc"/>
      </g>
      <g id="planta-1" transform="translate(110,600)">
        <ellipse cx="0" cy="8" rx="20" ry="5" class="sombra"/><path d="M-13,-6 h26 l-4,16 h-18z" fill="#c4774c"/>
        <path d="M0,-6 C-6,-30 -22,-34 -24,-40 C-10,-38 -2,-28 0,-6 C2,-30 12,-44 22,-44 C16,-34 6,-28 0,-6 C-2,-24 2,-40 4,-52 C8,-40 4,-24 0,-6Z" fill="#3f9b63"/>
      </g>
      <g id="planta-2" transform="translate(900,612)">
        <ellipse cx="0" cy="6" rx="18" ry="5" class="sombra"/><rect x="-12" y="-10" width="24" height="16" rx="3" fill="#5d7a8a"/>
        <circle cx="-7" cy="-18" r="10" fill="#2f8a57"/><circle cx="6" cy="-22" r="11" fill="#3f9b63"/><circle cx="0" cy="-32" r="9" fill="#4fae72"/>
      </g>`;
    S.pizarra = $("#pizarra-texto", svg);
    S.cielos = Array.from(svg.querySelectorAll(".cielo"));
    S.soles = Array.from(svg.querySelectorAll(".sol"));
    S.agujaH = $("#aguja-h", svg);
    S.agujaM = $("#aguja-m", svg);

    // Exteriores
    const capaExt = $("#capa-exteriores", svg);
    S.ext = {};
    for (const id of ["buzon", "banco", "proveedores", "clientes", "aeat"]) {
      const x = EXTERIORES[id];
      const g = el("g", { class: "exterior" + (id === "buzon" || id === "banco" ? " izq" : ""), transform: `translate(${x.x},${x.y})`, tabindex: "0", role: "button", "aria-label": `${x.nombre}: ver sus mensajes`, "data-id": id }, capaExt);
      g.innerHTML = svgExterior(id);
      g.addEventListener("click", () => filtrarPor(id));
      g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); filtrarPor(id); } });
      S.ext[id] = g;
    }

    // Personas (orden por profundidad: de arriba abajo)
    const capaP = $("#capa-personas", svg);
    S.p = {};
    const orden = Object.keys(PERSONAS).filter((k) => k !== "orquestador").sort((a, b) => PERSONAS[a].y - PERSONAS[b].y);
    const crear = (id, x, y, html) => {
      const p = quien(id);
      const g = el("g", { class: "persona", transform: `translate(${x},${y})`, tabindex: "0", role: "button", "aria-label": `${p.nombre}, ${p.puesto}`, "data-id": id }, capaP);
      g.innerHTML = html;
      g.addEventListener("click", () => abrirPersona(id));
      g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); abrirPersona(id); } });
      S.p[id] = g;
      return g;
    };
    crear("orquestador", OLGA.x, OLGA.y, svgOlga(PERSONAS.orquestador));
    orden.filter((id) => PERSONAS[id].y < 500).forEach((id) => crear(id, PERSONAS[id].x, PERSONAS[id].y, svgPersonaSentada(PERSONAS[id])));
    crear("tu", EXTERIORES.tu.x, EXTERIORES.tu.y, svgTu());
    orden.filter((id) => PERSONAS[id].y >= 500).forEach((id) => crear(id, PERSONAS[id].x, PERSONAS[id].y, svgPersonaSentada(PERSONAS[id])));
    S.pila = S.p.tu.querySelector(".pila");
    S.pendientesTxt = S.p.tu.querySelector(".pendientes");
  }

  function ancla(id) {
    if (id === "orquestador") return [OLGA.x, OLGA.y - 110];
    if (PERSONAS[id]) return [PERSONAS[id].x, PERSONAS[id].y - 40];
    if (EXTERIORES[id]) return EXTERIORES[id].ancla;
    return [500, 320];
  }

  // ---------------------------------------------------------- bocadillos
  const bocadilloActivo = {};
  function bocadillo(id, txt, tipo, ms) {
    if (!txt) return;
    const prev = bocadilloActivo[id];
    if (prev) prev.remove();
    let [x, y] = ancla(id);
    y -= id === "orquestador" ? 58 : id === "tu" ? 66 : 70;
    if (id === "orquestador") x += 92;
    const corto = txt.length > 34 ? txt.slice(0, 33) + "…" : txt;
    const ancho = Math.max(60, corto.length * 6.6 + 26);
    x = Math.min(Math.max(x, ancho / 2 + 6), 1000 - ancho / 2 - 6);
    // El grupo exterior coloca; el interior anima (una animación CSS de transform
    // pisaría el atributo transform del mismo elemento)
    const exterior = el("g", { class: "bocadillo", transform: `translate(${x},${y})` }, S.bocadillos);
    const g = el("g", { class: "entra" }, exterior);
    el("rect", { x: -ancho / 2, y: -15, width: ancho, height: 28, rx: 12 }, g);
    el("rect", { class: "franja", x: -ancho / 2, y: -15, width: 6, height: 28, rx: 3, style: `fill:${colorTipo(tipo)}` }, g);
    if (id !== "orquestador") el("path", { d: "M-6,12.5 L0,20 L6,12.5Z", style: "fill:var(--panel)" }, g);
    const t = el("text", { x: 3, y: 4, "text-anchor": "middle" }, g);
    t.textContent = corto;
    bocadilloActivo[id] = exterior;
    setTimeout(() => { if (bocadilloActivo[id] === exterior) { exterior.remove(); delete bocadilloActivo[id]; } }, ms);
  }
  function limpiarBocadillos() {
    for (const k in bocadilloActivo) { bocadilloActivo[k].remove(); delete bocadilloActivo[k]; }
  }

  // --------------------------------------------------------------- vuelos
  function forma(tipo, de, a) {
    if (tipo === "email") return "sobre";
    if (de === "buzon") return "doc";
    if (de === "banco") return "moneda";
    if (a === "aeat") return "sello";
    if (a === "tu" && (tipo === "alerta" || tipo === "aviso" || tipo === "fiscal")) return "nota";
    return "avion";
  }
  function dibujarForma(g, f, tipo) {
    const c = colorTipo(tipo);
    switch (f) {
      case "sobre":
        g.innerHTML = `<rect x="-12" y="-8" width="24" height="16" rx="2" style="fill:var(--panel);stroke:${c}" stroke-width="2"/>
          <path d="M-12,-7 L0,2 L12,-7" fill="none" style="stroke:${c}" stroke-width="2"/>`; break;
      case "doc":
        g.innerHTML = `<path d="M-9,-12 h12 l6,6 v18 h-18z" style="fill:var(--panel);stroke:${c}" stroke-width="1.8"/>
          <path d="M-5,-2 h10 M-5,3 h10 M-5,8 h7" style="stroke:${c}" stroke-width="1.6"/>`; break;
      case "moneda":
        g.innerHTML = `<circle r="10" fill="#f0c247" stroke="#b98a1a" stroke-width="2"/><text y="4.5" text-anchor="middle" font-size="12" font-weight="800" fill="#8a640c">€</text>`; break;
      case "sello":
        g.innerHTML = `<circle r="11" style="fill:${c}"/><circle r="7.5" fill="none" stroke="#fff" stroke-width="1.4" stroke-dasharray="2 2"/>
          <path d="M-4,0 l3,3 l5,-6" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round"/>`; break;
      case "nota":
        g.innerHTML = `<path d="M-10,-10 h20 v14 l-6,6 h-14z" style="fill:${c}" opacity=".92"/><path d="M10,4 h-6 v6" fill="rgba(0,0,0,.18)"/>
          <path d="M-6,-4 h12 M-6,1 h8" stroke="#fff" stroke-width="1.6"/>`; break;
      default:
        g.innerHTML = `<path d="M-12,5 L13,-2 L-5,-10 Z" style="fill:${c}"/><path d="M-12,5 L13,-2 L-2,1 Z" fill="rgba(0,0,0,.18)"/>
          <path d="M-2,1 L-4,8 L13,-2" style="fill:${c}" opacity=".8"/>`;
    }
  }

  function volar(de, a, tipo, dur, gen) {
    return new Promise((resolver) => {
      const [x0, y0] = ancla(de);
      const [x1, y1] = ancla(a);
      const dist = Math.hypot(x1 - x0, y1 - y0);
      const cx = (x0 + x1) / 2, cy = Math.min(y0, y1) - 40 - dist * 0.16;
      const f = forma(tipo, de, a);
      const g = el("g", { class: "vuelo" }, S.vuelos);
      const sombra = el("ellipse", { class: "sombra", rx: 9, ry: 3.2 }, g);
      const item = el("g", {}, g);
      dibujarForma(item, f, tipo);
      if (reducido) dur = 1;
      const t0 = performance.now();
      const paso = (ahora) => {
        if (gen !== E.generacion) { g.remove(); return resolver(); }
        let t = Math.min(1, (ahora - t0) / dur);
        const e = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
        const u = 1 - e;
        const x = u * u * x0 + 2 * u * e * cx + e * e * x1;
        const y = u * u * y0 + 2 * u * e * cy + e * e * y1;
        const dx = 2 * u * (cx - x0) + 2 * e * (x1 - cx);
        const dy = 2 * u * (cy - y0) + 2 * e * (y1 - cy);
        const ang = f === "avion" ? Math.atan2(dy, dx) * 180 / Math.PI : Math.sin(t * Math.PI * 2) * 8;
        const escala = 1 + Math.sin(e * Math.PI) * 0.25;
        item.setAttribute("transform", `translate(${x.toFixed(1)},${y.toFixed(1)}) rotate(${ang.toFixed(1)}) scale(${escala.toFixed(2)})`);
        const sx = x0 + (x1 - x0) * e, sy = y0 + (y1 - y0) * e + 30;
        sombra.setAttribute("cx", sx.toFixed(1));
        sombra.setAttribute("cy", sy.toFixed(1));
        sombra.setAttribute("opacity", (0.5 - Math.sin(e * Math.PI) * 0.3).toFixed(2));
        if (t < 1) requestAnimationFrame(paso);
        else {
          g.remove();
          if (!reducido) {
            const onda = el("circle", { class: "onda", cx: x1, cy: y1, r: 6, style: `stroke:${colorTipo(tipo)}` }, S.vuelos);
            setTimeout(() => onda.remove(), 800);
          }
          resolver();
        }
      };
      requestAnimationFrame(paso);
    });
  }

  // --------------------------------------------------------------- rutas
  function claveRuta(de, a) { return de + ">" + a; }
  function dibujarRutas(recientes) {
    S.rutas.innerHTML = "";
    const max = Math.max(1, ...Array.from(E.d.rutas.values(), (r) => r.n));
    for (const [k, r] of E.d.rutas) {
      const [x0, y0] = ancla(r.de), [x1, y1] = ancla(r.a);
      const dist = Math.hypot(x1 - x0, y1 - y0);
      const cx = (x0 + x1) / 2, cy = Math.min(y0, y1) - 40 - dist * 0.16;
      const ancho = 1.5 + 7 * Math.sqrt(r.n / max);
      el("path", { class: "ruta" + (recientes && recientes.has(k) ? " reciente" : ""), d: `M${x0},${y0} Q${cx},${cy} ${x1},${y1}`, "stroke-width": ancho.toFixed(1), style: `stroke:${colorTipo(r.tipo)}`, "data-k": k }, S.rutas);
      const mx = 0.25 * x0 + 0.5 * cx + 0.25 * x1, my = 0.25 * y0 + 0.5 * cy + 0.25 * y1;
      const t = el("text", { class: "ruta-num", x: mx, y: my - 4, "text-anchor": "middle" }, S.rutas);
      t.textContent = r.n;
    }
  }

  // ------------------------------------------------- aplicar un evento
  // Actualiza el estado derivado (sin animar). Es idempotente sobre la base.
  function aplicar(ev) {
    const d = E.d, m = d.mesa, det = ev.detalle || {};
    const cuenta = (id, campo) => { (d.cuenta[id] = d.cuenta[id] || { env: 0, rec: 0 })[campo]++; };
    if (ev.dia) d.dia = ev.dia;

    if (ev.tema === "ciclo.iniciado") {
      d.enJornada = true; d.fase = null; d.hechas = new Set(); d.noche = false; d.trabajando = new Set();
    } else if (ev.tema === "ciclo.terminado") {
      if (d.fase) d.hechas.add(d.fase);
      d.fase = null; d.enJornada = false; d.noche = true; d.trabajando = new Set();
      E.info.fases.forEach((f) => d.hechas.add(f.id));
    } else if (ev.tipo === "fase") {
      if (d.enJornada) {
        if (d.fase) d.hechas.add(d.fase);
        d.fase = det.fase; d.noche = false;
      }
      // Fuera de jornada (p.ej. llega una factura suelta) solo se ponen a trabajar
      d.trabajando = new Set(ev.a);
    }

    if (ev.tipo !== "jornada") {
      cuenta(ev.de, "env");
      (ev.a || []).forEach((a) => {
        cuenta(a, "rec");
        if (ev.tipo !== "fase") {
          const k = claveRuta(ev.de, a);
          const r = d.rutas.get(k) || { de: ev.de, a, n: 0, tipo: ev.tipo };
          r.n++; r.tipo = ev.tipo;
          d.rutas.set(k, r);
        }
      });
    }

    switch (ev.tema) {
      case "factura.faltante":
      case "reclamacion.enviada":
        if (det.faltante) m.faltantes.set(det.faltante.id, det.faltante);
        break;
      case "escalado.humano":
        if (det.faltante) m.faltantes.set(det.faltante.id, Object.assign({}, det.faltante, { estado: "escalada" }));
        break;
      case "factura.faltante_resuelta":
        if (det.faltante) m.faltantes.delete(det.faltante.id);
        break;
      case "revision.incidencia":
        if (det.incidencia) m.incidencias.set(det.incidencia.id, det.incidencia);
        break;
      case "revision.resuelta":
        if (det.incidencia) m.incidencias.delete(det.incidencia.id);
        break;
      case "factura.emitida":
        if (det.registro && det.factura)
          m.cadena.set(det.factura.numero, { numero: det.factura.numero, huella: det.registro.huella, total: det.factura.total, envio: "pendiente", tipo: "alta" });
        break;
      case "aeat.envio":
        ((det.aeat && det.aeat.registros) || []).forEach((n) => { const r = m.cadena.get(n); if (r) r.envio = "aceptado"; });
        break;
      case "fiscal.informe":
        if (det.informe) m.informe = Object.assign({}, det.informe, { a_pagar: !String(det.informe.resultado).startsWith("-") });
        break;
    }
    if (ev.tipo === "email") m.emails++;
  }

  // ------------------------------------------------ pintar estado estático
  function pintarEscena() {
    const d = E.d;
    // trabajando / noche
    for (const id in S.p) S.p[id].classList.toggle("trabajando", d.trabajando.has(id) || (id === "orquestador" && !!d.fase));
    S.svg.classList.toggle("noche", d.noche);
    // pizarra
    S.pizarra.textContent = d.fase ? nombreFase(d.fase) : d.noche ? "Hasta mañana" : d.enJornada ? "¡Buenos días!" : "Antes de empezar";
    // reloj y cielo
    const clave = d.fase || (d.noche ? "fin" : d.enJornada ? "inicio" : "antes");
    const [h, mi] = RELOJ[clave] || [7, 45];
    S.agujaH.style.transform = `rotate(${(h % 12) * 30 + mi * 0.5}deg)`;
    S.agujaM.style.transform = `rotate(${mi * 6}deg)`;
    S.cielos.forEach((c) => c.setAttribute("fill", CIELO[clave] || CIELO.antes));
    S.soles.forEach((s) => s.setAttribute("opacity", d.noche ? "0" : clave === "informe" || clave === "inicio" ? ".55" : ".9"));
    // contadores en las insignias
    for (const id in S.p) {
      const c = d.cuenta[id];
      const ins = S.p[id].querySelector(".insignia");
      if (!ins) continue;
      if (id === "tu") continue;
      const n = c ? c.env + c.rec : 0;
      ins.classList.toggle("visible", n > 0);
      ins.querySelector(".insignia-num").textContent = n > 99 ? "99+" : n;
    }
    // tu mesa: pila de notas
    const pend = d.mesa.incidencias.size;
    const insTu = S.p.tu.querySelector(".insignia");
    insTu.classList.toggle("visible", pend > 0);
    insTu.querySelector(".insignia-num").textContent = pend;
    S.pendientesTxt.textContent = pend ? `${pend} cosa${pend > 1 ? "s" : ""} por revisar` : "Nada pendiente";
    pintarPila(false);
    dibujarRutas();
    pintarFases();
    pintarDia();
  }

  function pintarPila(animarUltima) {
    const notas = Array.from(E.d.mesa.incidencias.values()).slice(-9);
    S.pila.innerHTML = "";
    notas.forEach((n, i) => {
      const c = n.severidad === "error" ? "var(--c-alerta)" : n.severidad === "aviso" ? "var(--c-aviso)" : "var(--c-documento)";
      const pos = el("g", { transform: `translate(${(i % 3) * 2 - 2},${-i * 3.2}) rotate(${((i * 37) % 9) - 4})` }, S.pila);
      const g = el("g", { class: animarUltima && i === notas.length - 1 ? "pila-nota" : "" }, pos);
      el("rect", { x: -11, y: -7, width: 22, height: 14, rx: 1.5, style: `fill:${c}`, opacity: 0.9 }, g);
      el("path", { d: "M-7,-2 h12 M-7,2 h8", stroke: "#fff", "stroke-width": 1.4 }, g);
    });
  }

  function pintarFases() {
    const cont = $("#fases");
    if (!cont.childElementCount && E.info) {
      cont.innerHTML = E.info.fases.map((f, i) => `<div class="fase" data-f="${f.id}" title="${esc(f.nombre)}"><span class="n">${i + 1}</span><span class="t">${esc(f.nombre)}</span></div>`).join("");
    }
    cont.querySelectorAll(".fase").forEach((n) => {
      const id = n.dataset.f;
      n.classList.toggle("actual", E.d.fase === id);
      n.classList.toggle("hecha", E.d.hechas.has(id) && E.d.fase !== id);
    });
  }

  function pintarDia() {
    const d = E.d;
    const b = $("#dia b"), s = $("#dia span");
    if (d.dia) b.textContent = fechaLarga(d.dia);
    s.textContent = d.fase ? `Ahora: ${nombreFase(d.fase)}` : d.noche ? "Jornada terminada" : d.enJornada ? "Empieza la jornada" : "Esperando la jornada";
  }

  // ------------------------------------------------------- feed (conversación)
  let ultimoDiaFeed = null, ultimaFaseFeed = null;
  function itemFeed(ev, nuevo) {
    const feed = $("#feed");
    const frag = document.createDocumentFragment();
    if (ev.dia && ev.dia !== ultimoDiaFeed) {
      ultimoDiaFeed = ev.dia; ultimaFaseFeed = null;
      const li = document.createElement("li");
      li.className = "sep-dia";
      li.textContent = fechaLarga(ev.dia);
      frag.appendChild(li);
    }
    if (ev.tipo === "fase") {
      ultimaFaseFeed = ev.detalle.fase;
    }
    const li = document.createElement("li");
    li.className = "msg" + (ev.tipo === "fase" || ev.tipo === "jornada" ? " sistema" : "") + (nuevo ? " nuevo" : "");
    li.dataset.id = ev.id;
    li.tabIndex = 0;
    const t = TIPOS[ev.tipo] || TIPOS.sistema;
    const para = (ev.a || []).map((a) => `<span class="chip" style="--c:${colorDe(a)}"><i></i>${esc(quien(a).nombre)}</span>`).join(" ");
    li.innerHTML = `<span class="avatar">${avatar(ev.de, 30)}</span>
      <div style="min-width:0"><div class="cab"><b>${esc(quien(ev.de).nombre)}</b>${para ? `<span class="flecha">→</span>${para}` : ""}
      ${ev.tipo !== "fase" && ev.tipo !== "jornada" ? `<span class="tipo" style="--c:${colorTipo(ev.tipo)}">${esc(t.nombre)}</span>` : ""}</div>
      <div class="texto">${texto(ev)}</div></div>`;
    li.addEventListener("click", () => abrirEvento(ev));
    li.addEventListener("keydown", (e) => { if (e.key === "Enter") abrirEvento(ev); });
    frag.appendChild(li);
    feed.appendChild(frag);
    aplicarFiltroA(li, ev);
    $("#feed-vacio").hidden = true;
    return li;
  }
  function reiniciarFeed() {
    $("#feed").innerHTML = "";
    ultimoDiaFeed = null; ultimaFaseFeed = null;
    $("#feed-vacio").hidden = false;
  }
  function bajarFeed() {
    const v = $("#vista-feed");
    v.scrollTop = v.scrollHeight;
  }
  function marcarActivo(id) {
    $("#feed").querySelectorAll(".msg.activo").forEach((n) => n.classList.remove("activo"));
    const n = $(`#feed .msg[data-id="${id}"]`);
    if (n) n.classList.add("activo");
  }

  // filtros por participante
  function filtrarPor(id) {
    E.filtro = id;
    const q = quien(id);
    $("#filtro").hidden = false;
    $("#filtro-texto").innerHTML = `Mensajes de <span class="chip" style="--c:${colorDe(id)}"><i></i>${esc(q.nombre)}</span>`;
    $("#feed").querySelectorAll(".msg").forEach((li) => aplicarFiltroA(li, E.eventos[+li.dataset.id] || null));
    $("#feed").querySelectorAll(".sep-dia").forEach((s) => (s.hidden = false));
    mostrarPestana("feed");
    for (const k in S.p) S.p[k].classList.toggle("seleccionada", k === id);
  }
  function aplicarFiltroA(li, ev) {
    if (!ev) return;
    li.hidden = !!E.filtro && !(ev.de === E.filtro || (ev.a || []).includes(E.filtro));
  }
  function quitarFiltro() {
    E.filtro = null;
    $("#filtro").hidden = true;
    $("#feed").querySelectorAll(".msg").forEach((li) => (li.hidden = false));
    for (const k in S.p) S.p[k].classList.remove("seleccionada");
  }

  // ------------------------------------------------------------- tu mesa
  function pintarMesa() {
    const m = E.d.mesa;
    const incs = Array.from(m.incidencias.values());
    const orden = { error: 0, aviso: 1, info: 2 };
    incs.sort((a, b) => orden[a.severidad] - orden[b.severidad]);
    const falt = Array.from(m.faltantes.values());
    const cadena = Array.from(m.cadena.values()).slice(-6);
    const b = $("#burbuja-mesa");
    b.textContent = incs.length;
    b.hidden = !incs.length;

    const colorSev = (s) => (s === "error" ? "var(--c-alerta)" : s === "aviso" ? "var(--c-aviso)" : "var(--c-documento)");
    const etiquetaSev = { error: "Error", aviso: "Aviso", info: "Nota" };
    const estadoFalta = { detectada: ["Detectada", "var(--c-falta)"], reclamada: ["Reclamada", "var(--c-email)"], escalada: ["Te necesita", "var(--c-alerta)"] };
    const directo = E.modo === "directo";

    let html = `<section><h3>Necesita tu atención <span class="cuenta">${incs.length}</span></h3>`;
    html += incs.length ? `<div class="notas">${incs.map((i) => `
        <div class="nota" style="--c:${colorSev(i.severidad)}">
          <div><div class="quien"><span class="sev">${etiquetaSev[i.severidad] || "Nota"}</span>de ${esc(quien(i.agente).nombre)}</div>${esc(i.mensaje)}</div>
          ${directo ? `<button type="button" data-resolver="${esc(i.id)}">Hecho</button>` : ""}
        </div>`).join("")}</div>` : `<div class="vacio" style="padding:10px 0;text-align:left">Nada por ahora. Cuando un agente no pueda resolver algo, te dejará una nota aquí.</div>`;
    html += `</section>`;

    html += `<section><h3>Facturas que faltan <span class="cuenta">${falt.length}</span></h3>`;
    html += falt.length ? `<div class="notas">${falt.map((f) => {
      const [et, c] = estadoFalta[f.estado] || [f.estado, "var(--muted)"];
      return `<div class="falta"><span class="prov">${esc(f.proveedor)}</span><span class="estado" style="--c:${c}">${et}${f.intentos ? ` · ${f.intentos}✉` : ""}</span>
        <span class="motivo">${esc(f.importe || "")}${f.importe ? " · " : ""}${esc(f.periodo || "")}</span></div>`;
    }).join("")}</div>` : `<div class="vacio" style="padding:10px 0;text-align:left">No falta ninguna. Dani lo comprueba cada jornada.</div>`;
    html += `</section>`;

    const inf = m.informe;
    html += `<section><h3>Impuestos</h3>`;
    html += inf ? `<div class="impuesto">
        <div class="fila"><span>Modelo 303 · ${inf.trimestre}T ${inf.anio}</span><span>Plazo ${esc(inf.plazo)}</span></div>
        <div class="fila"><span>IVA que cobras</span><span>${esc(inf.repercutido)}</span></div>
        <div class="fila"><span>IVA que pagas</span><span>${esc(inf.soportado)}</span></div>
        <div class="fila total"><span>${inf.a_pagar ? "A pagar" : "A compensar"}</span><span>${esc(String(inf.resultado).replace("-", ""))}</span></div>
        ${(inf.avisos || []).map((a) => `<div class="aviso">⚠ ${esc(a)}</div>`).join("")}
      </div>` : `<div class="vacio" style="padding:10px 0;text-align:left">Fátima prepara el borrador al final de cada jornada.</div>`;
    html += `</section>`;

    html += `<section><h3>Cadena VeriFactu <span class="cuenta">${m.cadena.size}</span></h3>`;
    html += cadena.length ? `<div class="cadena">${cadena.map((r, i) => `${i ? '<span class="enlace-cadena"></span>' : ""}
        <span class="eslabon" title="Huella ${esc(r.huella)}"><b>${esc(r.numero)}</b><code>${esc(r.huella.slice(0, 8))}…</code><span style="color:var(--muted)">${r.envio === "aceptado" ? "En Hacienda ✓" : "Pendiente"}</span></span>`).join("")}</div>
        <div class="integridad${m.integra ? "" : " rota"}">${m.integra ? "✓ Cadena íntegra: ninguna factura se ha tocado" : "✗ La cadena está rota"}</div>`
      : `<div class="vacio" style="padding:10px 0;text-align:left">Cuando Vera emita una factura, verás aquí sus eslabones.</div>`;
    html += `</section>`;
    $("#mesa").innerHTML = html;
    $("#mesa").querySelectorAll("[data-resolver]").forEach((bt) => bt.addEventListener("click", () => resolver(bt.dataset.resolver, bt)));
  }

  // --------------------------------------------------- reproducción animada
  async function reproducir(ev, gen) {
    const v = E.velocidad;
    const dur = (ms) => (reducido ? 60 : ms / v);
    aplicar(ev);
    itemFeed(ev, true);
    marcarActivo(ev.id);
    if (!E.filtro || ev.de === E.filtro || (ev.a || []).includes(E.filtro)) bajarFeed();
    pintarFases(); pintarDia();

    if (ev.tipo === "jornada") {
      limpiarBocadillos();
      pintarEscena();
      bocadillo("orquestador", ev.tema === "ciclo.iniciado" ? "¡Buenos días, equipo!" : "¡Buen trabajo, a casa!", "jornada", dur(2200));
      await esperar(dur(1300));
      return;
    }
    if (ev.tipo === "fase") {
      pintarEscena();
      S.pizarra.style.opacity = 0;
      setTimeout(() => (S.pizarra.style.opacity = 1), 120);
      bocadillo(E.d.enJornada ? "orquestador" : ev.a[0], E.d.enJornada ? "¡Toca " + nombreFase(ev.detalle.fase).toLowerCase() + "!" : "¡Voy!", "fase", dur(1800));
      ev.a.forEach((a) => saltar(a));
      await esperar(dur(950));
      return;
    }

    // Mensaje normal: bocadillo del emisor, puertas, vuelo y llegada
    const exteriorSale = S.ext[ev.de];
    if (exteriorSale) abrirPuerta(ev.de, dur(1400));
    else bocadillo(ev.de, ev.titulo, ev.tipo, dur(2300));
    if (S.p[ev.de]) S.p[ev.de].classList.add("trabajando");
    if (ev.tipo === "alerta" && S.p[ev.de]) alarma(ev.de, dur(1600));
    const recientes = new Set((ev.a || []).map((a) => claveRuta(ev.de, a)));
    dibujarRutas(recientes);
    await esperar(dur(160));
    await Promise.all((ev.a || []).map((a, i) => esperar(i * dur(90)).then(() => {
      if (S.ext[a]) abrirPuerta(a, dur(1400));
      return volar(ev.de, a, ev.tipo, dur(980), gen).then(() => {
        if (gen !== E.generacion) return;
        saltar(a);
        if (a === "tu") { pintarPila(true); pintarEscena(); pintarMesa(); }
        if (ev.tema === "factura.faltante_resuelta") bocadillo("tu", "¡Una menos!", "exito", dur(1800));
      });
    })));
    if (gen !== E.generacion) return;
    pintarEscena();
    if (ev.a && ev.a.includes("tu")) pintarMesa();
    else if (["factura.faltante", "reclamacion.enviada", "factura.emitida", "aeat.envio"].includes(ev.tema)) pintarMesa();
    await esperar(dur(260));
  }

  function saltar(id) {
    const n = S.p[id];
    if (!n || reducido) return;
    n.classList.remove("salto");
    void n.getBBox();
    n.classList.add("salto");
    setTimeout(() => n.classList.remove("salto"), 520);
  }
  function alarma(id, ms) {
    const n = S.p[id];
    if (!n) return;
    n.classList.add("alarma");
    setTimeout(() => n.classList.remove("alarma"), ms);
  }
  function abrirPuerta(id, ms) {
    const n = S.ext[id];
    if (!n) return;
    n.classList.add("abierta");
    clearTimeout(n._t);
    n._t = setTimeout(() => n.classList.remove("abierta"), ms);
  }

  async function bucle() {
    for (;;) {
      if (!E.reproduciendo || E.cursor >= E.eventos.length) {
        if (E.reproduciendo && E.cursor >= E.eventos.length && E.modo === "grabacion") pausar();
        if (E.cursor >= E.eventos.length && !E.d.enJornada && E.d.trabajando.size) {
          await esperar(900);
          if (E.cursor >= E.eventos.length && !E.d.enJornada) { E.d.trabajando = new Set(); pintarEscena(); }
        }
        await esperar(150);
        continue;
      }
      const gen = E.generacion;
      const ev = E.eventos[E.cursor];
      E.cursor++;
      actualizarTiempo();
      await reproducir(ev, gen);
      if (gen !== E.generacion) continue;
      actualizarTiempo();
    }
  }

  // Rebobinar o saltar: reconstruye todo hasta n sin animar
  function irA(n) {
    E.generacion++;
    S.vuelos.innerHTML = "";
    limpiarBocadillos();
    E.d = estadoVacio(E.base);
    reiniciarFeed();
    E.cursor = Math.max(0, Math.min(n, E.eventos.length));
    const frag = [];
    for (let i = 0; i < E.cursor; i++) { aplicar(E.eventos[i]); frag.push(E.eventos[i]); }
    frag.forEach((ev) => itemFeed(ev, false));
    if (E.cursor) marcarActivo(E.eventos[E.cursor - 1].id);
    pintarEscena();
    pintarMesa();
    bajarFeed();
    actualizarTiempo();
  }

  function reproducirPausar() {
    if (E.reproduciendo) return pausar();
    if (E.cursor >= E.eventos.length && E.modo === "grabacion") irA(0);
    E.reproduciendo = true;
    pintarBotonPlay();
  }
  function pausar() { E.reproduciendo = false; pintarBotonPlay(); }
  function pintarBotonPlay() {
    const b = $("#btn-play");
    b.setAttribute("aria-label", E.reproduciendo ? "Pausar" : "Reproducir");
    b.innerHTML = E.reproduciendo
      ? `<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="3.5" y="3" width="3.2" height="10" rx="1" fill="currentColor"/><rect x="9.3" y="3" width="3.2" height="10" rx="1" fill="currentColor"/></svg>`
      : `<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4.5 2.8v10.4L13 8z" fill="currentColor"/></svg>`;
  }

  // ------------------------------------------------------- línea de tiempo
  function actualizarTiempo() {
    const r = $("#deslizador");
    r.max = E.eventos.length;
    r.value = E.cursor;
    $("#contador").textContent = `${E.cursor} / ${E.eventos.length}`;
    pintarLienzo();
  }
  function pintarLienzo() {
    const c = $("#lienzo-tiempo");
    const dpr = window.devicePixelRatio || 1;
    const w = c.clientWidth, h = c.clientHeight;
    if (!w) return;
    if (c.width !== Math.round(w * dpr)) { c.width = Math.round(w * dpr); c.height = Math.round(h * dpr); }
    const x = c.getContext("2d");
    x.setTransform(dpr, 0, 0, dpr, 0, 0);
    x.clearRect(0, 0, w, h);
    const cs = getComputedStyle(document.documentElement);
    const n = E.eventos.length;
    x.fillStyle = cs.getPropertyValue("--panel-2");
    x.beginPath(); x.roundRect ? x.roundRect(0, 4, w, h - 8, 6) : x.rect(0, 4, w, h - 8); x.fill();
    if (!n) return;
    const paso = w / n;
    let diaPrevio = null;
    E.eventos.forEach((ev, i) => {
      const color = cs.getPropertyValue((TIPOS[ev.tipo] || TIPOS.sistema).var).trim();
      x.globalAlpha = i < E.cursor ? 1 : 0.35;
      x.fillStyle = color;
      const alto = ev.tipo === "fase" || ev.tipo === "jornada" ? 5 : 12;
      x.fillRect(i * paso + paso * 0.15, h / 2 - alto / 2, Math.max(1.5, paso * 0.7), alto);
      if (ev.dia !== diaPrevio && i > 0) {
        x.globalAlpha = 0.6; x.fillStyle = cs.getPropertyValue("--muted");
        x.fillRect(i * paso - 0.5, 2, 1, h - 4);
      }
      diaPrevio = ev.dia;
    });
    x.globalAlpha = 1;
    const cx = E.cursor * paso;
    x.fillStyle = cs.getPropertyValue("--ink");
    x.fillRect(cx - 1, 1, 2, h - 2);
  }

  // ----------------------------------------------------------- modales
  let focoPrevio = null;
  function abrirModal(titulo, iconoHtml, html) {
    focoPrevio = document.activeElement;
    $("#modal-titulo").textContent = titulo;
    $("#modal-icono").innerHTML = iconoHtml || "";
    $("#modal-contenido").innerHTML = html;
    $("#capa").hidden = false;
    $("#modal-cerrar").focus();
  }
  function cerrarModal() {
    $("#capa").hidden = true;
    if (focoPrevio && focoPrevio.focus) focoPrevio.focus();
  }

  const kv = (pares) => `<dl class="kv">${pares.filter((p) => p[1] != null && p[1] !== "").map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v}</dd>`).join("")}</dl>`;
  const ficha = (titulo, cuerpo, extra) => `<div class="ficha"><div class="ficha-cab"><span>${esc(titulo)}</span>${extra ? `<span>${extra}</span>` : ""}</div><div class="ficha-cuerpo">${cuerpo}</div></div>`;

  function abrirEvento(ev) {
    const d = ev.detalle || {};
    const partes = [`<div class="frase">${texto(ev)}</div>`];
    if (d.email) partes.push(ficha("Correo", kv([["Para", esc(d.email.para)], ["Asunto", esc(d.email.asunto)]]) + `<div class="carta">${esc(d.email.cuerpo)}</div>`,
      E.modo === "directo" && !E.ia ? "Redactado con plantilla" : ""));
    if (d.factura) {
      const f = d.factura;
      const lineas = f.lineas && f.lineas.length ? `<table class="lineas"><thead><tr><th>Concepto</th><th>Cant.</th><th>IVA</th><th>Precio</th></tr></thead><tbody>
        ${f.lineas.map((l) => `<tr><td>${esc(l.descripcion)}</td><td>${esc(l.cantidad)}</td><td>${esc(l.iva)}</td><td>${esc(l.precio)}</td></tr>`).join("")}</tbody></table>` : "";
      partes.push(ficha(`Factura ${f.numero}`, kv([["Emite", esc(f.emisor)], ["Para", esc(f.receptor)], ["Fecha", esc(f.fecha)], ["Vence", esc(f.vencimiento)],
        ["Base", esc(f.base)], ["IVA", esc(f.iva)], ["Total", `<b>${esc(f.total)}</b>`]]) + lineas, esc(f.estado)));
    }
    if (d.registro) {
      const r = d.registro;
      partes.push(ficha("Sello VeriFactu", `
        ${kv([["Eslabón nº", esc(r.secuencia)], ["Registrado", esc(new Date(r.fecha_hora).toLocaleString("es-ES"))]])}
        <div><div class="txt-mini" style="font-size:12px;color:var(--muted);margin-bottom:4px">Huella de esta factura</div><div class="huella">${esc(r.huella)}</div></div>
        <div><div style="font-size:12px;color:var(--muted);margin-bottom:4px">Se encadena con la huella anterior</div><div class="huella">${r.huella_anterior ? esc(r.huella_anterior) : "Es el primer eslabón de la cadena"}</div></div>
        <div style="font-size:13px;color:var(--muted)">La huella se calcula con los datos de esta factura y la de la anterior. Si alguien cambia una factura pasada, la cadena deja de encajar.</div>
        ${r.qr ? `<div style="font-size:13px">Código QR de la factura: <a href="${esc(r.qr)}" target="_blank" rel="noopener">comprobar en Hacienda</a></div>` : ""}`));
    }
    if (d.movimiento) partes.push(ficha("Movimiento del banco", kv([["Fecha", esc(d.movimiento.fecha)], ["Concepto", esc(d.movimiento.concepto)], ["Importe", `<b>${esc(d.movimiento.importe)}</b>`]])));
    if (d.faltante) partes.push(ficha("Factura que falta", kv([["Proveedor", esc(d.faltante.proveedor)], ["Por qué", esc(d.faltante.motivo)], ["Importe", esc(d.faltante.importe)],
      ["Periodo", esc(d.faltante.periodo)], ["Reclamaciones", esc(d.faltante.intentos)], ["Estado", esc(d.faltante.estado)]])));
    if (d.incidencia) partes.push(ficha("Nota para ti", kv([["De", esc(quien(d.incidencia.agente).nombre)], ["Gravedad", esc(d.incidencia.severidad)], ["Qué pasa", esc(d.incidencia.mensaje)], ["Código", `<code>${esc(d.incidencia.codigo)}</code>`]])));
    if (d.informe) {
      const i = d.informe;
      partes.push(ficha(`Modelo 303 · ${i.trimestre}T ${i.anio} (borrador)`, kv([["IVA que cobras", esc(i.repercutido)], ["IVA que pagas", esc(i.soportado)], ["Resultado", `<b>${esc(i.resultado)}</b>`], ["Plazo", esc(i.plazo)]]) +
        (i.avisos || []).map((a) => `<div style="color:var(--c-aviso);font-size:13px">⚠ ${esc(a)}</div>`).join("")));
    }
    if (d.documento) partes.push(ficha("Documento recibido", kv([["Nombre", esc(d.documento.nombre)], ["Llega por", esc(d.documento.origen)]]) + `<div class="extracto">${esc(d.documento.extracto)}</div>`));
    if (d.aeat) partes.push(ficha("Envío a Hacienda", kv([["Aceptados", esc(d.aeat.aceptados)], ["Rechazados", esc(d.aeat.rechazados)], ["Facturas", esc((d.aeat.registros || []).join(", "))], ["Justificante", `<code>${esc(d.aeat.csv)}</code>`]])));
    if (d.resumen) partes.push(ficha("Cómo queda el día", kv(Object.entries(d.resumen).map(([k, v]) => [k.replace(/_/g, " "), esc(v)]))));
    if (d.fase) partes.push(`<div style="color:var(--muted);font-size:13px">En esta fase trabajan: ${(ev.a || []).map((a) => `<span class="chip" style="--c:${colorDe(a)}"><i></i>${esc(quien(a).nombre)}</span>`).join(", ") || "nadie"}.</div>`);
    const t = TIPOS[ev.tipo] || TIPOS.sistema;
    abrirModal(ev.titulo || t.nombre, `<span class="avatar">${avatar(ev.de, 34)}</span>`, partes.join(""));
  }

  function abrirPersona(id) {
    const p = quien(id);
    const part = E.info && E.info.participantes ? E.info.participantes.find((x) => x.id === id) : null;
    const c = E.d.cuenta[id] || { env: 0, rec: 0 };
    const ahora = E.d.trabajando.has(id) || (id === "orquestador" && E.d.fase) ? "Trabajando" : E.d.noche ? "Descansando" : "Esperando";
    const dibujo = id === "tu"
      ? avatar("tu", 84)
      : `<svg viewBox="-40 -100 80 80" aria-hidden="true"><circle cx="0" cy="-60" r="40" style="fill:${p.color}" opacity=".16"/>
          ${pelo(p, "detras")}<path style="fill:${p.color}" d="M-26,4 L-26,-26 Q-26,-47 -9,-48 L9,-48 Q26,-47 26,-26 L26,4Z"/>
          <circle cx="0" cy="-65" r="17.5" style="fill:${p.piel}"/>${pelo(p, "delante")}
          <circle cx="-6.5" cy="-64" r="2.1" fill="#1d2326"/><circle cx="6.5" cy="-64" r="2.1" fill="#1d2326"/>
          <path d="M-4.5,-56.5 Q0,-52.5 4.5,-56.5" fill="none" stroke="#7a3b2e" stroke-width="1.8" stroke-linecap="round"/></svg>`;
    const rol = id === "tu" ? "Aquí llegan las notas que el equipo no puede resolver solo, el borrador de impuestos y las buenas noticias."
      : part && part.rol ? part.rol : "";
    const html = `<div class="ficha-persona">${dibujo}<div><div style="font:600 13px var(--f-body);color:var(--muted);text-transform:uppercase;letter-spacing:.05em">${esc(p.puesto)}</div>
      <div style="font-size:15px;margin-top:4px">${esc(rol)}</div></div></div>
      <div class="cifras"><div class="cifra"><b>${c.env}</b><span>mensajes enviados</span></div><div class="cifra"><b>${c.rec}</b><span>recibidos</span></div><div class="cifra"><b style="font-size:16px">${ahora}</b><span>ahora mismo</span></div></div>
      <button class="btn primario" type="button" id="ver-mensajes">Ver sus mensajes</button>`;
    abrirModal(p.nombre, "", html);
    $("#ver-mensajes").addEventListener("click", () => { cerrarModal(); filtrarPor(id); });
  }

  function abrirAyuda() {
    const muestra = (f, t) => { const g = document.createElementNS(NS, "g"); dibujarForma(g, f, t); return `<svg viewBox="-17 -17 34 34">${g.innerHTML}</svg>`; };
    abrirModal("Cómo se lee la oficina", "", `
      <ul class="ayuda-lista">
        <li>${avatar("detective", 34)}<div><b>Cada persona es un agente</b> con un único trabajo. Pulsa en una para ver qué hace y qué mensajes ha enviado.</div></li>
        <li>${muestra("avion", "falta")}<div><b>Los aviones de papel</b> son avisos entre compañeros: «ha llegado una factura», «falta esta otra»…</div></li>
        <li>${muestra("sobre", "email")}<div><b>Los sobres</b> son emails que salen por la puerta: a proveedores (reclamar facturas) o a clientes (enviar facturas y recordar pagos).</div></li>
        <li>${muestra("doc", "documento")}<div><b>Los documentos y monedas</b> entran por el buzón y el banco: facturas que recibes y movimientos de la cuenta.</div></li>
        <li>${muestra("sello", "verifactu")}<div><b>Los sellos verdes</b> son facturas registradas con VeriFactu que viajan a Hacienda.</div></li>
        <li>${muestra("nota", "alerta")}<div><b>Las notas de colores</b> caen en <b>tu mesa</b>: lo que el equipo no puede resolver sin ti. Rojo es un error, ámbar un aviso.</div></li>
        <li>${avatar("orquestador", 34)}<div><b>Olga</b> dirige la jornada. La pizarra, el reloj y la barra de fases te dicen en qué momento del día está el equipo.</div></li>
      </ul>
      <div style="font-size:13px;color:var(--muted)">Pulsa cualquier mensaje de «Lo que pasa» para abrir el email, la factura o la huella. El botón de las rutas, junto a la línea de tiempo, enseña por dónde circula más tráfico.</div>`);
  }

  // ------------------------------------------------------- formulario venta
  function abrirVenta() {
    const clientes = (E.info && E.info.clientes) || [];
    abrirModal("Nueva venta", "", `
      <form class="formulario" id="form-venta" novalidate>
        <label for="v-cliente">Cliente
          <select id="v-cliente">${clientes.map((c) => `<option value="${esc(c.nif)}">${esc(c.nombre)} · ${esc(c.nif)}</option>`).join("")}<option value="">Otro cliente…</option></select></label>
        <div id="v-otro" hidden style="display:grid;gap:10px;grid-template-columns:minmax(0,1fr) 140px">
          <label for="v-nombre">Nombre<input id="v-nombre" autocomplete="off"></label>
          <label for="v-nif">NIF<input id="v-nif" autocomplete="off" placeholder="B12345674"></label>
        </div>
        <div id="v-lineas" style="display:grid;gap:8px"></div>
        <button class="btn" type="button" id="v-mas" style="justify-self:start">Añadir línea</button>
        <div class="total-venta"><span>Total con IVA</span><span id="v-total">0,00 €</span></div>
        <div class="error-form" id="v-error" hidden></div>
        <button class="btn primario" type="submit" id="v-enviar">Pedir a Vera que la emita</button>
      </form>`);
    const lineas = $("#v-lineas");
    let n = 0;
    const nuevaLinea = (desc, cant, precio, iva) => {
      n++;
      const div = document.createElement("div");
      div.className = "linea-venta";
      div.innerHTML = `<label for="v-d${n}">Concepto<input id="v-d${n}" class="d" value="${esc(desc || "")}" placeholder="Desayunos de empresa"></label>
        <label for="v-c${n}">Cant.<input id="v-c${n}" class="c" inputmode="decimal" value="${cant || 1}"></label>
        <label for="v-p${n}">Precio<input id="v-p${n}" class="p" inputmode="decimal" value="${precio || ""}" placeholder="0,00"></label>
        <label for="v-i${n}" class="iva-sel">IVA<select id="v-i${n}" class="i">${[21, 10, 4, 0].map((t) => `<option value="${t}" ${t === (iva || 10) ? "selected" : ""}>${t}%</option>`).join("")}</select></label>
        <button type="button" class="quitar" aria-label="Quitar línea">✕</button>`;
      div.querySelector(".quitar").addEventListener("click", () => { div.remove(); total(); });
      div.querySelectorAll("input,select").forEach((i) => i.addEventListener("input", total));
      lineas.appendChild(div);
    };
    const num = (s) => parseFloat(String(s || "0").replace(/\./g, "").replace(",", ".")) || 0;
    const total = () => {
      let t = 0;
      lineas.querySelectorAll(".linea-venta").forEach((l) => {
        t += num(l.querySelector(".c").value) * num(l.querySelector(".p").value) * (1 + num(l.querySelector(".i").value) / 100);
      });
      $("#v-total").textContent = t.toLocaleString("es-ES", { style: "currency", currency: "EUR" });
    };
    nuevaLinea("Desayunos de empresa", 1, "250,00", 10);
    total();
    $("#v-mas").addEventListener("click", () => nuevaLinea());
    $("#v-cliente").addEventListener("change", (e) => { $("#v-otro").hidden = !!e.target.value; });
    $("#form-venta").addEventListener("submit", async (e) => {
      e.preventDefault();
      const sel = $("#v-cliente").value;
      const cliente = clientes.find((c) => c.nif === sel);
      const datos = {
        cliente_nif: sel || $("#v-nif").value.trim(),
        cliente_nombre: cliente ? cliente.nombre : $("#v-nombre").value.trim(),
        lineas: Array.from(lineas.querySelectorAll(".linea-venta")).map((l) => ({
          descripcion: l.querySelector(".d").value, cantidad: num(l.querySelector(".c").value),
          precio_unitario: String(num(l.querySelector(".p").value)), tipo_iva: +l.querySelector(".i").value,
        })),
      };
      $("#v-enviar").disabled = true;
      const r = await api("/api/venta", datos);
      $("#v-enviar").disabled = false;
      if (r && r.ok) { cerrarModal(); tostada(`Factura ${r.numero} emitida por ${r.total}`); seguirEnDirecto(); }
      else { const er = $("#v-error"); er.hidden = false; er.textContent = (r && r.error) || "No se ha podido emitir."; }
    });
  }

  // ------------------------------------------------------------ pestañas
  function mostrarPestana(cual) {
    const feed = cual === "feed";
    $("#tab-feed").setAttribute("aria-selected", feed);
    $("#tab-mesa").setAttribute("aria-selected", !feed);
    $("#vista-feed").hidden = !feed;
    $("#vista-mesa").hidden = feed;
    if (!feed) pintarMesa();
  }

  // ---------------------------------------------------------- modo directo
  async function api(ruta, cuerpo) {
    try {
      const r = await fetch(ruta, cuerpo === undefined ? { cache: "no-store" } : {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cuerpo),
      });
      if (!r.ok && r.status !== 500) throw new Error(r.status);
      return await r.json();
    } catch (e) {
      return null;
    }
  }

  function seguirEnDirecto() {
    // Al lanzar una acción, nos colocamos al final y reproducimos lo nuevo
    if (E.cursor < E.eventos.length) irA(E.eventos.length);
    E.reproduciendo = true;
    pintarBotonPlay();
    sondear();
  }

  let sondeando = false;
  async function sondear() {
    if (sondeando) return;
    sondeando = true;
    const r = await api("/api/eventos?desde=" + E.eventos.length);
    sondeando = false;
    const pill = $("#modo");
    if (!r) {
      pill.className = "pill error";
      pill.lastElementChild.textContent = "Sin conexión";
      return;
    }
    pill.className = "pill directo";
    pill.lastElementChild.textContent = "En directo";
    if (r.eventos.length) {
      r.eventos.forEach((ev) => { if (ev.id === E.eventos.length) E.eventos.push(ev); });
      actualizarTiempo();
    }
  }

  async function refrescarEstado() {
    const st = await api("/api/estado");
    if (!st) return;
    E.porLlegar = st.por_llegar || 0;
    $("#num-llega").textContent = E.porLlegar;
    $("#btn-llega").disabled = !E.porLlegar || E.ocupado;
    if (st.hoy && !$("#fecha-jornada").dataset.tocada) $("#fecha-jornada").value = st.hoy;
    if (!E.d.dia && st.hoy) { E.d.dia = st.hoy; pintarDia(); }
  }

  async function accion(boton, ruta, cuerpo, ok) {
    if (E.ocupado) return;
    E.ocupado = true;
    boton.disabled = true;
    const r = await api(ruta, cuerpo);
    E.ocupado = false;
    boton.disabled = false;
    if (r && r.ok) { if (ok) ok(r); seguirEnDirecto(); }
    else tostada((r && r.error) || "No se ha podido conectar con la oficina. ¿Sigue abierto agentes-conta web?", true);
    refrescarEstado();
  }

  async function resolver(id, boton) {
    boton.disabled = true;
    const r = await api("/api/resolver", { id });
    if (r && r.ok) { tostada("Nota marcada como revisada"); seguirEnDirecto(); }
    else { boton.disabled = false; tostada((r && r.error) || "No se ha podido marcar.", true); }
  }

  function prepararDirecto() {
    $("#acciones").hidden = false;
    $("#btn-llega").hidden = E.info.modo !== "demo";
    const inp = $("#fecha-jornada");
    inp.value = E.info.hoy;
    inp.addEventListener("input", () => (inp.dataset.tocada = "1"));
    $("#btn-jornada").addEventListener("click", (e) => {
      const fecha = inp.value || E.info.hoy;
      accion(e.currentTarget, "/api/jornada", { fecha }, (r) => {
        inp.value = r.siguiente; delete inp.dataset.tocada;
        tostada(`Empieza la jornada del ${fechaCorta(r.jornada)}`);
      });
    });
    $("#btn-venta").addEventListener("click", abrirVenta);
    $("#btn-llega").addEventListener("click", (e) => accion(e.currentTarget, "/api/llega-factura", {}, (r) => tostada(`Ha llegado «${r.documento}» al buzón`)));
    setInterval(sondear, 900);
    setInterval(refrescarEstado, 5000);
  }

  // --------------------------------------------------------------- inicio
  function enlazarControles() {
    $("#btn-play").addEventListener("click", reproducirPausar);
    $("#btn-reiniciar").addEventListener("click", () => { irA(0); E.reproduciendo = true; pintarBotonPlay(); });
    document.querySelectorAll(".segmentado button").forEach((b) => b.addEventListener("click", () => {
      E.velocidad = parseFloat(b.dataset.vel);
      document.querySelectorAll(".segmentado button").forEach((x) => x.setAttribute("aria-pressed", x === b));
    }));
    const r = $("#deslizador");
    r.addEventListener("input", () => { pausar(); irA(+r.value); });
    $("#btn-rutas").addEventListener("click", (e) => {
      E.rutasVisibles = !E.rutasVisibles;
      e.currentTarget.setAttribute("aria-pressed", E.rutasVisibles);
      S.svg.classList.toggle("rutas-calor", E.rutasVisibles);
    });
    $("#tab-feed").addEventListener("click", () => mostrarPestana("feed"));
    $("#tab-mesa").addEventListener("click", () => mostrarPestana("mesa"));
    $("#quitar-filtro").addEventListener("click", quitarFiltro);
    $("#btn-ayuda").addEventListener("click", abrirAyuda);
    $("#modal-cerrar").addEventListener("click", cerrarModal);
    $("#capa").addEventListener("click", (e) => { if (e.target.id === "capa") cerrarModal(); });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !$("#capa").hidden) cerrarModal();
      else if (e.key === " " && e.target === document.body) { e.preventDefault(); reproducirPausar(); }
    });
    window.addEventListener("resize", pintarLienzo);
    if (window.matchMedia) window.matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change", pintarLienzo);
  }

  async function iniciar() {
    construirEscena();
    enlazarControles();
    E.d = estadoVacio(null);

    // 1) ¿Hay servidor? → en directo
    const info = location.protocol.startsWith("http") ? await api("/api/info") : null;
    if (info && info.participantes) {
      E.modo = "directo";
      E.info = info;
      E.ia = !!info.ia;
      const [estado, evs] = await Promise.all([api("/api/estado"), api("/api/eventos?desde=0")]);
      E.base = estado;
      E.eventos = (evs && evs.eventos) || [];
      $("#empresa").textContent = `${info.empresa.nombre} · ${info.empresa.nif}`;
      $("#modo").className = "pill directo";
      $("#modo").lastElementChild.textContent = "En directo";
      prepararDirecto();
      // Si acaba de abrir y hay poca historia, se reproduce; si no, se muestra ya hecha
      if (E.eventos.length > 40) irA(E.eventos.length); else irA(0);
      E.d.dia = E.d.dia || info.hoy;
      pintarEscena(); pintarMesa();
      refrescarEstado();
      E.reproduciendo = true;
    } else if (window.TRAZA_DEMO) {
      // 2) Grabación incluida
      E.modo = "grabacion";
      E.info = window.TRAZA_DEMO.info;
      E.eventos = window.TRAZA_DEMO.eventos;
      $("#empresa").textContent = `${E.info.empresa.nombre} · ${E.info.empresa.nif}`;
      $("#modo").lastElementChild.textContent = "Grabación de ejemplo";
      $("#aviso-grabacion").hidden = false;
      irA(0);
      setTimeout(() => { E.reproduciendo = true; pintarBotonPlay(); }, 700);
    } else {
      E.modo = "vacio";
      E.info = { fases: [], participantes: [] };
      $("#modo").lastElementChild.textContent = "Sin datos";
      $("#feed-vacio").innerHTML = "<b>No hay oficina que mostrar</b>Abre el panel con <code>agentes-conta web --demo</code> o con tu configuración.";
      pintarEscena();
    }
    pintarBotonPlay();
    pintarMesa();
    bucle();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", iniciar);
  else iniciar();
})();
