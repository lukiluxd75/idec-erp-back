from abc import ABC, abstractmethod


class DocumentReaderPort(ABC):
    """Port over OCR text extraction (Tesseract + OpenCV, see
    infrastructure/ocr/tesseract_document_reader.py), used by the ingestion
    pipeline before the LLM structures the raw text into a procedure."""

    @abstractmethod
    def extract_text(self, image_bytes: bytes) -> str:
        """Raw Spanish text read from a scanned document image. Empty string if
        nothing could be read."""
