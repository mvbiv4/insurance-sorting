"""Generate a sample scanned requisition image for testing the OCR pipeline."""

from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

SAMPLE_DIR = Path(__file__).parent.parent / "sample_reqs"


def create_sample_req(filename: str, insurance_name: str, member_id: str, group: str = "GRP001"):
    """Create a fake requisition form image with the given insurance info."""
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)

    img = Image.new("RGB", (800, 600), "white")
    draw = ImageDraw.Draw(img)

    # Use default font (no external font needed)
    try:
        font = ImageFont.truetype("arial.ttf", 18)
        font_bold = ImageFont.truetype("arialbd.ttf", 22)
    except (OSError, IOError):
        font = ImageFont.load_default()
        font_bold = font

    y = 30
    draw.text((50, y), "CAROLINA PATHOLOGY GROUP", fill="black", font=font_bold)
    y += 40
    draw.text((50, y), "Patient Requisition Form", fill="black", font=font)
    y += 40
    draw.line([(50, y), (750, y)], fill="black", width=2)
    y += 20

    draw.text((50, y), "Patient Name: DOE, JOHN", fill="black", font=font)
    y += 30
    draw.text((50, y), "DOB: 01/15/1980", fill="black", font=font)
    y += 30
    draw.text((50, y), "Phone: (704) 555-1234", fill="black", font=font)
    y += 40

    draw.line([(50, y), (750, y)], fill="black", width=2)
    y += 20
    draw.text((50, y), "INSURANCE INFORMATION", fill="black", font=font_bold)
    y += 35
    draw.text((50, y), f"Insurance: {insurance_name}", fill="black", font=font)
    y += 30
    draw.text((50, y), f"Member ID: {member_id}", fill="black", font=font)
    y += 30
    draw.text((50, y), f"Group #: {group}", fill="black", font=font)
    y += 40

    draw.line([(50, y), (750, y)], fill="black", width=2)
    y += 20
    draw.text((50, y), "Ordering Physician: DR. SMITH", fill="black", font=font)
    y += 30
    draw.text((50, y), "Tests Ordered: CBC, BMP, Lipid Panel", fill="black", font=font)

    path = SAMPLE_DIR / filename
    img.save(str(path))
    print(f"Created: {path}")
    return path


if __name__ == "__main__":
    # Flagged case: BCBS-NC (on blocklist)
    create_sample_req(
        "sample_flagged_bcbs.png",
        "Blue Cross Blue Shield of NC",
        "YMM123456789",
        "GRP5678",
    )

    # Clear case: not on blocklist
    create_sample_req(
        "sample_clear_labcorp.png",
        "LabCorp Internal Health Plan",
        "LC998877",
        "GRP1111",
    )

    # Fuzzy match case: OCR-garbled name
    create_sample_req(
        "sample_fuzzy_aetna.png",
        "Aetno",  # Simulated OCR error
        "W99887766",
        "GRP2222",
    )

    print("\nSample requisitions created in sample_reqs/")
