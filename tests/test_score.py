import numpy as np
import pytest
from core.score import score


def test_score_combines_cross_encoder_and_cosine_similarity():
    input_text = "I am writing a unit test and I need your output to make it real"
    output_text = "Something you need to buy a PC until I figure out where I'm working"
    assert score(input_text, output_text) == pytest.approx(14.84, abs=0.5)

    input_text = "retep I need you to be locked in and give me a good response"
    output_text = "Good at when it comes down to it"
    assert score(input_text, output_text) == pytest.approx(14.9, abs=0.5)

    input_text = "who is the diddy blud"
    output_text = "In the diddy acolyte's basement?"
    assert score(input_text, output_text) == pytest.approx(16.47, abs=0.5)
    # This is a non retep example to show that the scoring actually can go high
    input_text = "What is the capital of France"
    output_text = "The capital of France is Paris"
    assert score(input_text, output_text) == pytest.approx(99.53, abs=0.5)
