from scheme_intel.catalyst import classify
from scheme_intel.models import Article


def test_contract_award_is_material():
    article = Article("Praj Industries receives contract awarded for CBG plant", "https://example.test/a", "PIB", None)
    result = classify(article, [{"name": "Praj Industries", "aliases": ["Praj"]}])
    assert result is not None
    assert result.score >= 85
    assert result.companies == ("Praj Industries",)


