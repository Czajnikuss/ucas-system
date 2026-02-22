import pytest
from quality_scorer import Sample, score_sample_quality

def test_score_high_quality():
    s1 = Sample(text="Zgłaszam awarię", category="A", embedding=[1.0, 0.0])
    hist = [
        Sample(text="Awaria systemu", category="A", embedding=[0.8, 0.2])
    ]
    score = score_sample_quality(s1, hist)
    assert score == 1.0

def test_score_duplicate_low_quality():
    s1 = Sample(text="Zgłaszam awarię", category="A", embedding=[1.0, 0.0])
    hist = [
        Sample(text="Zgłaszam awarię", category="A", embedding=[1.0, 0.0])
    ]
    score = score_sample_quality(s1, hist)
    assert score == 0.2 # Zbyt podobne = niski score