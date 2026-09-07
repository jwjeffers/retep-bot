import numpy as np

from core.score import score


def test_score_combines_cross_encoder_and_cosine_similarity():
    input = "I am writing a unit test and I need your output to make it real"
    output = "Something you need to buy a PC until I figure out where I'm working"
    assert score(input, output) == 14.84

    input = "retep I need you to be locked in and give me a good response"
    output = "Good at when it comes down to it"
    assert score(input, output) == 14.9

    input = "who is the diddy blud"
    output = "In the diddy acolyte's basement?"
    assert score(input, output) == 16.47
