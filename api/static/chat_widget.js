// Simple floating LLM chat widget used on visualization pages
// Features:
// - Fixed bottom-right floating panel (default open) with minimize toggle
// - Horizon selector inside the widget
// - Brief tab: POST /llm/brief to fetch markdown
// - Ask tab: SSE /llm/ask_stream with Show thinking option
// - No persistence across reloads (session-only)

(function () {
  if (window.__LLM_WIDGET_LOADED__) return;
  window.__LLM_WIDGET_LOADED__ = true;

  function el(tag, attrs, children) {
    const e = document.createElement(tag);
    if (attrs) {
      for (const k of Object.keys(attrs)) {
        if (k === "style" && typeof attrs[k] === "object") {
          Object.assign(e.style, attrs[k]);
        } else if (k === "class") {
          e.className = attrs[k];
        } else {
          e.setAttribute(k, attrs[k]);
        }
      }
    }
    if (children) {
      for (const c of [].concat(children)) {
        if (c == null) continue;
        if (typeof c === "string") e.appendChild(document.createTextNode(c));
        else e.appendChild(c);
      }
    }
    return e;
  }

  function getDefaultHorizon() {
    // If page has an #horizon input (indicators page), mirror it; fallback to 1w
    try {
      const inp = document.getElementById("horizon");
      const val = inp && inp.value ? String(inp.value).trim() : "";
      return val || "1w";
    } catch {}
    return "1w";
  }

  function createStyles() {
    const css = `
      .llm-widget{position:fixed;top:0;right:0;bottom:0;width:380px;background:#fff;border-left:1px solid #ddd;display:flex;flex-direction:column;overflow:hidden;z-index:9000}
      .llm-header{display:flex;align-items:center;justify-content:flex-start;height:48px;padding:0 12px;border-bottom:1px solid #eee;background:rgba(255,255,255,0.95)}
      .llm-header-title{font-weight:600;color:#222}
      .llm-body{display:flex;flex-direction:column;gap:8px;padding:8px 10px;overflow:auto}
      .llm-controls{display:flex;align-items:center;gap:8px}
      .llm-tabs{display:flex;gap:8px;margin-top:4px}
      .llm-tab{padding:4px 8px;border:1px solid #ddd;border-radius:6px;cursor:pointer;color:#333}
      .llm-tab.active{background:#f4f4f4}
      .llm-section{display:none}
      .llm-section.active{display:block}
      .llm-field{display:flex;align-items:center;gap:8px;margin:4px 0}
      .llm-textarea{width:100%;min-height:64px}
      .llm-stream{white-space:pre-wrap;border:1px solid #eee;padding:6px;border-radius:6px;min-height:42px}
      .llm-mini-btn{background:none;border:none;color:#333;cursor:pointer;font-size:14px;padding:4px 6px;border-radius:6px}
      .llm-mini-btn:hover{background:#f2f2f2}
    `;
    const style = el("style", {}, css);
    document.head.appendChild(style);
  }

  function buildWidget() {
    const container = el("div", { class: "llm-widget", id: "llm_widget" });

    const header = el("div", { class: "llm-header" }, [
      el("div", { class: "llm-header-title" }, "Liquidity Assistant"),
    ]);

    const body = el("div", { class: "llm-body" });

    // Controls: horizon, show thinking
    const horizonSel = el("select", { id: "llm_horizon" }, [
      el("option", { value: "1w" }, "1w"),
      el("option", { value: "1d" }, "1d"),
      el("option", { value: "2w" }, "2w"),
      el("option", { value: "1m" }, "1m"),
    ]);
    horizonSel.value = getDefaultHorizon();
    const showThinking = el("label", {}, [
      el("input", {
        type: "checkbox",
        id: "llm_show_thinking",
        checked: "checked",
      }),
      " Show thinking",
    ]);
    const controls = el("div", { class: "llm-controls" }, [
      el("span", {}, "horizon:"),
      horizonSel,
      showThinking,
    ]);

    // Tabs
    const tabs = el("div", { class: "llm-tabs" }, [
      el("div", { class: "llm-tab active", id: "llm_tab_brief" }, "Brief"),
      el("div", { class: "llm-tab", id: "llm_tab_ask" }, "Ask"),
    ]);

    // Sections
    const briefSection = el("div", {
      class: "llm-section active",
      id: "llm_sec_brief",
    });
    const briefBtn = el("button", { id: "llm_btn_brief" }, "Generate brief");
    const briefStatus = el(
      "span",
      { id: "llm_brief_status", style: { color: "#555", marginLeft: "8px" } },
      ""
    );
    const briefOut = el("div", { id: "llm_brief_md", class: "llm-stream" }, "");
    briefSection.appendChild(el("div", {}, [briefBtn, briefStatus]));
    briefSection.appendChild(briefOut);

    const askSection = el("div", { class: "llm-section", id: "llm_sec_ask" });
    const askTA = el("textarea", {
      id: "llm_ask_q",
      class: "llm-textarea",
      placeholder: "Ask about the current liquidity context…",
    });
    const askBtn = el("button", { id: "llm_btn_ask" }, "Ask (stream)");
    const askStatus = el(
      "span",
      { id: "llm_ask_status", style: { color: "#555", marginLeft: "8px" } },
      ""
    );
    const askEvents = el(
      "div",
      {
        id: "llm_ask_events",
        style: {
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
          fontSize: "12px",
          whiteSpace: "pre-wrap",
          border: "1px solid #ddd",
          padding: "8px",
          borderRadius: "6px",
          maxHeight: "240px",
          overflow: "auto",
        },
      },
      ""
    );
    const askAnswer = el(
      "div",
      { id: "llm_ask_answer", class: "llm-stream" },
      ""
    );
    askSection.appendChild(askTA);
    askSection.appendChild(el("div", {}, [askBtn, askStatus]));
    askSection.appendChild(el("div", {}, [el("strong", {}, "Agent stream")]));
    askSection.appendChild(askEvents);
    askSection.appendChild(
      el("div", { style: { marginTop: "6px" } }, [el("strong", {}, "Answer")])
    );
    askSection.appendChild(askAnswer);

    body.appendChild(controls);
    body.appendChild(tabs);
    body.appendChild(briefSection);
    body.appendChild(askSection);

    container.appendChild(header);
    container.appendChild(body);
    document.body.appendChild(container);

    // Tab behavior
    function activate(tab) {
      document.getElementById("llm_tab_brief").classList.remove("active");
      document.getElementById("llm_tab_ask").classList.remove("active");
      document.getElementById("llm_sec_brief").classList.remove("active");
      document.getElementById("llm_sec_ask").classList.remove("active");
      if (tab === "brief") {
        document.getElementById("llm_tab_brief").classList.add("active");
        document.getElementById("llm_sec_brief").classList.add("active");
      } else {
        document.getElementById("llm_tab_ask").classList.add("active");
        document.getElementById("llm_sec_ask").classList.add("active");
      }
    }
    document
      .getElementById("llm_tab_brief")
      .addEventListener("click", function () {
        activate("brief");
      });
    document
      .getElementById("llm_tab_ask")
      .addEventListener("click", function () {
        activate("ask");
      });

    // Sidebar is always open; no minimize control

    // Brief fetch
    briefBtn.addEventListener("click", async function () {
      try {
        briefStatus.textContent = "Generating…";
        briefOut.textContent = "";
        const h = document.getElementById("llm_horizon").value || "1w";
        const r = await fetch("/llm/brief?horizon=" + encodeURIComponent(h), {
          method: "POST",
        });
        if (!r.ok) throw new Error("brief failed");
        const js = await r.json();
        briefOut.textContent = js.markdown || "";
      } catch (e) {
        briefOut.textContent = "Brief failed.";
      } finally {
        briefStatus.textContent = "";
      }
    });

    // Ask stream
    let es = null;
    function closeStream() {
      if (es) {
        try {
          es.close();
        } catch (_) {}
        es = null;
      }
    }
    askBtn.addEventListener("click", function () {
      closeStream();
      askEvents.textContent = "";
      askAnswer.textContent = "";
      askStatus.textContent = "Streaming…";
      const q = (document.getElementById("llm_ask_q").value || "").trim();
      if (!q) {
        askStatus.textContent = "";
        return;
      }
      const h = document.getElementById("llm_horizon").value || "1w";
      const show = document.getElementById("llm_show_thinking").checked;
      const url =
        "/llm/ask_stream?question=" +
        encodeURIComponent(q) +
        "&horizon=" +
        encodeURIComponent(h);
      es = new EventSource(url);
      es.addEventListener("start", function (e) {
        try {
          askEvents.textContent += "start " + e.data + "\n";
        } catch (_) {}
        askEvents.scrollTop = askEvents.scrollHeight;
      });
      es.addEventListener("decision", function (e) {
        try {
          askEvents.textContent += "decision " + e.data + "\n";
        } catch (_) {}
        askEvents.scrollTop = askEvents.scrollHeight;
      });
      es.addEventListener("tool_call", function (e) {
        try {
          askEvents.textContent += "tool_call " + e.data + "\n";
        } catch (_) {}
        askEvents.scrollTop = askEvents.scrollHeight;
      });
      es.addEventListener("tool_result", function (e) {
        try {
          askEvents.textContent += "tool_result " + e.data + "\n";
        } catch (_) {}
        askEvents.scrollTop = askEvents.scrollHeight;
      });
      es.addEventListener("ping", function (e) {
        try {
          askEvents.textContent += "ping " + e.data + "\n";
        } catch (_) {}
        askEvents.scrollTop = askEvents.scrollHeight;
      });
      es.addEventListener("thinking_token", function (e) {
        if (!show) return;
        try {
          const d = JSON.parse(e.data);
          askEvents.textContent += d.text || "";
        } catch (_) {}
        askEvents.scrollTop = askEvents.scrollHeight;
      });
      es.addEventListener("answer_token", function (e) {
        try {
          const d = JSON.parse(e.data);
          askAnswer.textContent += d.text || "";
        } catch (_) {}
        askAnswer.scrollTop = askAnswer.scrollHeight;
      });
      es.addEventListener("final", function (e) {
        try {
          const d = JSON.parse(e.data);
          if (!askAnswer.textContent) askAnswer.textContent = d.answer || "";
        } catch (_) {
          if (!askAnswer.textContent) askAnswer.textContent = e.data || "";
        }
        askStatus.textContent = "";
        closeStream();
      });
      es.onerror = function () {
        askStatus.textContent = "Stream error.";
        closeStream();
      };
    });

    // Cleanup on navigation
    window.addEventListener("beforeunload", closeStream);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      createStyles();
      buildWidget();
    });
  } else {
    createStyles();
    buildWidget();
  }
})();
