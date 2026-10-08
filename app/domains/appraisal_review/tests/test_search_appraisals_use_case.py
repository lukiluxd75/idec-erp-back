from app.domains.appraisal_review.application.use_cases.search_appraisals_use_case import (
    SearchAppraisalsUseCase,
)


class FakeOperativoRepository:
    def __init__(self):
        self.search_calls = []

    def search_by_form_number(self, term, limit):
        self.search_calls.append((term, limit))
        return ["resultado"]


def test_search_trims_term_and_forwards_requested_limit():
    repository = FakeOperativoRepository()

    results = SearchAppraisalsUseCase(repository).execute("  AV-2026  ", limit=12)

    assert results == ["resultado"]
    assert repository.search_calls == [("AV-2026", 12)]


def test_search_short_terms_without_calling_repository():
    repository = FakeOperativoRepository()

    assert SearchAppraisalsUseCase(repository).execute(" A ") == []
    assert repository.search_calls == []
