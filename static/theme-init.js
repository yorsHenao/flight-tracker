// Se carga en <head> para aplicar el tema antes de pintar (evita parpadeo)
try {
  if (localStorage.getItem("vuelos_theme") === "dark") {
    document.documentElement.setAttribute("data-theme", "dark");
  }
  document.documentElement.setAttribute("data-palette", "mono-azul");
} catch (e) {}
