from fomc_signal.score.sentences import split_sentences


def test_splits_on_sentence_ends_but_not_abbreviations():
    text = ("The U.S. economy grew. Inflation remains elevated.\n\n"
            "The release is at 2 p.m. Eastern time today. Chair.")
    assert split_sentences(text) == [
        "The U.S. economy grew.", "Inflation remains elevated.",
        "The release is at 2 p.m. Eastern time today."]


def test_keeps_numbers_and_quotes_together():
    text = 'The target is 1-1/4 percent. "Further firming may be needed," the Committee said.'
    assert split_sentences(text) == ["The target is 1-1/4 percent.",
                                     '"Further firming may be needed," the Committee said.']
