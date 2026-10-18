"""Render distributed PDFs for visual review using optional tools in excluded tmp/."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tmp/pdf-review-tools"))
import pypdfium2 as pdfium
from PIL import Image, ImageDraw

FILES = ("slides/pitch.pdf", "docs/architecture.pdf", "docs/security-assessment.pdf",
         "docs/submission-notes.pdf", "docs/Tideway_FinTechathon_2026_Roadmap.pdf")


def main():
    out = Path(__file__).parent / "pdf-review"
    out.mkdir(exist_ok=True)
    records = []
    for name in FILES:
        path = ROOT / name
        document = pdfium.PdfDocument(path)
        pages = []
        for index in range(len(document)):
            page = document[index]
            width, height = page.get_size()
            textpage = page.get_textpage()
            text = textpage.get_text_bounded()
            thumbnail = page.render(scale=380 / width).to_pil().convert("RGB")
            pages.append((index, thumbnail))
            if not text.strip():
                raise RuntimeError(f"Empty PDF text: {name} page {index + 1}")
            textpage.close()
            page.close()
        sheets = []
        for offset in range(0, len(pages), 9):
            group = pages[offset:offset + 9]
            cell_height = max(im.height for _, im in group) + 30
            sheet = Image.new("RGB", (1200, ((len(group) + 2) // 3) * cell_height), "#dce4e2")
            draw = ImageDraw.Draw(sheet)
            for pos, (index, im) in enumerate(group):
                x, y = (pos % 3) * 400 + 10, (pos // 3) * cell_height
                draw.text((x, y + 4), f"{path.stem} - page {index + 1}", fill="black")
                sheet.paste(im, (x, y + 24))
            destination = out / f"{path.stem}-{offset // 9 + 1}.png"
            sheet.save(destination)
            sheets.append(destination.relative_to(ROOT).as_posix())
        records.append({"file": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "pages": len(document), "all_pages_have_text": True,
                        "all_pages_rendered": True, "contact_sheets": sheets})
        document.close()
        print(f"{name}: {len(pages)} pages rendered")
    report = {"renderer": "pypdfium2", "tool_scope": "Optional temporary PDF review tools; not runtime or ZIP dependencies",
              "visual_inspection_completed": False, "pdfs": records}
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
