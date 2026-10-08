"""A standard text with a value that is missing prints no label for it."""

from grip.services import quote_sender
from grip.services.quote_drafts import _follows

TEMPLATE = (
    "Met vriendelijke groet.\n\n"
    "**Contactpersoon {eenheid}**\n{contactpersoon}\n\n"
    "Stuur de opdracht naar {opdrachtenadres}."
)


def test_an_empty_value_takes_its_line_and_its_label_along():
    text = quote_sender.fill_placeholders(
        TEMPLATE,
        {"eenheid": "Team", "contactpersoon": "", "opdrachtenadres": "a@b.example"},
    )
    assert text == ("Met vriendelijke groet.\n\nStuur de opdracht naar a@b.example.")


def test_a_value_inside_a_sentence_leaves_the_sentence():
    text = quote_sender.fill_placeholders(
        TEMPLATE,
        {"eenheid": "Team", "contactpersoon": "Carla", "opdrachtenadres": ""},
    )
    assert "**Contactpersoon Team**\nCarla" in text
    assert text.endswith("Stuur de opdracht naar .")


def test_a_text_filled_without_the_value_still_follows_its_template():
    values = {"eenheid": "Team", "contactpersoon": "", "opdrachtenadres": "a@b.example"}
    filled = quote_sender.fill_placeholders(TEMPLATE, values)
    assert _follows(TEMPLATE, filled)
    assert not _follows(TEMPLATE, "Een eigen begin. " + filled)
