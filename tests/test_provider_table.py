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
    assert table.format().splitlines()[0] == "9 = Nine"


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
    assert ProviderTable().suggestion(Asn(35612)) == "35612 = "


def test_suggestion_appends_without_touching_what_is_there() -> None:
    """An existing table keeps its rows and gains the unmapped one."""
    suggested = ProviderTable({"35612": "Eolo"}).suggestion(Asn(51207))
    assert suggested.splitlines() == ["35612 = Eolo", "51207 = "]


def test_suggestion_leaves_an_already_mapped_network_alone() -> None:
    """Suggesting a network that is already named would duplicate the row."""
    assert ProviderTable({"35612": "Eolo"}).suggestion(Asn(35612)) == "35612 = Eolo"


def test_suggestion_survives_a_failed_detection() -> None:
    """A failed lookup must open the form, not break it."""
    assert ProviderTable({"35612": "Eolo"}).suggestion(None) == "35612 = Eolo"
