from app.rag.embedder import embed_documents, embed_query


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def test_embedding_has_expected_size():
    vectors = embed_documents(["Hello world", "Another sentence"])
    assert len(vectors) == 2
    assert len(vectors[0]) == 384


def test_empty_input_returns_empty_list():
    assert embed_documents([]) == []


def test_related_text_scores_higher_than_unrelated():
    docs = embed_documents(
        [
            "A genetic algorithm improves solutions using selection and mutation.",
            "My favourite pizza topping is pepperoni.",
        ]
    )
    query = embed_query("How do genetic algorithms work?")

    assert dot(query, docs[0]) > dot(query, docs[1])