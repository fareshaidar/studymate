from app.config import Settings


def test_retrieval_top_k_default_is_8():
    # _env_file=None: check the code default, not whatever a local .env sets.
    assert Settings(_env_file=None).retrieval_top_k == 8
