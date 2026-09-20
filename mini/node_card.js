/**
 * Role: Mounts the Markdown PDF mini-card behavior for compact displays.
 * File Name: node_card.js
 */
/**
 * Open the PDF viewing surface through the generic compact API.
 *
 * @param {object} api - Generic block UI API supplied by the compact view.
 * @param {object} context - Markdown PDF render context.
 * @returns {void}
 */
function openPdf(api, context) {
  if (typeof api?.actions?.openPdfViewer === "function") {
    api.actions.openPdfViewer(context || {});
    return;
  }
  if (typeof api?.actions?.openBlockModal === "function") {
    api.actions.openBlockModal(context?.node_id || context?.nodeId || "");
    return;
  }
  api?.actions?.selectNode?.(context?.node_id || context?.nodeId || "");
}

/**
 * Bind tap/click activation for the compact Markdown PDF card.
 *
 * @param {HTMLElement} root - Mounted mini-card root.
 * @param {object} api - Generic compact block UI API.
 * @param {object} context - Markdown PDF render context.
 * @returns {void}
 */
export function mount(root, api, context) {
  if (!root || root.dataset.markdownPdfMiniBound === "true") {
    return;
  }
  root.dataset.markdownPdfMiniBound = "true";
  root.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    openPdf(api || {}, context || {});
  });
}
