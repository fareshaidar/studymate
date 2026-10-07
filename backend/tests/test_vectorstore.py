from app.rag.chunker import Chunk
from app.rag.vectorstore import VectorStore


def make_store(tmp_path):
    # tmp_path is a throwaway folder, so tests never touch your real data.
    return VectorStore(path=tmp_path / "chroma")


def sample_chunks():
    return [
        Chunk(text="A genetic algorithm evolves solutions using mutation.", page=3, index=0),
        Chunk(text="Pepperoni pizza is made with cheese and tomato sauce.", page=7, index=1),
    ]


def test_search_returns_best_chunk_with_its_page(tmp_path):
    store = make_store(tmp_path)
    store.add_chunks("doc1", sample_chunks())

    results = store.search("How do genetic algorithms work?", k=2)

    assert results[0].page == 3
    assert results[0].document_id == "doc1"
    assert results[0].score > results[1].score


def test_search_on_empty_store_returns_nothing(tmp_path):
    assert make_store(tmp_path).search("anything") == []


def test_search_can_be_limited_to_one_document(tmp_path):
    store = make_store(tmp_path)
    store.add_chunks("doc1", sample_chunks())
    store.add_chunks("doc2", sample_chunks())

    results = store.search("genetic algorithm", k=5, document_ids=["doc2"])

    assert results
    assert all(r.document_id == "doc2" for r in results)


def test_delete_document_removes_its_chunks(tmp_path):
    store = make_store(tmp_path)
    store.add_chunks("doc1", sample_chunks())

    store.delete_document("doc1")

    assert store.search("genetic algorithm") == []


def test_adding_the_same_document_twice_does_not_duplicate(tmp_path):
    store = make_store(tmp_path)
    store.add_chunks("doc1", sample_chunks())
    store.add_chunks("doc1", sample_chunks())

    assert len(store.search("genetic algorithm", k=10)) == 2