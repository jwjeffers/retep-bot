import pytest
from core.score import score


def test_score_combines_relevance_and_cosine_similarity():
    input_text = "I am writing a unit test and I need your output to make it real"
    output_text = "Something you need to buy a PC until I figure out where I'm working"
    assert score(input_text, output_text) == pytest.approx(32.08, abs=15.0)

    input_text = "retep I need you to be locked in and give me a good response"
    output_text = "Good at when it comes down to it"
    assert score(input_text, output_text) == pytest.approx(28.49, abs=15.0)

    input_text = "Mogo"
    output_text = "Mogo look at the picture"
    assert score(input_text, output_text) == pytest.approx(14.68, abs=15.0)

    input_text = "who is the diddy blud"
    output_text = "In the diddy acolyte's basement?"
    assert score(input_text, output_text) == pytest.approx(90.90, abs=15.0)

    input_text = "am I going to break you with the scoreboard change"
    output_text = "Going so well it seems."
    assert score(input_text, output_text) == pytest.approx(44.44, abs=15.0)

    input_text = "are you ok if I switch out the encoder model for one that was trained on reddit threads"
    output_text = "Switch one but I already unplugged my setup. Surely you would do that."
    assert score(input_text, output_text) == pytest.approx(43.57, abs=15.0)
    
    # This is a non retep example to show that the scoring actually can go high
    input_text = "What is the capital of France"
    output_text = "The capital of France is Paris"
    assert score(input_text, output_text) == pytest.approx(96.11, abs=15.0)


def test_one_word_input_strips_repeated_words():
    # Nothing left after removing the echoed word, so there's nothing to score
    assert score("Mogo", "Mogo") == 0.0
    assert score("Mogo", "mogo!") == 0.0
