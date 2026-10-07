from app.rag.citations import check_citations


def test_valid_citations_are_kept():
    result = check_citations("Mutation adds variety [1]. Selection keeps the best [2].", 2)
    assert result.text == "Mutation adds variety [1]. Selection keeps the best [2]."
    assert result.cited == {1, 2}
    assert result.removed == []


def test_out_of_range_citation_is_removed():
    result = check_citations("Mutation adds variety [1][7].", 3)
    assert result.text == "Mutation adds variety [1]."
    assert result.cited == {1}
    assert result.removed == [7]


def test_zero_is_not_a_valid_citation():
    result = check_citations("Mutation adds variety [0].", 3)
    assert result.text == "Mutation adds variety."
    assert result.removed == [0]


def test_grouped_citations_are_split_and_checked():
    result = check_citations("GAs evolve solutions [1, 9].", 2)
    assert result.text == "GAs evolve solutions [1]."
    assert result.removed == [9]

    result = check_citations("GAs evolve solutions [1,2].", 2)
    assert result.text == "GAs evolve solutions [1][2]."


def test_spacing_is_tidied_after_removal():
    result = check_citations("First [5] point, and second [6] point [1].", 1)
    assert result.text == "First point, and second point [1]."


def test_answer_without_citations_is_unchanged():
    result = check_citations("No citations here.", 3)
    assert result.text == "No citations here."
    assert result.cited == set()


def test_newlines_are_preserved():
    result = check_citations("- Point one [1]\n- Point two [4]", 2)
    assert result.text == "- Point one [1]\n- Point two"
