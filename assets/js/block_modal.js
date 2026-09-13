(function () {
  "use strict";

  const registry = (window.CWBlockUiBlocks = window.CWBlockUiBlocks || {});

  /**
   * Activate one Markdown PDF modal tab without replacing the modal content.
   *
   * @param {HTMLElement} root - Mounted Markdown PDF modal root.
   * @param {string} tabName - Target tab and panel identifier.
   */
  function activateTab(root, tabName) {
    const target = String(tabName || "attributes");
    root.querySelectorAll("[data-block-modal-tab]").forEach((tab) => {
      const active = tab.getAttribute("data-block-modal-tab") === target;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });
    root.querySelectorAll("[data-block-modal-panel]").forEach((panel) => {
      const active = panel.getAttribute("data-block-modal-panel") === target;
      panel.classList.toggle("is-active", active);
      panel.toggleAttribute("hidden", !active);
    });
  }

  /**
   * Bind Markdown PDF modal tabs and block-owned close affordance.
   *
   * @param {HTMLElement} root - Mounted Markdown PDF modal root.
   * @param {object} api - Generic block UI API.
   */
  function mount(root, api = {}) {
    const activeTab = root.querySelector("[data-block-modal-tab].is-active")?.getAttribute("data-block-modal-tab") || "attributes";
    activateTab(root, activeTab);

    root.addEventListener("click", (event) => {
      const tab = event.target.closest("[data-block-modal-tab]");
      if (tab && root.contains(tab)) {
        event.preventDefault();
        activateTab(root, tab.getAttribute("data-block-modal-tab"));
        return;
      }
      const closeButton = event.target.closest("[data-block-modal-close]");
      if (closeButton && root.contains(closeButton)) {
        event.preventDefault();
        api.close?.();
      }
    });
  }

  registry.markdown_pdf = { mount };
})();
