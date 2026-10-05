"""FB3/FB5: conversion failure cannot replace or truncate the previous document."""

from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from blocs.markdown_pdf.block import MarkdownPdfBlock
from bloxsmith_app.block_api import BlockRuntimeContext


def main():
    block = MarkdownPdfBlock()
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        output = root / "report.pdf"
        previous = b"%PDF-1.4\nprevious complete report\n%%EOF\n"
        context = BlockRuntimeContext(node_id="pdf", root_dir=root,
            config={"output_path": "report.pdf"}, input_message="# Report",
            output_ports=(SimpleNamespace(id=1, name="pdf"),))

        def fake(code=0, data=b"%PDF-1.4\nnext complete report\n%%EOF\n", timeout=False):
            def run(argv, **kwargs):
                target = Path(argv[argv.index("--output") + 1])
                assert target != output and target.parent.parent == root
                assert output.read_bytes() == previous
                target.write_bytes(data)
                if timeout:
                    raise subprocess.TimeoutExpired(argv, 1)
                return subprocess.CompletedProcess(argv, code, "", "")
            return run

        cases = [(fake(code=2, data=b"partial"), {}, "pandoc_failed"),
                 (fake(data=b"not a PDF"), {}, "missing_pdf"),
                 (fake(timeout=True), {}, "timeout"),
                 (fake(), {"cancel_requested": lambda: True}, "cancelled")]
        for command, services, reason in cases:
            output.write_bytes(previous)
            context.services = services
            with patch("blocs.markdown_pdf.block.shutil.which", return_value="pandoc"), patch(
                    "blocs.markdown_pdf.block.subprocess.run", side_effect=command):
                result = block.execute_runtime(context)
            assert result.status == "failed" and not any(item.emitted for item in result.outputs)
            assert result.metadata["reason"] == reason, result.metadata
            assert output.read_bytes() == previous
            assert not list(root.glob(".markdown_pdf*"))
        context.services = {}
        with patch("blocs.markdown_pdf.block.shutil.which", return_value="pandoc"), patch(
                "blocs.markdown_pdf.block.subprocess.run", side_effect=fake()):
            result = block.execute_runtime(context)
        assert result.status == "success" and result.outputs[0].value == str(output)
        assert b"next complete" in output.read_bytes() and output.stat().st_mode & 0o777 == 0o600
        assert not list(root.glob(".markdown_pdf*"))
    print("[ok] Markdown PDF atomic publication and preservation on all conversion failures")


if __name__ == "__main__":
    main()
