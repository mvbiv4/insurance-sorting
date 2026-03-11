"""Tesseract OCR wrapper with image preprocessing for scanned requisitions."""

import logging
import shutil
import sys
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image
import pytesseract

log = logging.getLogger(__name__)

# Auto-detect Tesseract on Windows — check PATH first, then common install locations
_tesseract_found = shutil.which("tesseract")
if _tesseract_found:
    pytesseract.pytesseract.tesseract_cmd = _tesseract_found
else:
    _TESSERACT_PATHS = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    for p in _TESSERACT_PATHS:
        if Path(p).exists():
            pytesseract.pytesseract.tesseract_cmd = p
            break
    else:
        log.warning(
            "Tesseract not found in PATH or standard locations. "
            "OCR will fail. Install Tesseract-OCR and ensure it's in PATH or "
            "installed to 'C:\\Program Files\\Tesseract-OCR\\'."
        )


def _normalize_dpi(img: np.ndarray, target_dpi: int = 300) -> np.ndarray:
    """Upscale low-DPI images (faxes are typically 200 DPI) to target DPI."""
    h, w = img.shape[:2]
    # Heuristic: US Letter at 200 DPI is ~1700x2200, at 300 DPI is ~2550x3300
    if w < 2000 and h < 2800:
        scale = 1.5  # assume 200 DPI, scale to ~300
        new_w, new_h = int(w * scale), int(h * scale)
        return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
    return img


def preprocess_image(img: np.ndarray) -> np.ndarray:
    """Deskew, denoise, and enhance contrast for better OCR on faxed/scanned docs."""
    if img is None or img.size == 0:
        raise ValueError("Empty or invalid image data")

    img = _normalize_dpi(img)

    # Convert to grayscale if needed
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img.copy()

    # Denoise
    denoised = cv2.medianBlur(gray, 3)

    # Adaptive threshold for better contrast on faxed docs
    binary = cv2.adaptiveThreshold(
        denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 10
    )

    # Repair broken characters and remove speckle noise
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)

    # Deskew — only for small angles (skip if image is rotated 90°+)
    coords = np.column_stack(np.where(binary < 128))
    if len(coords) > 100:
        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
        if abs(angle) > 0.5 and abs(angle) < 15:
            h, w = binary.shape
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            binary = cv2.warpAffine(
                binary, M, (w, h), flags=cv2.INTER_CUBIC, borderValue=255
            )

    # Prevent edge artifacts from confusing Tesseract page segmentation
    binary = cv2.copyMakeBorder(binary, 10, 10, 10, 10, cv2.BORDER_CONSTANT, value=255)

    return binary


def _read_image_cv2(filepath: Path) -> np.ndarray:
    """Read image with OpenCV, handling non-ASCII paths on Windows."""
    # cv2.imread fails on non-ASCII paths on Windows — use numpy workaround
    try:
        img = cv2.imread(str(filepath))
        if img is not None:
            return img
    except Exception:
        pass

    # Fallback: read via numpy buffer for non-ASCII path support
    try:
        buf = np.fromfile(str(filepath), dtype=np.uint8)
        img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        if img is not None:
            return img
    except Exception:
        pass

    raise ValueError(f"Could not read image: {filepath}")


def load_image(filepath: Path) -> list[np.ndarray]:
    """Load image or PDF pages as numpy arrays."""
    suffix = filepath.suffix.lower()

    if suffix == ".pdf":
        try:
            from pdf2image import convert_from_path
            pages = convert_from_path(str(filepath), dpi=300)
            return [np.array(page) for page in pages]
        except ImportError:
            log.warning("pdf2image not installed — falling back to Pillow for PDF (limited support)")
        except Exception as e:
            raise ValueError(f"Failed to convert PDF '{filepath.name}': {e}") from e

        # Pillow fallback for simple PDFs
        try:
            with Image.open(filepath) as img:
                frames = []
                try:
                    while True:
                        frames.append(np.array(img.convert("RGB")))
                        img.seek(img.tell() + 1)
                except EOFError:
                    pass
                if not frames:
                    frames.append(np.array(img.convert("RGB")))
                return frames
        except Exception as e:
            raise ValueError(f"Failed to open PDF '{filepath.name}' with Pillow: {e}") from e

    elif suffix in (".tif", ".tiff"):
        try:
            with Image.open(filepath) as img:
                frames = []
                try:
                    while True:
                        frames.append(np.array(img.convert("RGB")))
                        img.seek(img.tell() + 1)
                except EOFError:
                    pass
                return frames if frames else [np.array(img.convert("RGB"))]
        except Exception as e:
            raise ValueError(f"Failed to open TIFF '{filepath.name}': {e}") from e

    else:
        return [_read_image_cv2(filepath)]


def extract_text(filepath: Path, preprocess: bool = True) -> str:
    """Run OCR on an image/PDF file and return extracted text."""
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    pages = load_image(filepath)
    if not pages:
        raise ValueError(f"No pages extracted from: {filepath}")

    all_text = []
    for i, page_img in enumerate(pages):
        try:
            if preprocess:
                processed = preprocess_image(page_img)
            else:
                processed = page_img

            config = "--oem 3 --psm 3 --dpi 300"
            text = pytesseract.image_to_string(processed, config=config)

            if not text or not text.strip():
                log.warning(f"OCR returned empty text for page {i+1} of {filepath.name}")

            all_text.append(text)
        except pytesseract.TesseractNotFoundError:
            raise RuntimeError(
                "Tesseract OCR is not installed or not in PATH. "
                "Install from: https://github.com/UB-Mannheim/tesseract/wiki"
            )
        except Exception as e:
            log.error(f"OCR failed on page {i+1} of {filepath.name}: {e}")
            all_text.append(f"[OCR ERROR on page {i+1}: {e}]")

    return "\n--- PAGE BREAK ---\n".join(all_text)


# OCR quality thresholds
OCR_QUALITY_GOOD = 78       # Above this = good scan
OCR_QUALITY_POOR = 40       # Below this = poor scan, likely unreadable
# Between 40-78 = fair (may have errors)


def assess_ocr_quality(filepath: Path, preprocess: bool = True) -> dict:
    """Run OCR with confidence data and return text + quality assessment.

    Returns dict with:
        text: str — extracted text
        quality_score: float — 0-100, average word confidence
        word_count: int — total words detected
        low_confidence_words: int — words below 60% confidence
        quality_label: str — 'good', 'fair', 'poor', 'unreadable'
        quality_details: str — human-readable quality summary
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    pages = load_image(filepath)
    if not pages:
        raise ValueError(f"No pages extracted from: {filepath}")

    all_text = []
    all_confidences = []
    total_words = 0
    low_conf_words = 0
    page_errors = 0

    for i, page_img in enumerate(pages):
        try:
            if preprocess:
                processed = preprocess_image(page_img)
            else:
                processed = page_img

            config = "--oem 3 --psm 3 --dpi 300"

            # Get per-word confidence data (single Tesseract call)
            data = pytesseract.image_to_data(processed, config=config, output_type=pytesseract.Output.DICT)

            # Reconstruct text from data dict preserving line breaks
            current_block = -1
            current_line = -1
            page_lines = []
            current_line_words = []
            for j in range(len(data["text"])):
                block_num = data["block_num"][j]
                line_num = data["line_num"][j]
                word = data["text"][j].strip()
                conf = int(data["conf"][j])

                if block_num != current_block or line_num != current_line:
                    if current_line_words:
                        page_lines.append(" ".join(current_line_words))
                    current_line_words = []
                    if block_num != current_block and current_block != -1:
                        page_lines.append("")  # paragraph break between blocks
                    current_block = block_num
                    current_line = line_num

                if word and conf >= 0:
                    current_line_words.append(word)
                    all_confidences.append(conf)
                    total_words += 1
                    if conf < 60:
                        low_conf_words += 1

            if current_line_words:
                page_lines.append(" ".join(current_line_words))

            full_text = "\n".join(page_lines)
            all_text.append(full_text)

            if not full_text.strip():
                log.warning(f"OCR returned no words for page {i+1} of {filepath.name}")

        except pytesseract.TesseractNotFoundError:
            raise RuntimeError(
                "Tesseract OCR is not installed or not in PATH. "
                "Install from: https://github.com/UB-Mannheim/tesseract/wiki"
            )
        except Exception as e:
            log.error(f"OCR failed on page {i+1} of {filepath.name}: {e}")
            all_text.append(f"[OCR ERROR on page {i+1}: {e}]")
            page_errors += 1

    # Calculate quality score
    if all_confidences:
        quality_score = sum(all_confidences) / len(all_confidences)
    elif page_errors > 0:
        quality_score = 0.0
    else:
        quality_score = 0.0

    # Determine quality label
    if total_words == 0:
        quality_label = "unreadable"
        quality_details = "No text could be extracted from the scan"
    elif quality_score >= OCR_QUALITY_GOOD:
        quality_label = "good"
        quality_details = f"Scan quality good ({quality_score:.0f}% avg confidence, {total_words} words)"
    elif quality_score >= OCR_QUALITY_POOR:
        quality_label = "fair"
        quality_details = (
            f"Scan quality fair ({quality_score:.0f}% avg confidence, "
            f"{low_conf_words}/{total_words} words uncertain) — verify extracted data"
        )
    else:
        quality_label = "poor"
        quality_details = (
            f"POOR SCAN QUALITY ({quality_score:.0f}% avg confidence, "
            f"{low_conf_words}/{total_words} words uncertain) — manual review required"
        )

    if page_errors > 0:
        quality_details += f" [{page_errors} page(s) failed to process]"

    combined_text = "\n--- PAGE BREAK ---\n".join(all_text)

    return {
        "text": combined_text,
        "quality_score": round(quality_score, 1),
        "word_count": total_words,
        "low_confidence_words": low_conf_words,
        "quality_label": quality_label,
        "quality_details": quality_details,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ocr.py <image_or_pdf_path>")
        sys.exit(1)
    result = assess_ocr_quality(Path(sys.argv[1]))
    print(f"Quality: {result['quality_label']} ({result['quality_score']}%)")
    print(f"Words: {result['word_count']} ({result['low_confidence_words']} low confidence)")
    print(f"Details: {result['quality_details']}")
    print(f"\n--- Extracted Text ---\n{result['text']}")
