"""Local OCR smoke check using a generated image; no bank data or paid API."""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw, ImageFont
from app.tools.statement_ocr import extract_pages

image = Image.new('RGB', (1600, 350), 'white')
try:
    font = ImageFont.truetype('arial.ttf', 42)
except OSError:
    font = ImageFont.load_default(size=42)
draw = ImageDraw.Draw(image)
draw.text((50, 60), 'BANK STATEMENT', fill='black', font=font)
draw.text((50, 150), '2026-01-01 SALARY CREDIT USD 1000.00', fill='black', font=font)
buffer = io.BytesIO()
image.save(buffer, format='PDF')
text = extract_pages(buffer.getvalue(), [''])[0]
assert '1000' in text and 'SALARY' in text.upper(), text
print('Scanned PDF OCR: passed (generated statement, no provider API calls).')
