from app.domains.folder_analysis.domain.ports.server_reading_port import ServerReadingPort


class FolioExtractionPort(ServerReadingPort):
    """Reads a folio real from its photos with OCR and rules, without the vision
    model. Takes seconds per photo, so it never runs inside a request."""
