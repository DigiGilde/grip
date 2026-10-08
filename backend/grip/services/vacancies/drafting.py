"""Build the prompt for a draft text. Pure, no database, no network.

What goes to the language model is fixed by construction: ``DraftInput`` has
a closed set of fields and nothing else can be passed along. No names of
candidates or colleagues, no rates, cost prices, margins or KPI figures
(data classes D, E and F). Free text that a person typed (the summary of an
assignment, earlier vacancy texts) is checked against the names of the
people known to the instance before it is sent.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, fields
from datetime import date
from decimal import Decimal

from grip.models.vacancy import ContractType, TextKind

# Bump when a prompt changes; stored with every draft.
PROMPT_VERSION = "vacature-2026-10-1"

MAX_EXAMPLES = 3
MAX_EXAMPLE_CHARS = 4000

CONTRACT_LABELS: dict[ContractType, str] = {
    ContractType.temporary_project: "tijdelijk (projectcontract)",
    ContractType.temporary_before_permanent: "tijdelijk, voorafgaand aan vast",
}

_SYSTEM = (
    "Je schrijft teksten voor een organisatie van de Rijksoverheid. Je schrijft "
    "helder en zakelijk Nederlands op taalniveau B1, in de je-vorm, zonder "
    "jargon en zonder overdrijving. Je gebruikt alleen de gegevens die je "
    "krijgt. Je verzint geen feiten, bedragen, namen, data, opleidingseisen of "
    "arbeidsvoorwaarden. Ontbreekt iets, dan laat je het weg. Je noemt geen "
    "namen van personen. Je geeft alleen de gevraagde tekst terug, zonder "
    "inleiding of toelichting."
)

_INSTRUCTIONS: dict[TextKind, str] = {
    TextKind.vacancy_text: (
        "Schrijf een concept voor een vacaturetekst. Gebruik deze opbouw, met "
        "een korte kop per onderdeel:\n"
        "1. Wat ga je doen\n"
        "2. Waar kom je te werken\n"
        "3. Wat breng je mee\n"
        "4. Wat bieden we\n"
        "Houd het bij 300 tot 450 woorden. Bij 'Wat bieden we' noem je alleen "
        "de schaal, de omvang, de periode en het soort contract uit de "
        "gegevens."
    ),
    TextKind.motivation: (
        "Schrijf een concept voor het onderdeel 'Aanleiding en motivatie' van "
        "een aanvraag om een vacature open te stellen. Leg in 60 tot 120 "
        "woorden uit waarom deze rol nodig is voor de opdracht en wat er "
        "gebeurt als de rol niet wordt ingevuld. Schrijf een doorlopende "
        "alinea, zonder kopjes."
    ),
}


class DraftInputError(ValueError):
    """The input for a draft may not be sent to the model."""


@dataclass(frozen=True)
class DraftInput:
    """Everything a draft may be based on. Nothing else reaches the model."""

    role: str
    scale_band: str | None = None
    fte: Decimal | None = None
    period_start: date | None = None
    period_end: date | None = None
    contract_type: ContractType | None = None
    assignment_name: str | None = None
    assignment_summary: str | None = None
    organisation_description: str | None = None
    # Established texts of earlier vacancies of this instance.
    examples: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.role or not self.role.strip():
            raise DraftInputError("Een concept heeft minstens de rol nodig.")
        if len(self.examples) > MAX_EXAMPLES:
            raise DraftInputError(
                f"Geef hooguit {MAX_EXAMPLES} eerdere vacatureteksten mee."
            )

    def free_text(self) -> list[str]:
        """Every piece of text a person typed, for the name check."""
        parts = [
            self.role,
            self.assignment_name,
            self.assignment_summary,
            self.organisation_description,
            *self.examples,
        ]
        return [part for part in parts if part]


# The whitelist, for tests and for anyone reading: exactly these fields.
ALLOWED_INPUT_FIELDS: frozenset[str] = frozenset(f.name for f in fields(DraftInput))


def find_person_names(draft_input: DraftInput, names: Iterable[str]) -> list[str]:
    """Names from ``names`` that occur in the free text of the input.

    A full name matches anywhere, ignoring case. Names shorter than five
    characters are skipped: they would match ordinary words.
    """
    # Collapse whitespace on both sides, so a line break or a double space
    # inside a name does not hide it.
    haystack = " ".join("\n".join(draft_input.free_text()).split()).casefold()
    found: list[str] = []
    for name in names:
        needle = " ".join(name.split()).casefold()
        if len(needle) < 5:
            continue
        if needle in haystack:
            found.append(name)
    return found


def ensure_no_person_names(draft_input: DraftInput, names: Iterable[str]) -> None:
    """Refuse an input that mentions a person known to this instance."""
    found = find_person_names(draft_input, names)
    if found:
        raise DraftInputError(
            "In de gegevens voor het concept staat de naam van een persoon ("
            f"{len(found)} gevonden). Namen gaan niet naar het taalmodel; haal "
            "ze uit de tekst en probeer het opnieuw."
        )


def _format_fte(fte: Decimal) -> str:
    return format(fte.normalize(), "f").replace(".", ",")


def _format_period(start: date | None, end: date | None) -> str | None:
    if start and end:
        return f"van {start.isoformat()} tot en met {end.isoformat()}"
    if start:
        return f"vanaf {start.isoformat()}"
    if end:
        return f"tot en met {end.isoformat()}"
    return None


def build_prompt(kind: TextKind | str, draft_input: DraftInput) -> tuple[str, str]:
    """The system and user message for a draft of this kind."""
    kind = TextKind(kind)
    facts: list[tuple[str, str]] = [("Rol", draft_input.role.strip())]
    if draft_input.scale_band:
        facts.append(("Schaal", draft_input.scale_band))
    if draft_input.fte is not None:
        facts.append(("Omvang (fte)", _format_fte(draft_input.fte)))
    period = _format_period(draft_input.period_start, draft_input.period_end)
    if period:
        facts.append(("Periode", period))
    if draft_input.contract_type is not None:
        facts.append(
            ("Soort contract", CONTRACT_LABELS[ContractType(draft_input.contract_type)])
        )
    if draft_input.assignment_name:
        facts.append(("Opdracht", draft_input.assignment_name.strip()))
    if draft_input.assignment_summary:
        facts.append(("Over de opdracht", draft_input.assignment_summary.strip()))
    if draft_input.organisation_description:
        facts.append(
            ("Over de organisatie", draft_input.organisation_description.strip())
        )

    lines = [_INSTRUCTIONS[kind], "", "Gegevens:"]
    lines.extend(f"- {label}: {value}" for label, value in facts)
    if kind is TextKind.vacancy_text and draft_input.examples:
        lines.append("")
        lines.append(
            "Eerdere vacatureteksten van deze organisatie. Neem de toon en de "
            "opbouw over, niet de inhoud:"
        )
        for number, example in enumerate(draft_input.examples, start=1):
            lines.append("")
            lines.append(f"Voorbeeld {number}:")
            lines.append(example.strip()[:MAX_EXAMPLE_CHARS])
    return _SYSTEM, "\n".join(lines)
