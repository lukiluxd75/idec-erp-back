from typing import Optional

import cv2
import numpy as np
import pytesseract

from app.core.config.settings import settings
from app.domains.chatbot.domain.ports.document_reader_port import DocumentReaderPort


class TesseractDocumentReader(DocumentReaderPort):
    """OCR adapter ported from the prototype's OpenCV + Tesseract pipeline
    (decode -> grayscale -> Otsu threshold -> pytesseract). The one fix required
    to run on the ERP's server: the prototype hardcoded a Windows install path
    for tesseract.exe -- here it comes from CHATBOT_TESSERACT_CMD (empty means
    'whatever tesseract resolves to on PATH')."""

    def __init__(self, tesseract_cmd: Optional[str] = None, lang: Optional[str] = None):
        cmd = tesseract_cmd if tesseract_cmd is not None else settings.CHATBOT_TESSERACT_CMD
        if cmd:
            pytesseract.pytesseract.tesseract_cmd = cmd
        self._lang = lang or settings.CHATBOT_TESSERACT_LANG

    def extract_text(self, image_bytes: bytes) -> str:
        buffer = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
        if image is None:
            return ""

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        return pytesseract.image_to_string(thresh, lang=self._lang).strip()
