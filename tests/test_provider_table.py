"""Tests for the provider table parsing rules."""


def test_accepts_the_forms_people_type(provider_table) -> None:
    """Bare digits, the AS prefix and a spaced prefix all mean the same.

    Args:
        provider_table: the module under test.
    """
    parsed = provider_table.parse_provider_table(
        "35612 = Eolo\nAS51207 = Iliad\nas 29447 = Iliad"
    )
    assert parsed == {"35612": "Eolo", "51207": "Iliad", "29447": "Iliad"}


def test_skips_unusable_lines_instead_of_failing(provider_table) -> None:
    """A typo costs one provider, never a dialog that refuses to close.

    Args:
        provider_table: the module under test.
    """
    parsed = provider_table.parse_provider_table(
        "\n35612 = Eolo\nnonsense\n= orphan\n99 =\n"
    )
    assert parsed == {"35612": "Eolo"}


def test_round_trip_is_stable(provider_table) -> None:
    """Formatting then parsing returns the mapping unchanged.

    Args:
        provider_table: the module under test.
    """
    table = {"51207": "Iliad", "35612": "Eolo"}
    formatted = provider_table.format_provider_table(table)
    assert provider_table.parse_provider_table(formatted) == table


def test_formatting_orders_by_number_not_by_string(provider_table) -> None:
    """Ordering by text would put 9 after 35612.

    Args:
        provider_table: the module under test.
    """
    formatted = provider_table.format_provider_table({"35612": "Eolo", "9": "Nine"})
    assert formatted.splitlines()[0] == "9 = Nine"


def test_suggestion_offers_the_detected_network_for_naming(provider_table) -> None:
    """On an empty table the detected network is the only line to fill in.

    Args:
        provider_table: the module under test.
    """
    assert provider_table.suggest_table({}, 35612) == "35612 = "


def test_suggestion_appends_without_touching_what_is_there(provider_table) -> None:
    """An existing table keeps its rows and gains the unmapped one.

    Args:
        provider_table: the module under test.
    """
    suggested = provider_table.suggest_table({"35612": "Eolo"}, 51207)
    assert suggested.splitlines() == ["35612 = Eolo", "51207 = "]


def test_suggestion_leaves_an_already_mapped_network_alone(provider_table) -> None:
    """Suggesting a network that is already named would duplicate the row.

    Args:
        provider_table: the module under test.
    """
    assert provider_table.suggest_table({"35612": "Eolo"}, 35612) == "35612 = Eolo"


def test_label_comes_from_the_table_when_the_network_is_known(provider_table) -> None:
    """A mapped network reports the name the user chose.

    Args:
        provider_table: the module under test.
    """
    assert provider_table.resolve_label({"35612": "Eolo"}, 35612, "Unknown") == "Eolo"


def test_unmapped_and_unresolved_give_the_same_answer(provider_table) -> None:
    """Not in the table and not resolvable are both honestly unknown.

    Args:
        provider_table: the module under test.
    """
    unmapped = provider_table.resolve_label({"35612": "Eolo"}, 51207, "Unknown")
    unresolved = provider_table.resolve_label({"35612": "Eolo"}, None, "Unknown")
    assert unmapped == unresolved == "Unknown"


def test_suggestion_survives_a_failed_detection(provider_table) -> None:
    """A failed lookup must open the form, not break it.

    Args:
        provider_table: the module under test.
    """
    assert provider_table.suggest_table({"35612": "Eolo"}, None) == "35612 = Eolo"
