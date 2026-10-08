from app.config import Settings


def test_retrieval_top_k_default_is_8():
    # _env_file=None: check the code default, not whatever a local .env sets.
    assert Settings(_env_file=None).retrieval_top_k == 8


def test_study_time_budget_default_is_180_seconds():
    assert Settings(_env_file=None).study_max_seconds == 180


def test_startup_cleanup_is_off_by_default():
    # The owner turns it on after reviewing a report-only run on real data.
    assert Settings(_env_file=None).startup_cleanup is False


def test_front_matter_filter_is_off_by_default():
    # Measured in Phase 9: no gain in expected page kept or hit@8, so it stays off.
    assert Settings(_env_file=None).exclude_front_matter is False
