from __future__ import annotations

import json
import platform
import re
import subprocess
from pathlib import Path

import fitz

from .models import PageDiagnostic, Word


PRINTED_PAGE_RE = re.compile(r"(?:第\s*)?(\d+)\s*页")


def _native_words(page: fitz.Page) -> list[Word]:
    return [
        Word(
            text=item[4],
            x0=float(item[0]),
            y0=float(item[1]),
            x1=float(item[2]),
            y1=float(item[3]),
        )
        for item in page.get_text("words", sort=True)
        if item[4].strip()
    ]


def _printed_page(text: str, words: list[Word]) -> str | None:
    matches = PRINTED_PAGE_RE.findall(text)
    if matches:
        return matches[-1]
    edge_numbers = [
        word.text
        for word in words
        if word.text.isdigit()
        and (
            word.x0 < 50
            or word.x1 > max((candidate.x1 for candidate in words), default=0) - 50
        )
    ]
    return edge_numbers[-1] if edge_numbers else None


class MacOSVisionOCR:
    name = "macos-vision"

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.source = project_root / "scripts" / "vision_ocr.swift"
        self.binary = project_root / "artifacts" / "bin" / "vision_ocr"

    def available(self) -> bool:
        return platform.system() == "Darwin" and self.source.exists()

    def _compile(self) -> None:
        self.binary.parent.mkdir(parents=True, exist_ok=True)
        if self.binary.exists() and self.binary.stat().st_mtime >= self.source.stat().st_mtime:
            return
        subprocess.run(
            ["swiftc", str(self.source), "-o", str(self.binary)],
            check=True,
            capture_output=True,
            text=True,
        )

    def extract(self, image_path: Path, page_width: float, page_height: float) -> list[Word]:
        self._compile()
        result = subprocess.run(
            [str(self.binary), str(image_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        output: list[Word] = []
        for item in json.loads(result.stdout):
            output.append(
                Word(
                    text=item["text"],
                    x0=item["x0"] * page_width,
                    y0=item["y0"] * page_height,
                    x1=item["x1"] * page_width,
                    y1=item["y1"] * page_height,
                    confidence=item["confidence"],
                    source=self.name,
                )
            )
        return output


class PDFParser:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.pages_dir = project_root / "artifacts" / "pages"
        self.ocr = MacOSVisionOCR(project_root)

    def parse(self, pdf_path: Path) -> tuple[list[PageDiagnostic], dict[int, list[Word]]]:
        self.pages_dir.mkdir(parents=True, exist_ok=True)
        for old_page in self.pages_dir.glob("page-*.png"):
            old_page.unlink()
        document = fitz.open(pdf_path)
        diagnostics: list[PageDiagnostic] = []
        words_by_page: dict[int, list[Word]] = {}
        for index, page in enumerate(document):
            page_number = index + 1
            text = page.get_text("text")
            native = _native_words(page)
            rect = page.rect
            image_path = self.pages_dir / f"page-{page_number}.png"
            page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5), alpha=False).save(image_path)

            warnings: list[str] = []
            page_type = "native" if len(text.strip()) >= 40 else "scanned"
            parser = "pymupdf"
            words = native
            if page_type == "scanned":
                if self.ocr.available():
                    words = self.ocr.extract(image_path, rect.width, rect.height)
                    parser = self.ocr.name
                else:
                    words = []
                    parser = "unavailable"
                    warnings.append("OCR backend unavailable; scanned page not parsed")
            elif len(page.get_images(full=True)) > 0:
                page_type = "mixed"

            if not words:
                warnings.append("No words extracted")
            low_confidence = sum(word.confidence < 0.6 for word in words)
            if low_confidence:
                warnings.append(f"{low_confidence} low-confidence OCR tokens")

            printed_page = _printed_page(text, words)
            diagnostics.append(
                PageDiagnostic(
                    pdf_page=page_number,
                    printed_page=printed_page,
                    page_type=page_type,
                    parser=parser,
                    orientation="landscape" if rect.width > rect.height else "portrait",
                    width=round(rect.width, 2),
                    height=round(rect.height, 2),
                    native_text_chars=len(text.strip()),
                    image_count=len(page.get_images(full=True)),
                    word_count=len(words),
                    warnings=warnings,
                )
            )
            words_by_page[page_number] = words
        return diagnostics, words_by_page
