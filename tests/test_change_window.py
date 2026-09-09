"""Tests for the moving window of provider changes."""

from datetime import UTC, datetime, timedelta

from domain import ChangeWindow

MOMENT = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
DAY = timedelta(hours=24)


def test_counts_only_what_is_inside_the_window() -> None:
    """A change from last week is not a change of the last day."""
    window = ChangeWindow([MOMENT - DAY - timedelta(minutes=1), MOMENT])
    assert window.count(MOMENT) == 1


def test_the_average_is_the_count_over_the_width_of_the_window() -> None:
    """One change in twenty four hours has to read as more than zero."""
    window = ChangeWindow([MOMENT])
    assert window.per_hour(MOMENT) == 0.042


def test_an_empty_window_averages_zero() -> None:
    """A line that never switched reports zero, not nothing."""
    assert ChangeWindow().per_hour(MOMENT) == 0.0


def test_expiring_reports_whether_anything_left() -> None:
    """The hourly sweep republishes only when the numbers actually moved."""
    window = ChangeWindow([MOMENT - DAY - timedelta(minutes=1), MOMENT])
    assert window.expire(MOMENT) is True
    assert window.expire(MOMENT) is False
    assert len(window) == 1


def test_the_last_change_is_the_most_recent_one() -> None:
    """Recording out of order must not confuse what happened last."""
    window = ChangeWindow()
    window.record(MOMENT)
    window.record(MOMENT - timedelta(hours=2))
    assert window.last == MOMENT


def test_nothing_recorded_means_no_last_change() -> None:
    """Before the first switchover there is nothing to report."""
    assert ChangeWindow().last is None


def test_adopting_a_stored_window_keeps_what_happened_meanwhile() -> None:
    """A change between startup and restore must not be dropped."""
    window = ChangeWindow()
    window.record(MOMENT)
    window.adopt([MOMENT - timedelta(hours=3)])
    assert len(window) == 2


def test_adopting_the_same_change_twice_counts_it_once() -> None:
    """Restoring must not inflate the count it is restoring."""
    window = ChangeWindow([MOMENT])
    window.adopt([MOMENT])
    assert len(window) == 1


def test_the_window_survives_a_round_trip_through_storage() -> None:
    """What is written has to be readable."""
    window = ChangeWindow([MOMENT, MOMENT - timedelta(hours=1)])
    assert ChangeWindow(ChangeWindow.from_list(window.to_list())).count(MOMENT) == 2


def test_a_corrupted_record_costs_one_change_and_not_the_entity() -> None:
    """An unreadable stored window must not keep the sensor from starting."""
    assert len(ChangeWindow.from_list([MOMENT.isoformat(), "not a date"])) == 1


def test_nothing_stored_is_an_empty_window() -> None:
    """A first run has nothing to restore."""
    assert ChangeWindow.from_list(None) == []
