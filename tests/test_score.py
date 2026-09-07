import numpy as np

from core.score import score


def test_score_combines_cross_encoder_and_cosine_similarity():
    input = "I am writing a unit test and I need your output to make it real"
    output = "Something you need to buy a PC until I figure out where I'm working"
    assert score(input, output) == -10.27
