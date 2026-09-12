"""Tests for the record of which provider carried the traffic, and for how long."""

from datetime import UTC, datetime, timedelta

from domain import LabelTimeline

MOMENT = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
LATER = MOMENT + timedelta(hours=4)


def test_one_segment_holds_the_whole_record() -> None:
    """A line that never moved spent all of its recorded time on one provider."""
    timeline = LabelTimeline()
    timeline.record(MOMENT, "Eolo")
    assert timeline.share("Eolo", LATER) == 100.0


def test_the_share_is_the_time_and_not_the_number_of_turns() -> None:
    """Three hours and one hour are not half each."""
    timeline = LabelTimeline()
    timeline.record(MOMENT, "Eolo")
    timeline.record(MOMENT + timedelta(hours=3), "Iliad")
    assert timeline.share("Eolo", LATER) == 75.0
    assert timeline.share("Iliad", LATER) == 25.0


def test_a_provider_that_came_back_adds_its_two_turns_up() -> None:
    """A line that flaps is one provider with two segments, not two providers."""
    timeline = LabelTimeline()
    timeline.record(MOMENT, "Eolo")
    timeline.record(MOMENT + timedelta(hours=1), "Iliad")
    timeline.record(MOMENT + timedelta(hours=2), "Eolo")
    assert timeline.share("Eolo", LATER) == 75.0


def test_the_same_label_twice_opens_no_second_segment() -> None:
    """A reading that changed nothing is not the start of anything."""
    timeline = LabelTimeline()
    timeline.record(MOMENT, "Eolo")
    timeline.record(MOMENT + timedelta(hours=1), "Eolo")
    assert len(timeline) == 1


def test_a_provider_never_seen_holds_nothing() -> None:
    """A label with no segment is honestly zero, not absent."""
    timeline = LabelTimeline()
    timeline.record(MOMENT, "Eolo")
    assert timeline.share("Iliad", LATER) == 0.0


def test_an_empty_record_gives_everybody_nothing() -> None:
    """Before the first reading there is no share to hand out."""
    assert LabelTimeline().share("Eolo", MOMENT) == 0.0


def test_the_segment_running_at_the_window_start_is_clipped_to_it() -> None:
    """What happened two days ago is not part of the last day."""
    timeline = LabelTimeline()
    timeline.record(LATER - timedelta(hours=48), "Eolo")
    timeline.record(LATER - timedelta(hours=12), "Iliad")
    assert timeline.share("Eolo", LATER) == 50.0


def test_the_denominator_is_what_is_on_record_not_the_whole_day() -> None:
    """An installation of two hours can only speak for those two hours."""
    timeline = LabelTimeline()
    timeline.record(LATER - timedelta(hours=2), "Eolo")
    assert timeline.share("Eolo", LATER) == 100.0
    assert timeline.covered(LATER) == timedelta(hours=2).total_seconds()


def test_segments_that_left_the_window_are_dropped() -> None:
    """The record is the last day, so it has to stop growing somewhere."""
    timeline = LabelTimeline()
    timeline.record(LATER - timedelta(hours=48), "Eolo")
    timeline.record(LATER - timedelta(hours=36), "Iliad")
    timeline.record(LATER - timedelta(hours=1), "Eolo")
    assert timeline.expire(LATER)
    assert len(timeline) == 2


def test_the_segment_covering_the_window_start_survives_the_sweep() -> None:
    """Dropping it would hand the first half of the day to nobody."""
    timeline = LabelTimeline()
    timeline.record(LATER - timedelta(hours=48), "Eolo")
    timeline.record(LATER - timedelta(hours=1), "Iliad")
    timeline.expire(LATER)
    assert timeline.share("Eolo", LATER) > 90.0


def test_a_sweep_that_drops_nothing_says_so() -> None:
    """The caller republishes on a True, so a False has to mean unchanged."""
    timeline = LabelTimeline()
    timeline.record(LATER - timedelta(hours=1), "Eolo")
    assert not timeline.expire(LATER)


def test_the_open_segment_is_the_provider_carrying_now() -> None:
    """The record knows what it is holding without being asked the time."""
    timeline = LabelTimeline()
    timeline.record(MOMENT, "Eolo")
    timeline.record(MOMENT + timedelta(hours=1), "Iliad")
    assert timeline.current == "Iliad"
    assert LabelTimeline().current is None


def test_round_trip_through_storage_is_stable() -> None:
    """What survives a restart has to be what was held before it."""
    timeline = LabelTimeline()
    timeline.record(MOMENT, "Eolo")
    timeline.record(MOMENT + timedelta(hours=1), "Iliad")
    restored = LabelTimeline(LabelTimeline.from_list(timeline.to_list()))
    assert restored.share("Eolo", LATER) == timeline.share("Eolo", LATER)


def test_an_unreadable_segment_is_skipped_not_raised() -> None:
    """A corrupted record costs one segment, never an entity that will not start."""
    entries = LabelTimeline.from_list(
        [["not a date", "Eolo"], [MOMENT.isoformat(), "Iliad"], "nonsense"]
    )
    assert entries == [(MOMENT, "Iliad")]


def test_what_comes_back_is_merged_with_what_already_ran() -> None:
    """The first reading of the new run lands before the stored record does."""
    timeline = LabelTimeline()
    timeline.record(MOMENT + timedelta(hours=3), "Iliad")
    timeline.adopt([(MOMENT, "Eolo")])
    assert timeline.share("Eolo", LATER) == 75.0


def test_merging_does_not_reopen_a_segment_already_open() -> None:
    """The label was already running: the stored entry is the same segment."""
    timeline = LabelTimeline()
    timeline.record(MOMENT + timedelta(hours=1), "Eolo")
    timeline.adopt([(MOMENT, "Eolo")])
    assert len(timeline) == 1
    assert timeline.share("Eolo", LATER) == 100.0
