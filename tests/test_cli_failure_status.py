from src.cli import _has_destination_failure


def test_partial_destination_delivery_is_a_failure():
    results = [
        {
            "status": "partial_success",
            "destinations": {
                "telegram": {"status": "success"},
                "mega": {"status": "failed"},
            },
        }
    ]

    assert _has_destination_failure(results) is True


def test_all_destinations_success_or_duplicate_is_not_a_failure():
    results = [
        {
            "status": "success",
            "destinations": {
                "telegram": {"status": "success"},
                "mega": {"status": "success"},
            },
        },
        {
            "status": "skipped_duplicate",
            "destinations": {
                "mega": {"status": "duplicate"},
            },
        },
    ]

    assert _has_destination_failure(results) is False


def test_empty_results_have_no_destination_failure():
    assert _has_destination_failure([]) is False
