(function () {
  "use strict";

  // 1. Modo Claro / Oscuro persistente
  var rootEl = document.documentElement;
  var themeToggleBtn = document.getElementById("theme-toggle");
  var mobileThemeBtn = document.getElementById("mobile-theme-switch");
  var themeLabel = document.getElementById("theme-toggle-label");

  function applyTheme(theme) {
    if (theme === "dark") {
      rootEl.setAttribute("data-theme", "dark");
      if (themeLabel) themeLabel.textContent = "Modo claro";
    } else {
      rootEl.removeAttribute("data-theme");
      if (themeLabel) themeLabel.textContent = "Modo oscuro";
    }
    try {
      localStorage.setItem("vuelos_theme", theme);
    } catch (e) {}
  }

  try {
    var savedTheme = localStorage.getItem("vuelos_theme");
    if (savedTheme === "dark" || savedTheme === "light") {
      applyTheme(savedTheme);
    }
  } catch (e) {}

  function toggleTheme() {
    var isDark = rootEl.getAttribute("data-theme") === "dark";
    applyTheme(isDark ? "light" : "dark");
  }

  if (themeToggleBtn) themeToggleBtn.addEventListener("click", toggleTheme);
  if (mobileThemeBtn) mobileThemeBtn.addEventListener("click", toggleTheme);

  // 2. Botón circular ⇅ para intercambiar Origen y Destino
  var swapBtn = document.getElementById("swap-route-btn");
  var originField = document.getElementById("origin");
  var destField = document.getElementById("destination");

  if (swapBtn && originField && destField) {
    swapBtn.addEventListener("click", function () {
      var tmp = originField.value;
      originField.value = destField.value;
      destField.value = tmp;
    });
  }

  // 3. Selector de fecha propio (DD-MM-AAAA), teclado, móvil y modo oscuro
  var monthInput = document.getElementById("travel_month");
  var MESES = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"];
  var DIAS = ["L","M","X","J","V","S","D"];
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function toDmy(d) { return pad(d.getDate()) + "-" + pad(d.getMonth() + 1) + "-" + d.getFullYear(); }
  function parseDmy(v) {
    var m = (v || "").trim().replace(/\//g, "-").match(/^(\d{1,2})-(\d{1,2})-(\d{4})$/);
    if (!m) return null;
    var d = new Date(+m[3], +m[2] - 1, +m[1]);
    return d.getDate() === +m[1] && d.getMonth() === +m[2] - 1 ? d : null;
  }
  function today() { var t = new Date(); t.setHours(0, 0, 0, 0); return t; }
  function same(a, b) { return a && b && a.getTime() === b.getTime(); }

  document.querySelectorAll("[data-datepicker]").forEach(function (wrap) {
    var input = wrap.querySelector("input");
    var trigger = wrap.querySelector(".dp-trigger");
    var hint = document.getElementById(input.getAttribute("aria-describedby"));
    var minFromId = wrap.getAttribute("data-min-from"); // p. ej. regreso >= ida
    var pop = document.createElement("div");
    pop.className = "dp-pop"; pop.hidden = true;
    pop.setAttribute("role", "dialog"); pop.setAttribute("aria-label", "Elegir fecha");
    wrap.appendChild(pop);
    var view, focusDay;

    function minDate() {
      var m = today();
      if (minFromId) { var o = parseDmy(document.getElementById(minFromId).value); if (o && o > m) m = o; }
      return m;
    }
    function validate() {
      var d = parseDmy(input.value), msg = "";
      if (input.value && !d) msg = "Usa el formato DD-MM-AAAA, por ejemplo 20-12-2026.";
      else if (d && d < today()) msg = "Elige una fecha de hoy en adelante.";
      else if (d && minFromId && d < minDate()) msg = "El regreso debe ser igual o posterior a la ida.";
      input.setCustomValidity(msg);
      input.classList.toggle("dp-invalid", !!msg);
      if (hint) hint.textContent = msg;
      if (d && !msg && monthInput && input.id === "travel_date") monthInput.value = d.getFullYear() + "-" + pad(d.getMonth() + 1);
      return !msg;
    }
    function render() {
      var sel = parseDmy(input.value), min = minDate();
      var first = new Date(view.getFullYear(), view.getMonth(), 1);
      var offset = (first.getDay() + 6) % 7;
      var days = new Date(view.getFullYear(), view.getMonth() + 1, 0).getDate();
      var prevDisabled = new Date(view.getFullYear(), view.getMonth(), 0) < min;
      var h = '<div class="dp-head"><button type="button" class="dp-nav" data-nav="-1" aria-label="Mes anterior"' + (prevDisabled ? " disabled" : "") + '><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M15 6l-6 6 6 6"/></svg></button>' +
        '<div class="dp-month" aria-live="polite">' + MESES[view.getMonth()] + " " + view.getFullYear() + '</div>' +
        '<button type="button" class="dp-nav" data-nav="1" aria-label="Mes siguiente"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M9 6l6 6-6 6"/></svg></button></div>' +
        '<div class="dp-grid" role="grid">';
      DIAS.forEach(function (d) { h += '<span class="dp-dow" aria-hidden="true">' + d + "</span>"; });
      for (var i = 0; i < offset; i++) h += "<span></span>";
      for (var n = 1; n <= days; n++) {
        var d = new Date(view.getFullYear(), view.getMonth(), n);
        var dis = d < min, cls = "dp-day" + (same(d, sel) ? " is-selected" : "") + (same(d, today()) ? " is-today" : "");
        h += '<button type="button" class="' + cls + '" data-day="' + n + '" tabindex="' + (same(d, focusDay) ? 0 : -1) + '" aria-label="' + n + " de " + MESES[view.getMonth()] + " de " + view.getFullYear() + '"' + (same(d, sel) ? ' aria-selected="true"' : "") + (dis ? " disabled" : "") + ">" + n + "</button>";
      }
      h += '</div><div class="dp-foot"><button type="button" class="dp-link" data-today>Hoy</button><button type="button" class="dp-link" data-close>Cerrar</button></div>';
      pop.innerHTML = h;
    }
    function focusCurrent() { var b = pop.querySelector('.dp-day[tabindex="0"]'); if (b) b.focus(); }
    function open() {
      var sel = parseDmy(input.value), min = minDate();
      focusDay = sel && sel >= min ? sel : min;
      view = new Date(focusDay.getFullYear(), focusDay.getMonth(), 1);
      render(); pop.hidden = false; trigger.setAttribute("aria-expanded", "true");
      wrap.classList.add("dp-open"); focusCurrent();
    }
    function close(refocus) {
      pop.hidden = true; trigger.setAttribute("aria-expanded", "false");
      wrap.classList.remove("dp-open"); if (refocus) trigger.focus();
    }
    function pick(d) { input.value = toDmy(d); validate(); input.dispatchEvent(new Event("change", { bubbles: true })); close(true); }
    function moveFocus(d) {
      if (d < minDate()) return;
      focusDay = d; view = new Date(d.getFullYear(), d.getMonth(), 1); render(); focusCurrent();
    }

    trigger.addEventListener("click", function () { pop.hidden ? open() : close(true); });
    input.addEventListener("click", function () { if (pop.hidden) open(); });
    input.addEventListener("input", function () {
      // Autoformato al escribir: 20122026 -> 20-12-2026
      var digits = input.value.replace(/\D/g, "").slice(0, 8);
      if (input.value.indexOf("-") === -1 && input.value.indexOf("/") === -1) {
        input.value = digits.length > 4 ? digits.slice(0, 2) + "-" + digits.slice(2, 4) + "-" + digits.slice(4)
          : digits.length > 2 ? digits.slice(0, 2) + "-" + digits.slice(2) : digits;
      }
      validate();
    });
    input.addEventListener("keydown", function (e) { if (e.key === "ArrowDown" && e.altKey) { e.preventDefault(); open(); } });
    pop.addEventListener("click", function (e) {
      var t = e.target.closest("button"); if (!t || t.disabled) return;
      if (t.hasAttribute("data-nav")) { view = new Date(view.getFullYear(), view.getMonth() + +t.getAttribute("data-nav"), 1); focusDay = new Date(view); if (focusDay < minDate()) focusDay = minDate(); render(); }
      else if (t.hasAttribute("data-day")) pick(new Date(view.getFullYear(), view.getMonth(), +t.getAttribute("data-day")));
      else if (t.hasAttribute("data-today")) pick(minDate());
      else if (t.hasAttribute("data-close")) close(true);
    });
    pop.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { e.preventDefault(); close(true); return; }
      if (!e.target.classList.contains("dp-day")) return;
      var d = new Date(focusDay), k = e.key;
      if (k === "ArrowLeft") d.setDate(d.getDate() - 1);
      else if (k === "ArrowRight") d.setDate(d.getDate() + 1);
      else if (k === "ArrowUp") d.setDate(d.getDate() - 7);
      else if (k === "ArrowDown") d.setDate(d.getDate() + 7);
      else if (k === "PageUp") d.setMonth(d.getMonth() - 1);
      else if (k === "PageDown") d.setMonth(d.getMonth() + 1);
      else return;
      e.preventDefault(); moveFocus(d);
    });
    document.addEventListener("mousedown", function (e) { if (!pop.hidden && !wrap.contains(e.target)) close(false); });
    if (minFromId) { var src = document.getElementById(minFromId); if (src) src.addEventListener("change", validate); }
    validate();
  });

  // 3a. Abrir "Más opciones" si un campo interno no es válido
  document.querySelectorAll("details.more-options input, details.more-options select").forEach(function (f) {
    f.addEventListener("invalid", function () { var d = f.closest("details"); if (d) d.open = true; });
  });

  // 3c. Barra de búsqueda tipo píldora: popovers, segmentos y chips
  (function () {
    var pops = document.querySelectorAll(".sb-pop");
    function closeAll(except) {
      pops.forEach(function (p) {
        if (p !== except && !p.hidden) {
          p.hidden = true;
          var t = document.querySelector('[data-pop-toggle="' + p.id + '"]');
          if (t) { t.setAttribute("aria-expanded", "false"); t.closest(".sb-seg, .sb-chip-wrap").classList.remove("is-open"); }
        }
      });
    }
    function openPop(id) {
      var p = document.getElementById(id), t = document.querySelector('[data-pop-toggle="' + id + '"]');
      if (!p) return;
      closeAll(p); p.hidden = false;
      t.setAttribute("aria-expanded", "true"); t.closest(".sb-seg, .sb-chip-wrap").classList.add("is-open");
      var f = p.querySelector("input, select, button"); if (f) { f.focus(); if (f.select && f.tagName === "INPUT") f.select(); }
    }
    document.querySelectorAll("[data-pop-toggle]").forEach(function (t) {
      t.addEventListener("click", function () {
        var p = document.getElementById(t.getAttribute("data-pop-toggle"));
        if (p.hidden) openPop(p.id); else closeAll();
      });
    });
    document.addEventListener("mousedown", function (e) {
      if (!e.target.closest(".sb-seg, .sb-chip-wrap")) closeAll();
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        var open = document.querySelector(".sb-pop:not([hidden])");
        if (open) { var t = document.querySelector('[data-pop-toggle="' + open.id + '"]'); closeAll(); if (t) t.focus(); }
      }
    });

    // Segmentos de ciudad: código IATA grande + ciudad pequeña
    function paintCity(seg) {
      var input = seg.querySelector("input"), v = (input.value || "").trim();
      var m = v.match(/\(([A-Za-z]{3})\)\s*$/);
      var name = v.replace(/\s*\([^)]*\)\s*$/, "");
      seg.querySelector("[data-iata]").textContent = m ? m[1].toUpperCase() : (name.split(",")[0] || "Elegir");
      seg.querySelector("[data-cityname]").textContent = m ? name : (name ? "Ciudad o país" : "Ciudad o aeropuerto");
      var fold = function (t) { return t.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, ""); };
      var q = fold(v), shown = 0;
      seg.querySelectorAll("[data-sug]").forEach(function (b) {
        var extra = b.hasAttribute("data-extra");
        var hit = !q || !!m || fold(b.getAttribute("data-sug")).indexOf(q) !== -1;
        if (extra && (!q || m)) hit = false;
        if (hit && q && !m) { shown += 1; if (shown > 12) hit = false; }
        b.hidden = !hit;
      });
    }
    document.querySelectorAll("[data-city-seg]").forEach(function (seg) {
      var input = seg.querySelector("input");
      paintCity(seg);
      input.addEventListener("input", function () { paintCity(seg); });
      input.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); closeAll(); } });
      input.addEventListener("invalid", function () { openPop(seg.querySelector(".sb-pop").id); });
      seg.querySelectorAll("[data-sug]").forEach(function (b) {
        b.addEventListener("click", function () { input.value = b.getAttribute("data-sug"); paintCity(seg); closeAll(); });
      });
    });
    var swap = document.getElementById("swap-route-btn");
    if (swap) swap.addEventListener("click", function () {
      setTimeout(function () { document.querySelectorAll("[data-city-seg]").forEach(paintCity); }, 0);
    });

    // Segmento de fecha: toda la zona abre el calendario; día de la semana debajo
    var DOW = ["domingo","lunes","martes","miércoles","jueves","viernes","sábado"];
    var dateSeg = document.querySelector("[data-date-seg]");
    if (dateSeg) {
      var di = dateSeg.querySelector("input"), wd = dateSeg.querySelector("[data-weekday]");
      function paintDate() {
        var m = (di.value || "").match(/^(\d{2})-(\d{2})-(\d{4})$/);
        wd.textContent = m ? DOW[new Date(+m[3], +m[2] - 1, +m[1]).getDay()] : "Elige un día";
      }
      paintDate();
      di.addEventListener("change", paintDate); di.addEventListener("input", paintDate);
      dateSeg.addEventListener("click", function (e) {
        if (e.target === dateSeg || e.target.classList.contains("sb-label") || e.target === wd) di.click();
      });
    }

    // Chips: muestran el valor elegido
    document.querySelectorAll("[data-chip-for]").forEach(function (el) {
      var f = document.getElementById(el.getAttribute("data-chip-for"));
      function paint() { el.textContent = f.tagName === "SELECT" ? f.options[f.selectedIndex].text : f.value; }
      paint(); f.addEventListener("change", paint); f.addEventListener("input", paint);
      f.addEventListener("invalid", function () { openPop(f.closest(".sb-pop").id); });
    });
    var sitesLabel = document.querySelector("[data-chip-sites]");
    document.querySelectorAll("#pop-sites [data-portal-filter]").forEach(function (c) {
      c.addEventListener("click", function () { if (sitesLabel) sitesLabel.textContent = c.textContent; });
    });
  })();

  // 3b. Mostrar / ocultar contraseña (login)
  document.querySelectorAll("[data-reveal]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var f = document.getElementById(btn.getAttribute("data-reveal"));
      var show = f.type === "password";
      f.type = show ? "text" : "password";
      btn.textContent = show ? "Ocultar" : "Mostrar";
      btn.setAttribute("aria-label", show ? "Ocultar contraseña" : "Mostrar contraseña");
    });
  });

  // 4. Sitios: Google Flights (precios reales), Kayak, Skyscanner y Booking (abren la búsqueda
  //    con la ruta precargada). Aerolíneas: solo filtran los resultados de Google y reservan en Google.
  var portalChips = document.querySelectorAll("[data-portal-filter]");
  var flightCards = document.querySelectorAll("[data-flight-card]");
  var SITE_TEXT = { kayak: "Kayak", skyscanner: "Skyscanner", booking: "Booking" };
  var SITE_ATTR = { kayak: "data-kayak-url", skyscanner: "data-sky-url", booking: "data-booking-url" };
  var AIRLINES = ["latam", "jetsmart", "wingo", "avianca"];

  portalChips.forEach(function (chip) {
    chip.addEventListener("click", function () {
      var selected = chip.getAttribute("data-portal-filter") || "all";
      portalChips.forEach(function (c) { c.classList.toggle("active", c === chip); });

      flightCards.forEach(function (card) {
        var airKey = card.getAttribute("data-airline-key") || "";
        var btn = card.querySelector("[data-main-buy-btn]");
        var label = card.querySelector("[data-provider-label]");
        var gfUrl = card.getAttribute("data-gf-booking");
        var baseText = (btn && btn.getAttribute("data-buy-label")) || "Comprar →";
        card.style.display = "";
        var url = gfUrl, text = baseText, via = "Reserva directa · Google Flights";

        if (SITE_ATTR[selected] && card.getAttribute(SITE_ATTR[selected])) {
          url = card.getAttribute(SITE_ATTR[selected]);
          text = SITE_TEXT[selected] + " →";
          via = "Vía " + SITE_TEXT[selected];
        } else if (AIRLINES.indexOf(selected) !== -1 && airKey !== selected) {
          card.style.display = "none";
        }
        if (btn && url) { btn.href = url; btn.textContent = text; }
        if (label) label.textContent = via;
      });
    });
  });

  // 5. Navegación por Pestañas (Escritorio y Barra Inferior Móvil)
  var tabButtons = document.querySelectorAll("[data-tab-target]");
  var tabPanels = document.querySelectorAll(".tab-panel");

  function activateTab(tabId) {
    tabButtons.forEach(function (btn) {
      btn.classList.toggle("active", btn.getAttribute("data-tab-target") === tabId);
    });
    tabPanels.forEach(function (panel) {
      panel.classList.toggle("active", panel.id === tabId);
    });
  }

  tabButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      var target = btn.getAttribute("data-tab-target");
      if (target) activateTab(target);
    });
  });

  // 6. Ideas rápidas
  var presetButtons = document.querySelectorAll("[data-preset-origin]");
  presetButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      if (originField && destField) {
        originField.value = btn.getAttribute("data-preset-origin") || "";
        destField.value = btn.getAttribute("data-preset-dest") || "";
      }
    });
  });

  // 7. Cerrar avisos
  var closeBtns = document.querySelectorAll("[data-dismiss-banner]");
  closeBtns.forEach(function (btn) {
    btn.addEventListener("click", function () {
      var toast = btn.closest(".stitch-toast");
      if (toast) toast.remove();
    });
  });

  // Evitar doble envío (doble clic) en todos los formularios POST
  document.querySelectorAll('form[method="post"], form[method="POST"]').forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (form.dataset.enviando === "1") { e.preventDefault(); return; }
      form.dataset.enviando = "1";
      setTimeout(function () { form.dataset.enviando = ""; }, 8000);
    });
  });
})();

// Animación de rutas en la pantalla de acceso (antes estaba en línea)
    (function () {
      var R = [["BOG","Bogotá","CLO","Cali"],["MDE","Medellín","CTG","Cartagena"],["BOG","Bogotá","MIA","Miami"],["CLO","Cali","MAD","Madrid"],
               ["BOG","Bogotá","CUN","Cancún"],["MDE","Medellín","SMR","Santa Marta"],["BOG","Bogotá","LIM","Lima"],["CTG","Cartagena","PTY","Ciudad de Panamá"]];
      var el = document.getElementById("lg-route"); if (!el) return;
      var i = Math.floor(Math.random() * R.length);
      function set(k) { var r = R[k]; ["o","oc","d","dc"].forEach(function (key, n) { el.querySelector('[data-r="' + key + '"]').textContent = r[n]; }); }
      set(i);
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
      setInterval(function () {
        var n; do { n = Math.floor(Math.random() * R.length); } while (n === i); i = n;
        el.classList.add("is-out");
        setTimeout(function () { set(i); el.classList.remove("is-out"); }, 450);
      }, 5000);
    })();
