class AlignmentDomainException(Exception):
    pass


class AlignmentBlockNotFound(AlignmentDomainException):
    def __init__(self, block_id: int):
        detail = f"alignment_block {block_id} no encontrado."
        super().__init__(detail)
        self.detail = detail


class InvalidControlPoints(AlignmentDomainException):
    """Fewer than 3 control points, or 3+ points that are collinear/degenerate
    (no unique affine transform can be fit through them)."""

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail
