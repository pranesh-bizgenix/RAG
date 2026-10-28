// Loaded in <head> so the saved theme applies before first paint.
(function () {
  var saved = null;
  try {
    saved = localStorage.getItem("theme");
  } catch (error) {
    saved = null;
  }
  var dark = saved ? saved === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
})();
