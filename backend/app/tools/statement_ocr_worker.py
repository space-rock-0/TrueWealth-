"""Isolated OCR process: input PDF on stdin, extracted page text on stdout."""
import io
import json
import sys
from pypdf import PdfReader
from app.tools.statement_ocr import extract_pages


def main():
    raw = sys.stdin.buffer.read(10 * 1024 * 1024 + 1)
    if len(raw) > 10 * 1024 * 1024:
        raise ValueError('File exceeds OCR upload limit.')
    texts = [page.extract_text() or '' for page in PdfReader(io.BytesIO(raw)).pages]
    print(json.dumps(extract_pages(raw, texts)), flush=True)


if __name__ == '__main__':
    main()
