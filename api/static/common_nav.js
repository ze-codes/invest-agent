(function () {
  if (window.__COMMON_NAV__) return;
  window.__COMMON_NAV__ = true;
  function injectNav() {
    var nav = document.getElementById("top_nav");
    if (!nav) {
      nav = document.createElement("div");
      nav.id = "top_nav";
      document.body.appendChild(nav);
    }
    // Apply styles and (re)populate links
    nav.setAttribute(
      "style",
      [
        "position: fixed",
        "top: 0",
        "left: 0",
        "right: 0",
        "height: 48px",
        "display: flex",
        "align-items: center",
        "justify-content: flex-start",
        "gap: 16px",
        "padding: 0 12px",
        "background: rgba(255, 255, 255, 0.9)",
        "border-bottom: 1px solid #eee",
        "z-index: 9000",
        "backdrop-filter: saturate(120%) blur(6px)",
      ].join(";")
    );
    function link(href, text, current) {
      var a = document.createElement("a");
      a.href = href;
      a.textContent = text;
      a.setAttribute(
        "style",
        "text-decoration:none;color:#222;font-weight:600;padding:6px 10px;border-radius:6px;"
      );
      if (current) a.setAttribute("aria-current", "page");
      return a;
    }
    var path = (location && location.pathname) || "";
    // Reset content before adding links
    nav.innerHTML = "";
    nav.appendChild(
      link(
        "/static/viz_indicators.html",
        "Indicators",
        path.endsWith("/viz_indicators.html")
      )
    );
    nav.appendChild(
      link(
        "/static/viz_series.html",
        "Data Series",
        path.endsWith("/viz_series.html")
      )
    );
  }
  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", injectNav);
  else injectNav();
})();
