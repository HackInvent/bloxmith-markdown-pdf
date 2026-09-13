# Markdown PDF

<!-- block-metadata:start -->
[![Block version: unversioned](https://img.shields.io/badge/block-unversioned-lightgrey)](model.json)
[![BloxSmith compatibility: 1.0.9](https://img.shields.io/badge/BloxSmith-1.0.9-brightgreen)](compatibility.json)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

Verified BloxSmith versions: **1.0.9** (bundled-block tests; see [test evidence](compatibility.json)).
<!-- block-metadata:end -->


Convert Markdown input to a PDF file with `pandoc`.

## Ports and behavior

- Input **`markdown`** accepts `text/markdown`, `text/plain` and `message/*`.
- Output **`pdf`** emits the absolute PDF path as `file/path`, with `mime_type=application/pdf` metadata.

The PDF is written inside the open project's directory. Relative paths resolve from that directory; paths escaping it are rejected.

## Configuration

| Field | Default | Meaning |
| --- | --- | --- |
| `output_path` | `exports/tmp.pdf` | Target PDF path |
| `from_format` | `markdown` | Pandoc input format |
| `paper_size` | `a4` | `a4`, `a3` or `letter` |
| `margin` | `20mm` | Passed as `geometry:margin` |
| `toc` | See `model.json` | Include a table of contents when enabled |
| `metadata_title` | Optional | Pandoc title metadata |
| `timeout_sec` | See `model.json` | Execution timeout, 1–3,600 seconds |

## Dependencies and runtime

The server needs `pandoc` on PATH. Its installation may also require a compatible PDF engine such as LaTeX, WeasyPrint or wkhtmltopdf. The block does not install dependencies.

The generic runtime supports `centralized` and `zeromq_active`. Empty Markdown, invalid paths, missing Pandoc, timeouts and conversion errors return `failed` with explicit logs.

## Inspector and modal

The block-owned `inspector_panel.html` exposes Pandoc attributes, block actions, port editing and runtime values.

`block_modal.html` declares `data-block-runtime-refresh="autonomous"` so polling does not reset tabs or draft fields. `assets/js/block_modal.js` owns Attributes, Ports and Runtime tabs and the close button. Configuration stays local until Apply through the generic framework.

## Compact card

The block-owned `mini/` directory provides:

- `mini/node_card.html`: compact PDF-oriented card.
- `mini/node_card.css`: compact styles.
- `mini/node_card.js`: `markdown_pdfMiniNodeCard`, opening the PDF viewer through the generic compact API, with modal/selection fallback.

## Compatibility policy

[compatibility.json](compatibility.json) records HackInvent's verified BloxSmith versions and test evidence. Only the versions listed above have been verified, using the block-owned suites in a **bundled-block test installation**. This is not a certification of managed-package installation, every browser/OS, or live provider availability. Other framework versions are unverified, not necessarily incompatible.

The block-version badge follows `model.json`, not a published Git tag. `unversioned` means that no block release version is declared; no number is inferred from the framework version. The framework still uses `model.json` for its runtime/install contract; the tester-owned JSON does not replace it. Official integration tests run in the private `bloxmith-blocs` workspace. Test helpers and the proprietary framework are not bundled in this public block repository.
