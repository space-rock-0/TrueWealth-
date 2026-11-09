"""Bounded CPU OCR; page images are never sent to an AI provider."""
import threading
import os
import json
import subprocess
import sys

_lock = threading.Lock()
_engine = None


def extract_pages(raw, texts):
    """Render only pages missing searchable text, limiting OCR resource use."""
    missing = [i for i, text in enumerate(texts) if len(text.strip()) < 30]
    if not missing:
        return texts
    maximum = int(os.getenv('OCR_MAX_PAGES', '20'))
    if len(missing) > maximum:
        raise ValueError(f'Split scanned PDFs into files containing at most {maximum} scanned pages.')
    if os.getenv('OCR_ISOLATED', 'false').lower() == 'true':
        env = dict(os.environ, OCR_ISOLATED='false')
        try:
            result = subprocess.run([sys.executable, '-m', 'app.tools.statement_ocr_worker'], input=raw, capture_output=True, timeout=120, env=env)
        except subprocess.TimeoutExpired:
            raise ValueError('OCR timed out. Upload fewer scanned pages or a bank CSV export.') from None
        if result.returncode != 0:
            raise ValueError('OCR could not process this scan. Try a smaller PDF or clearer image.')
        return json.loads(result.stdout)
    import numpy as np
    import pypdfium2 as pdfium
    from rapidocr_onnxruntime import RapidOCR
    global _engine
    with _lock:
        if _engine is None:
            _engine = RapidOCR()
        pdf = pdfium.PdfDocument(raw)
        try:
            for index in missing:
                page = pdf[index]
                width, height = page.get_size()
                scale = min(2.5, int(os.getenv('OCR_MAX_IMAGE_EDGE', '2500')) / max(width, height))
                bitmap = page.render(scale=scale)
                try:
                    result, _ = _engine(np.asarray(bitmap.to_pil()).copy())
                    texts[index] = '\n'.join(row[1] for row in (result or []))
                finally:
                    bitmap.close()
                    page.close()
        finally:
            pdf.close()
    return texts
