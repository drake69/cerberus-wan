"""Tests for the provider table."""

from domain import Asn, ProviderTable


def test_parses_one_provider_per_line() -> None:
    """The table is written the way a person would write it."""
    table = ProviderTable.parse("35612 = Eolo\nAS51207 = Iliad\nas 29447 = Iliad")
    assert table.as_mapping() == {
        "35612": "Eolo",
        "51207": "Iliad",
        "29447": "Iliad",
    }


def test_skips_unusable_lines_instead_of_failing() -> None:
    """A typo costs one provider, never a dialog that refuses to close."""
    table = ProviderTable.parse("\n35612 = Eolo\nnonsense\n= orphan\n99 =\n")
    assert table.as_mapping() == {"35612": "Eolo"}


def test_round_trip_is_stable() -> None:
    """Formatting then parsing returns the table unchanged."""
    table = ProviderTable({"51207": "Iliad", "35612": "Eolo"})
    assert ProviderTable.parse(table.format()) == table


def test_formatting_orders_by_number_not_by_string() -> None:
    """Ordering by text would put 9 after 35612."""
    table = ProviderTable({"35612": "Eolo", "9": "Nine"})
    assert table.format().splitlines()[0] == "9 = Nine;"


def test_known_labels_drop_repeats_and_keep_the_order() -> None:
    """Two networks of one provider are one entity, not two."""
    table = ProviderTable({"51207": "Iliad", "29447": "Iliad", "35612": "Eolo"})
    assert table.known_labels == ["Iliad", "Eolo"]


def test_label_comes_from_the_table_when_the_network_is_known() -> None:
    """A mapped network reports the name the user chose."""
    table = ProviderTable({"35612": "Eolo"})
    assert table.label_for(Asn(35612), "Unknown") == "Eolo"


def test_unmapped_and_unresolved_give_the_same_answer() -> None:
    """Not in the table and not resolvable are both honestly unknown."""
    table = ProviderTable({"35612": "Eolo"})
    unmapped = table.label_for(Asn(51207), "Unknown")
    unresolved = table.label_for(None, "Unknown")
    assert unmapped == unresolved == "Unknown"


def test_suggestion_offers_the_detected_network_for_naming() -> None:
    """On an empty table the detected network is the only line to fill in."""
    assert ProviderTable().suggestion(Asn(35612)) == "35612 = ;"


def test_suggestion_appends_without_touching_what_is_there() -> None:
    """An existing table keeps its rows and gains the unmapped one."""
    suggested = ProviderTable({"35612": "Eolo"}).suggestion(Asn(51207))
    assert suggested.splitlines() == ["35612 = Eolo;", "51207 = ;"]


def test_suggestion_leaves_an_already_mapped_network_alone() -> None:
    """Suggesting a network that is already named would duplicate the row."""
    assert ProviderTable({"35612": "Eolo"}).suggestion(Asn(35612)) == "35612 = Eolo;"


def test_suggestion_survives_a_failed_detection() -> None:
    """A failed lookup must open the form, not break it."""
    assert ProviderTable({"35612": "Eolo"}).suggestion(None) == "35612 = Eolo;"


def test_suggestion_offers_the_networks_seen_before_the_current_one() -> None:
    """A backup can be named the day after the failover, not only during it."""
    suggested = ProviderTable({"35612": "Eolo"}).suggestion(
        Asn(35612), Asn(51207), Asn(30722)
    )
    assert suggested.splitlines() == ["35612 = Eolo;", "51207 = ;", "30722 = ;"]


def test_suggestion_offers_a_network_only_once() -> None:
    """The network in use is normally also the last one seen."""
    assert ProviderTable().suggestion(Asn(51207), Asn(51207)) == "51207 = ;"


def test_suggestion_offers_the_history_when_detection_failed() -> None:
    """Losing the lookup must not also lose what was already written down."""
    assert ProviderTable().suggestion(None, Asn(51207)) == "51207 = ;"


def test_suggestion_with_nothing_to_offer_returns_the_table_unchanged() -> None:
    """An installation with every provider named sees only its own table."""
    assert ProviderTable({"35612": "Eolo"}).suggestion() == "35612 = Eolo;"


def test_the_semicolon_closes_a_provider_on_a_single_line() -> None:
    """The field can hand the whole table back on one line, and often does."""
    table = ProviderTable.parse("35612 = Eolo; 51207 = Iliad; 30722 = Fastweb")
    assert table.as_mapping() == {
        "35612": "Eolo",
        "51207": "Iliad",
        "30722": "Fastweb",
    }


def test_without_a_closing_semicolon_a_number_lands_inside_a_name() -> None:
    """The bug the semicolon exists to prevent, kept as a test."""
    broken = ProviderTable.parse("35612 = Eolo 51207 = Iliad")
    assert broken.as_mapping() == {"35612": "Eolo 51207 = Iliad"}


def test_a_trailing_semicolon_does_not_invent_a_provider() -> None:
    """Every row is closed, so the last one ends on a separator by design."""
    assert ProviderTable.parse("35612 = Eolo;") == ProviderTable({"35612": "Eolo"})


def test_rows_survive_being_written_either_way() -> None:
    """Line breaks and semicolons are both a row ending, and they mix."""
    mixed = ProviderTable.parse("35612 = Eolo;\n51207 = Iliad\n30722 = Fastweb;")
    assert mixed.known_labels == ["Eolo", "Iliad", "Fastweb"]


def test_a_named_row_can_be_written_after_without_a_separator() -> None:
    """Closing the rows is what makes appending to the table safe."""
    table = ProviderTable({"35612": "Eolo"})
    assert ProviderTable.parse(table.format() + "51207 = Iliad").as_mapping() == {
        "35612": "Eolo",
        "51207": "Iliad",
    }
