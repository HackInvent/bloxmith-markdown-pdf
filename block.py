# -----------------------------------------------------------------------------
# Role: Implements Markdown to PDF conversion through Pandoc.
# File Name: block.py
# Author: Alexandre EL
# Email: alex@hackinvent.com
# Created Date: 2026-05-19
# -----------------------------------------------------------------------------

from __future__ import annotations

from html import escape
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import os
import shutil
import subprocess
import tempfile

from bloxsmith_app.block_api import (
    BlockDefinition,
    BlockRuntimeContext,
    BlockRuntimeOutput,
    BlockRuntimeResult,
    FILE_PATH,
    render_inspector_template,
    render_mini_node_card_template,
    render_node_card_template,
    TEXT_PLAIN,
)


PDF_CONTENT_TYPE = "application/pdf"
TEXT_MARKDOWN = "text/markdown"
DEFAULT_OUTPUT_PATH = "exports/tmp.pdf"
DEFAULT_FROM_FORMAT = "markdown"
DEFAULT_PAPER_SIZE = "a4"
DEFAULT_MARGIN = "20mm"
DEFAULT_TIMEOUT_SEC = 120
MAX_TIMEOUT_SEC = 3600


class MarkdownPdfBlockError(ValueError):
    """Raised when Markdown PDF configuration cannot be executed safely."""


# Functional behavior:
# FB1 - Render block-owned UI surfaces with a safe default PDF target.
# FB2 - Fail explicitly when Pandoc or required execution configuration is unavailable.
# FB3 - Convert non-empty Markdown into a scoped PDF file and emit its path.
# FB4 - Preserve the same conversion contract in centralized and zeromq_active runtimes.
class MarkdownPdfBlock(BlockDefinition):
    """Convert Markdown text received from the graph into a PDF file.

    The block owns its path resolution, Pandoc invocation, UI rendering, and
    runtime result publication. Relative output paths are resolved inside the
    project directory so the generated PDF remains part of the opened project.
    """

    kind = "markdown_pdf"

    def render_node_card(self, *, node: dict[str, Any], payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Render the compact graph card with the configured PDF target."""

        config = self._ui_config(node)
        return render_node_card_template(
            block=self,
            node=node,
            node_classes=["markdown-pdf-node"],
            replacements={
                "title": node.get("title") or self.default_title(),
                "output_path": config["output_path"],
                "format": f"{config['paper_size'].upper()} / {'TOC' if config['toc'] else 'sans sommaire'}",
            },
        )

    def render_mini_node_card(self, *, node: dict[str, Any], payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Render the compact Markdown PDF card for reduced displays.

        Args:
            node: Serialized Markdown PDF node being rendered.
            payload: Optional compact UI payload.

        Returns:
            Block UI payload consumed by the generic compact view.
        """

        config = self._ui_config(node)
        return render_mini_node_card_template(
            block=self,
            node=node,
            node_classes=["markdown-pdf-mini-node"],
            replacements={
                "title": node.get("title") or self.default_title(),
                "format": f"{config['paper_size'].upper()} / {'TOC' if config['toc'] else 'sans sommaire'}",
            },
        )

    def render_inspector_panel(self, *, node: dict[str, Any], payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Render the inspector with editable Pandoc PDF settings."""

        config = self._ui_config(node)
        template = (self.directory / "inspector_panel.html").read_text(encoding="utf-8")
        html = render_inspector_template(
            template=template,
            node={**node, "type": self.kind, "kind": self.kind},
            payload=payload,
            replacements=self._template_replacements(config),
            show_duplicate=True,
        )
        return {"html": html, "context": {"node_id": str(node.get("id") or ""), "full_panel": True}}

    def render_modal(self, *, node: dict[str, Any], payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Render the modal with attributes, ports, runtime state, and errors."""

        config = self._ui_config(node)
        template = (self.directory / "block_modal.html").read_text(encoding="utf-8")
        html = self._render_generic_modal_template(template=template, node=node, payload=payload or {})
        for key, value in self._template_replacements(config).items():
            html = html.replace(f"{{{{ {key} }}}}", str(value))
        return {
            "html": html,
            "context": {
                "node_id": str(node.get("id") or ""),
                "node_kind": self.kind,
                "output_path": config["output_path"],
            },
        }

    def handle_ui_action(
        self,
        *,
        node: dict[str, Any],
        action: str,
        values: dict[str, Any],
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Delegate generic inspector and modal field updates to the base contract."""

        if action in {"inspector_update_fields", "modal_update_fields"}:
            return super().handle_ui_action(node=node, action=action, values=values, payload=payload)
        return {"error": f"unsupported_action:{action}"}

    def execute_runtime(self, context: BlockRuntimeContext) -> BlockRuntimeResult:
        """Run Pandoc on the Markdown input and emit the generated PDF path.

        Args:
            context: Runtime context containing Markdown inputs, node config,
                output ports, and the project root directory.

        Returns:
            A successful result containing one file path per output port, or a
            failed result with logs explaining the missing dependency, invalid
            path, empty input, timeout, or Pandoc error.
        """

        config = self._runtime_config(context.config)
        logs = [f"[markdown-pdf] {context.node_id}: output={config['output_path']} format={config['from_format']}."]
        markdown = self._runtime_markdown(context)
        if not markdown.strip():
            error = self.translate("block.markdown_pdf.error_no_markdown",
                fallback="No Markdown received on the block input.")
            logs.append(f"[markdown-pdf-error] {context.node_id}: {error}")
            return self._failed(error, logs, metadata={"reason": "empty_markdown"})

        pandoc_binary = shutil.which("pandoc")
        if not pandoc_binary:
            error = "Pandoc is required to generate the PDF. Install pandoc and a compatible PDF engine."
            logs.append(f"[markdown-pdf-error] {context.node_id}: {error}")
            return self._failed(error, logs, metadata={"reason": "pandoc_required"})

        try:
            output_path = self._resolve_output_path(context.root_dir, config["output_path"])
        except MarkdownPdfBlockError as exc:
            error = str(exc)
            logs.append(f"[markdown-pdf-error] {context.node_id}: {error}")
            return self._failed(error, logs, metadata={"reason": "invalid_output_path"})

        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_markdown_path: Path | None = None
        try:
            temp_markdown_path = self._write_temp_markdown(output_path.parent, markdown)
            command = self._pandoc_command(
                pandoc_binary=pandoc_binary,
                markdown_path=temp_markdown_path,
                output_path=output_path,
                config=config,
            )
            logs.append(f"[markdown-pdf] {context.node_id}: commande={' '.join(command)}")
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=config["timeout_sec"],
                check=False,
            )
        except subprocess.TimeoutExpired:
            error = f"Pandoc exceeded the {config['timeout_sec']}s timeout."
            logs.append(f"[markdown-pdf-error] {context.node_id}: {error}")
            return self._failed(error, logs, exit_code=124, metadata={"reason": "timeout"})
        except OSError as exc:
            error = f"Pandoc execution failed: {exc}"
            logs.append(f"[markdown-pdf-error] {context.node_id}: {error}")
            return self._failed(error, logs, metadata={"reason": "pandoc_os_error"})
        finally:
            if temp_markdown_path is not None:
                temp_markdown_path.unlink(missing_ok=True)

        if completed.stdout.strip():
            logs.append(completed.stdout.strip())
        if completed.stderr.strip():
            logs.append(completed.stderr.strip())
        if completed.returncode != 0:
            error = f"Pandoc failed with code {completed.returncode}."
            logs.append(f"[markdown-pdf-error] {context.node_id}: {error}")
            return self._failed(error, logs, exit_code=completed.returncode, metadata={"reason": "pandoc_failed"})
        if not output_path.is_file() or output_path.stat().st_size <= 0:
            error = "Pandoc did not produce a usable PDF file."
            logs.append(f"[markdown-pdf-error] {context.node_id}: {error}")
            return self._failed(error, logs, metadata={"reason": "missing_pdf"})

        size = output_path.stat().st_size
        display_path = self._relative_path(context.root_dir, output_path)
        logs.append(f"[done] Markdown PDF {context.node_id}: file written {display_path} ({size} bytes).")
        output_ports = tuple(context.output_ports or ())
        if not output_ports:
            output_ports = (SimpleNamespace(id=1, name="pdf"),)
        outputs = [
            BlockRuntimeOutput(
                port_id=int(getattr(port, "id", 1) or 1),
                port_name=str(getattr(port, "name", "") or "pdf"),
                value=str(output_path),
                content_type=FILE_PATH,
                metadata={
                    "path": display_path,
                    "absolute_path": str(output_path),
                    "bytes": size,
                    "mime_type": PDF_CONTENT_TYPE,
                },
            )
            for port in output_ports
        ]
        return BlockRuntimeResult(
            status="success",
            outputs=outputs,
            logs=logs,
            last_message=display_path,
            content_type=FILE_PATH,
            worker_received=display_path,
            metadata={
                "output_path": display_path,
                "absolute_path": str(output_path),
                "bytes": size,
                "mime_type": PDF_CONTENT_TYPE,
            },
        )

    def preview_received(self, *, node: Any, **runtime_services: Any) -> str:
        """Return the configured PDF target for runtime preview rows."""

        config = self._runtime_config(getattr(node, "config", {}) or {})
        return config["output_path"]

    def _ui_config(self, node: dict[str, Any]) -> dict[str, Any]:
        """Return normalized config for a serialized graph node."""

        return self._runtime_config(node.get("config") if isinstance(node.get("config"), dict) else {})

    def _runtime_config(self, raw_config: dict[str, Any]) -> dict[str, Any]:
        """Normalize user-editable Pandoc PDF settings."""

        config = raw_config if isinstance(raw_config, dict) else {}
        return {
            "output_path": self._normalize_output_path(config.get("output_path")),
            "from_format": self._normalize_from_format(config.get("from_format")),
            "paper_size": self._normalize_paper_size(config.get("paper_size")),
            "margin": self._normalize_margin(config.get("margin")),
            "toc": bool(config.get("toc")),
            "metadata_title": str(config.get("metadata_title") or "").strip(),
            "timeout_sec": self._normalize_timeout(config.get("timeout_sec")),
        }

    def _template_replacements(self, config: dict[str, Any]) -> dict[str, str]:
        """Build escaped template replacements for block-owned HTML."""

        return {
            "output_path": escape(config["output_path"], quote=True),
            "from_format": escape(config["from_format"], quote=True),
            "paper_size": escape(config["paper_size"], quote=True),
            "paper_size_a4_selected": "selected" if config["paper_size"] == "a4" else "",
            "paper_size_letter_selected": "selected" if config["paper_size"] == "letter" else "",
            "paper_size_a3_selected": "selected" if config["paper_size"] == "a3" else "",
            "margin": escape(config["margin"], quote=True),
            "toc_checked": "checked" if config["toc"] else "",
            "metadata_title": escape(config["metadata_title"], quote=True),
            "timeout_sec": str(config["timeout_sec"]),
        }

    def _runtime_markdown(self, context: BlockRuntimeContext) -> str:
        """Read Markdown from named inputs with compatibility fallbacks."""

        for key in ("markdown", "content", "contenu", "in", "1"):
            value = context.input_value(key)
            if value is not None and str(value).strip():
                return str(value)
        return str(context.input_message or "")

    def _pandoc_command(
        self,
        *,
        pandoc_binary: str,
        markdown_path: Path,
        output_path: Path,
        config: dict[str, Any],
    ) -> list[str]:
        """Build the Pandoc CLI command from normalized block config."""

        command = [
            pandoc_binary,
            str(markdown_path),
            "--from",
            config["from_format"],
            "--output",
            str(output_path),
            "--standalone",
            "-V",
            f"papersize:{config['paper_size']}",
            "-V",
            f"geometry:margin={config['margin']}",
        ]
        if config["toc"]:
            command.append("--toc")
        if config["metadata_title"]:
            command.extend(["--metadata", f"title={config['metadata_title']}"])
        return command

    def _write_temp_markdown(self, directory: Path, markdown: str) -> Path:
        """Write Markdown to a temporary UTF-8 file consumed by Pandoc."""

        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            suffix=".md",
            prefix=".markdown_pdf_",
            dir=directory,
            delete=False,
        ) as handle:
            handle.write(markdown)
            return Path(handle.name)

    def _resolve_output_path(self, root_dir: Path, raw_output_path: str) -> Path:
        """Resolve a configured output path inside the project directory."""

        root = Path(root_dir).resolve()
        cleaned = self._normalize_output_path(raw_output_path)
        candidate = Path(os.path.expanduser(cleaned))
        if not candidate.is_absolute():
            candidate = root / candidate
        resolved = candidate.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise MarkdownPdfBlockError("The PDF path must stay inside the project directory.") from exc
        if resolved.name in {"", ".", ".."}:
            raise MarkdownPdfBlockError(self.translate("block.markdown_pdf.error_path_without_name",
                fallback="The PDF path must contain a file name."))
        if resolved.suffix.lower() != ".pdf":
            resolved = resolved.with_suffix(".pdf")
        return resolved

    def _normalize_output_path(self, value: Any) -> str:
        """Return a non-empty project-relative PDF path."""

        text = str(value or "").strip().replace("\\", "/")
        return text or DEFAULT_OUTPUT_PATH

    def _normalize_from_format(self, value: Any) -> str:
        """Return the Pandoc input format identifier."""

        text = str(value or "").strip()
        return text or DEFAULT_FROM_FORMAT

    def _normalize_paper_size(self, value: Any) -> str:
        """Return a supported Pandoc paper size."""

        text = str(value or "").strip().lower()
        return text if text in {"a3", "a4", "letter"} else DEFAULT_PAPER_SIZE

    def _normalize_margin(self, value: Any) -> str:
        """Return a compact Pandoc geometry margin value."""

        text = str(value or "").strip()
        return text or DEFAULT_MARGIN

    def _normalize_timeout(self, value: Any) -> int:
        """Clamp the Pandoc timeout to a reasonable positive integer."""

        try:
            timeout = int(value)
        except (TypeError, ValueError):
            timeout = DEFAULT_TIMEOUT_SEC
        return max(1, min(MAX_TIMEOUT_SEC, timeout))

    def _relative_path(self, root_dir: Path, path: Path) -> str:
        """Return a stable display path relative to the project root when possible."""

        try:
            return str(path.resolve().relative_to(Path(root_dir).resolve()))
        except ValueError:
            return str(path)

    def _failed(
        self,
        error: str,
        logs: list[str],
        *,
        exit_code: int = 1,
        metadata: dict[str, Any] | None = None,
    ) -> BlockRuntimeResult:
        """Build a failed runtime result with consistent metadata."""

        return BlockRuntimeResult(
            status="failed",
            outputs=[
                BlockRuntimeOutput(
                    port_id=1,
                    port_name="pdf",
                    value="",
                    content_type=FILE_PATH,
                    status="failed",
                    exit_code=exit_code,
                    emitted=False,
                    metadata=metadata or {},
                )
            ],
            logs=logs,
            error=error,
            exit_code=exit_code,
            last_message=error,
            content_type=TEXT_PLAIN,
            worker_received=error,
            metadata=metadata or {},
        )


__all__ = ["MarkdownPdfBlock", "MarkdownPdfBlockError", "PDF_CONTENT_TYPE", "TEXT_MARKDOWN"]
