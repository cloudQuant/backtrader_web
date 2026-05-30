import csv
from pathlib import Path


def test_news_classifier_accuracy_against_golden_set():
    from app.services.news_intelligence import NewsIntelligenceService

    dataset = Path(__file__).resolve().parents[3] / "data" / "news_labelled_200.csv"
    rows = list(csv.DictReader(dataset.read_text(encoding="utf-8").splitlines()))

    service = NewsIntelligenceService()
    correct = 0
    for row in rows:
        result = service.analyze(row["headline"], allow_ai=False)
        if result["sentiment"] == row["expected_sentiment"]:
            correct += 1

    accuracy = correct / len(rows)
    assert len(rows) == 200
    assert accuracy >= 0.70
