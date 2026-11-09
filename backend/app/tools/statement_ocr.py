"""Bounded CPU OCR; page images are never sent to an AI provider."""
import threading
import os
import json
import subprocess
import sys
import io

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
            with _lock:
                result = subprocess.run([sys.executable, '-m', 'app.tools.statement_ocr_worker'], input=raw, capture_output=True, timeout=120, env=env)
        except subprocess.TimeoutExpired:
            raise ValueError('OCR timed out. Upload fewer scanned pages or a bank CSV export.') from None
        if result.returncode != 0:
            raise ValueError('OCR could not process this scan. Try a smaller PDF or clearer image.')
        return json.loads(result.stdout)
    import pypdfium2 as pdfium
    engine_name = os.getenv('OCR_ENGINE', 'rapidocr')
    if engine_name != 'tesseract':
        import numpy as np
        from rapidocr_onnxruntime import RapidOCR
    global _engine
    with _lock:
        if engine_name != 'tesseract' and _engine is None:
            _engine = RapidOCR()
        pdf = pdfium.PdfDocument(raw)
        try:
            for index in missing:
                page = pdf[index]
                width, height = page.get_size()
                scale = min(2.5, int(os.getenv('OCR_MAX_IMAGE_EDGE', '2500')) / max(width, height))
                bitmap = page.render(scale=scale)
                try:
                    if engine_name == 'tesseract':
                        image = io.BytesIO()
                        bitmap.to_pil().save(image, format='PNG')
                        result = subprocess.run(['tesseract', 'stdin', 'stdout', '-l', 'eng', '--psm', '6'], input=image.getvalue(), capture_output=True, timeout=45)
                        if result.returncode != 0:
                            raise ValueError('Server OCR could not read this page. Try a clearer scan or a CSV export.')
                        texts[index] = result.stdout.decode('utf-8', errors='replace')
                    else:
                        result, _ = _engine(np.asarray(bitmap.to_pil()).copy())
                        texts[index] = '\n'.join(row[1] for row in (result or []))
                finally:
                    bitmap.close()
                    page.close()
        finally:
            pdf.close()
    return texts
