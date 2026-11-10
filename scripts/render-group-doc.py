"""Render the root group-meeting Markdown to DOCX and PDF via LibreOffice."""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "组会汇报-科研智能体进展与下一步.md"

HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<style>
@page { size: A4; margin: 16mm 15mm 16mm 15mm; }
body { font-family: "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
       font-size: 10.2pt; line-height: 1.62; color: #1f2937; }
h1 { font-size: 19pt; line-height: 1.3; margin: 0 0 10pt; color: #0f172a; }
h2 { font-size: 14pt; margin: 16pt 0 7pt; padding-bottom: 3pt;
     border-bottom: 1px solid #cbd5e1; color: #0f172a; page-break-after: avoid; }
h3 { font-size: 11.5pt; margin: 12pt 0 5pt; color: #1e3a5f; page-break-after: avoid; }
p { margin: 4pt 0; }
ul, ol { margin: 4pt 0 4pt 16pt; padding: 0; }
li { margin: 2pt 0; }
table { border-collapse: collapse; width: 100%; margin: 7pt 0 10pt;
        font-size: 8.8pt; page-break-inside: auto; }
th, td { border: 1px solid #cbd5e1; padding: 4pt 5pt; vertical-align: top; }
th { background: #eef4fb; font-weight: 600; }
tr { page-break-inside: avoid; }
blockquote { margin: 7pt 0; padding: 4pt 10pt; border-left: 3px solid #94a3b8;
             color: #475569; background: #f8fafc; }
code { font-family: Consolas, "Courier New", monospace; font-size: 8.8pt;
       background: #f1f5f9; padding: 1pt 3pt; }
pre { background: #f1f5f9; padding: 7pt; white-space: pre-wrap; }
hr { border: 0; border-top: 1px solid #e2e8f0; margin: 10pt 0; }
strong { color: #0f172a; }
</style></head><body>__BODY__</body></html>"""


def main() -> int:
    body = markdown.markdown(
        SOURCE.read_text(encoding="utf-8"),
        extensions=["tables", "fenced_code", "sane_lists", "nl2br"],
    )
    tmp = Path(tempfile.mkdtemp(prefix="groupdoc-"))
    html_path = tmp / "report.html"
    html_path.write_text(HTML.replace("__BODY__", body), encoding="utf-8")
    profile = tmp / "lo-profile"
    for fmt in ("docx:MS Word 2007 XML", "pdf:writer_pdf_Export"):
        command = [
            "soffice", "--headless", "--norestore",
            "-env:UserInstallation=file:///" + profile.as_posix(),
            "--convert-to", fmt, "--outdir", tmp.as_posix(), html_path.as_posix(),
        ]
        result = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=180,
        )
        if result.returncode != 0:
            print(result.stdout)
            print(result.stderr)
            return result.returncode
    for name in ("report.docx", "report.pdf"):
        generated = tmp / name
        if not generated.is_file():
            raise SystemExit("missing output: " + name)
        target = ROOT / ("组会汇报-科研智能体进展与下一步" + generated.suffix)
        shutil.copyfile(str(generated), str(target))
    print("rendered:", tmp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
