from app.domains.folder_analysis.domain.ports.server_reading_port import ServerReadingPort


class TaxExtractionPort(ServerReadingPort):
    """Reads a municipal property tax receipt (FUR) from its photo with OCR and
    the form's rules, without queueing anything to the architects' PCs. Takes
    seconds per photo, so it never runs inside a request."""
