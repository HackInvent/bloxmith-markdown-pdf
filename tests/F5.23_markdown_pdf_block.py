#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# Role: Verifies Markdown PDF block behavior with a fake Pandoc binary.
# File Name: F5.23_markdown_pdf_block.py
# Author: Alexandre EL
# Email: alex@hackinvent.com
# Created Date: 2026-05-19
# -----------------------------------------------------------------------------

# Test cases:
# - FB1 - Render the node-card, inspector, and modal with the default exports/tmp.pdf target.
# - FB2 - Fail clearly when Pandoc is unavailable.
# - FB3 - Generate a PDF path directly with a fake Pandoc executable.
# - FB4 - Execute the block in centralized and zeromq_active runtime modes.

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import os
import shutil
import sys
import tempfile


ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
TESTS_DIR = ROOT_DIR / "tests"
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from blocs import get_block_definition
from bloxsmith_app.block_runtime import BlockRuntimeContext
from ui_smoke_common import create_run_api, data_edge, expect, graph_payload, isolated_server, text_node, wait_for_run_terminal


PDF_BYTES = b"%PDF-1.4\n% fake pandoc output\n"
MARKDOWN_TEXT = "# Titre\n\nUn paragraphe **Markdown**."


@contextmanager
def fake_pandoc_cli() -> Path:
    """Expose a fake Pandoc executable in PATH for deterministic tests."""

    temp_dir = Path(tempfile.mkdtemp(prefix="bloxsmith-fake-pandoc-"))
    pandoc_path = temp_dir / "pandoc"
    pandoc_path.write_text(
        """#!/usr/bin/env python3
from pathlib import Path
import sys

args = sys.argv[1:]
if "--output" not in args:
    sys.exit(2)
output_path = Path(args[args.index("--output") + 1])
output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_bytes(b"%PDF-1.4\\n% fake pandoc output\\n")
sys.exit(0)
""",
        encoding="utf-8",
    )
    pandoc_path.chmod(0o755)
    old_path = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{temp_dir}{os.pathsep}{old_path}"
    try:
        yield pandoc_path
    finally:
        os.environ["PATH"] = old_path
        shutil.rmtree(temp_dir, ignore_errors=True)


@contextmanager
def no_pandoc_cli() -> None:
    """Temporarily hide Pandoc from PATH."""

    old_path = os.environ.get("PATH", "")
    os.environ["PATH"] = ""
    try:
        yield
    finally:
        os.environ["PATH"] = old_path


def runtime_context(root_dir: Path, *, output_path: str = "exports/tmp.pdf") -> BlockRuntimeContext:
    """Build a direct runtime context for the Markdown PDF block."""

    return BlockRuntimeContext(
        run_id="run-markdown-pdf-test",
        node_id="markdown-pdf-1",
        kind="markdown_pdf",
        title="Markdown PDF",
        config={"output_path": output_path, "paper_size": "a4", "margin": "20mm", "timeout_sec": 20},
        inputs={"markdown": MARKDOWN_TEXT},
        input_content_types={"markdown": "text/markdown"},
        input_message=MARKDOWN_TEXT,
        input_ports=(SimpleNamespace(id=1, name="markdown"),),
        output_ports=(SimpleNamespace(id=1, name="pdf"),),
        root_dir=root_dir,
    )


def markdown_pdf_document(*, output_path: str) -> dict:
    """Return a minimal graph that converts text Markdown into PDF."""

    markdown_pdf = {
        "id": "markdown-pdf-1",
        "kind": "markdown_pdf",
        "title": "Markdown PDF",
        "position": {"x": 360, "y": 120},
        "inputs": [
            {
                "id": 1,
                "name": "markdown",
                "title": "Markdown",
                "accepts": ["text/markdown", "text/plain", "message/*"],
                "multiplicity": "many",
            }
        ],
        "outputs": [
            {
                "id": 1,
                "name": "pdf",
                "title": "PDF",
                "emits": ["file/path", "application/pdf", "message/*"],
                "multiplicity": "many",
            }
        ],
        "config": {
            "output_path": output_path,
            "from_format": "markdown",
            "paper_size": "a4",
            "margin": "20mm",
            "toc": False,
            "metadata_title": "Test PDF",
            "timeout_sec": 20,
        },
    }
    return graph_payload(
        "Markdown PDF runtime",
        [
            text_node("text-1", "Markdown source", MARKDOWN_TEXT, 80, 120),
            markdown_pdf,
        ],
        [data_edge("edge-text-pdf", "text-1", 1, "markdown-pdf-1", 1)],
    )


def main() -> None:
    block = get_block_definition("markdown_pdf")
    node = block.build_node_payload(node_id="markdown-pdf-ui")
    expect(node["config"]["output_path"] == "exports/tmp.pdf", "La sortie PDF par defaut doit etre exports/tmp.pdf.")

    card = block.render_node_card(node=node)
    expect("exports/tmp.pdf" in card["html"], "La node-card doit afficher le chemin PDF.")
    mini_card = block.render_mini_node_card(node=node)
    expect("data-markdown-pdf-mini-card" in mini_card["html"], "La mini-card Markdown PDF doit venir du bloc.")
    expect("Toucher pour visualiser" in mini_card["html"], "La mini-card doit exposer l'action compacte de visualisation.")
    inspector = block.render_inspector_panel(node=node)
    expect('data-block-config-field="output_path"' in inspector["html"], "L'inspector doit editer output_path.")
    expect('data-block-config-field="toc"' in inspector["html"], "L'inspector doit editer le sommaire.")
    modal = block.render_modal(node=node)
    modal_assets = {(asset.get("kind"), asset.get("path")) for asset in block.ui_assets("modal")}
    expect("exports/tmp.pdf" in modal["html"], "Le modal doit afficher le chemin par defaut.")
    expect('data-block-runtime-refresh="autonomous"' in modal["html"], "Le modal Markdown PDF doit gérer son refresh runtime.")
    expect('data-block-config-field="paper_size"' in modal["html"], "Le modal doit editer le papier.")
    expect(("js", "assets/js/block_modal.js") in modal_assets, "Le modal Markdown PDF doit declarer son JS block-owned.")

    with tempfile.TemporaryDirectory() as tmp_dir:
        root_dir = Path(tmp_dir)
        with no_pandoc_cli():
            missing = block.execute_runtime(runtime_context(root_dir))
        expect(missing.status == "failed", "Sans pandoc, le bloc doit echouer proprement.")
        expect("Pandoc est requis" in missing.error, "L'erreur doit mentionner la dependance Pandoc.")

        with fake_pandoc_cli():
            result = block.execute_runtime(runtime_context(root_dir))
        expect(result.status == "success", "Avec pandoc, le bloc doit produire un PDF.")
        expect(result.outputs and result.outputs[0].content_type == "file/path", "La sortie doit etre un chemin de fichier.")
        expect((root_dir / "exports/tmp.pdf").read_bytes() == PDF_BYTES, "Le PDF doit etre ecrit au chemin par defaut.")

    with fake_pandoc_cli():
        with isolated_server() as server:
            for runtime_mode in ("centralized", "zeromq_active"):
                output_path = f"exports/{runtime_mode}-tmp.pdf"
                created = create_run_api(server, markdown_pdf_document(output_path=output_path), runtime_mode=runtime_mode)
                run = wait_for_run_terminal(server, str(created.get("run_id") or ""), timeout_sec=20)
                expect(run.get("status") == "success", f"Le run Markdown PDF doit reussir en {runtime_mode}.")
                generated = server.root_dir / output_path
                expect(generated.read_bytes() == PDF_BYTES, f"Le PDF doit etre genere en {runtime_mode}.")


if __name__ == "__main__":
    main()
