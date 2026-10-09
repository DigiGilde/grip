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
from grip.services.quote_drafting import CONTEXT_INSTRUCTION

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


# --- a tailored vacancy text, with the standard text as example ---------------

# Bump when the tailored prompt changes; stored with every draft.
TAILORED_PROMPT_VERSION = "vacature-op-maat-2026-10-1"

MAX_STANDARD_EXAMPLES = 2
MAX_INSTRUCTION_CHARS = 600

# The style of the organisation, derived from its own vacancy texts (see
# docs/vacatureteksten.md).
_TAILORED_SYSTEM = (
    "Je schrijft vacatureteksten voor een organisatie van de Rijksoverheid. "
    "Houd je aan deze regels.\n"
    "- Schrijf in de je-vorm, actief en concreet, op taalniveau B1. Zinnen van "
    "hooguit twintig woorden. Geen jargon dat een buitenstaander niet kent, "
    "geen Engelse modewoorden, geen uitroeptekens.\n"
    "- Begin niet elke alinea met 'Je'. Wissel af, maar blijf de lezer "
    "aanspreken.\n"
    "- Gebruik alleen de gegevens die je krijgt. Verzin geen feiten, bedragen, "
    "namen, data, opleidingseisen, arbeidsvoorwaarden of opdrachtgevers.\n"
    "- Beloof niets over salaris, contract, verlof of doorgroei: die onderdelen "
    "voegt de organisatie zelf toe.\n"
    "- Noem geen namen van personen.\n"
    "- Stel geen eisen die mensen onnodig uitsluiten. Vraag ervaring en "
    "vaardigheden, geen leeftijd, afkomst of 'jong en dynamisch'.\n"
    "- Geef alleen de gevraagde onderdelen terug, in de gevraagde vorm, zonder "
    "inleiding of toelichting."
)


@dataclass(frozen=True)
class StandardExample:
    """A standard text of the organisation, as an example for the model."""

    role: str
    # Only the role's own sections; the shared ones are never sent.
    text: str


@dataclass(frozen=True)
class OutlineSection:
    key: str
    heading: str
    # Words to aim for, from the length of the standard text.
    words: int


@dataclass(frozen=True)
class TailoredInput:
    """Everything a tailored draft may be based on. Nothing else is sent."""

    role: str
    outline: tuple[OutlineSection, ...]
    scale_band: str | None = None
    fte: Decimal | None = None
    period_start: date | None = None
    period_end: date | None = None
    contract_type: ContractType | None = None
    assignment_name: str | None = None
    client_name: str | None = None
    unit_name: str | None = None
    # Titles of the corpus nodes the assignment refers to, with the political
    # input they follow from.
    context: tuple[str, ...] = ()
    # What the person adds: "leg nadruk op ...".
    instruction: str | None = None
    examples: tuple[StandardExample, ...] = ()

    def __post_init__(self) -> None:
        if not self.role or not self.role.strip():
            raise DraftInputError("Een concept heeft minstens de rol nodig.")
        if not self.outline:
            raise DraftInputError("Een concept heeft onderdelen nodig om te schrijven.")
        if len(self.examples) > MAX_STANDARD_EXAMPLES + 1:
            raise DraftInputError(
                "Geef hooguit drie standaardteksten mee als voorbeeld."
            )
        if self.instruction and len(self.instruction) > MAX_INSTRUCTION_CHARS:
            raise DraftInputError(
                f"Houd de aanwijzing korter dan {MAX_INSTRUCTION_CHARS} tekens."
            )

    def free_text(self) -> list[str]:
        """Every piece of text a person typed, for the name check."""
        parts = [
            self.role,
            self.assignment_name,
            self.client_name,
            self.unit_name,
            self.instruction,
            *self.context,
            *(example.text for example in self.examples),
        ]
        return [part for part in parts if part]


ALLOWED_TAILORED_FIELDS: frozenset[str] = frozenset(
    f.name for f in fields(TailoredInput)
)


def build_tailored_prompt(draft_input: TailoredInput) -> tuple[str, str]:
    """The system and user message for a tailored vacancy text.

    Three clearly separated parts: what to write, the facts as data, and the
    examples as examples. The answer comes back as the same sections, each
    under a line ``## <kop>``, so it lands in the same editor.
    """
    facts: list[tuple[str, str]] = [("Rol", draft_input.role.strip())]
    if draft_input.unit_name:
        facts.append(("Onderdeel", draft_input.unit_name.strip()))
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
    if draft_input.client_name:
        facts.append(("Opdrachtgever", draft_input.client_name.strip()))

    lines = [
        "Schrijf een concept voor een vacaturetekst op maat.",
        "",
        "Schrijf precies deze onderdelen, in deze volgorde. Zet boven elk "
        "onderdeel een regel '## ' met de kop zoals hieronder; het eerste "
        "onderdeel zonder kop begint met '## Inleiding'.",
    ]
    for section in draft_input.outline:
        heading = section.heading or "Inleiding"
        lines.append(f"- {heading} (ongeveer {section.words} woorden)")
    lines += [
        "",
        "Een lijst schrijf je met een streepje per regel. Schrijf geen andere "
        "onderdelen: wat de organisatie biedt, waar je komt te werken en hoe "
        "je solliciteert staan al vast en komen er later bij.",
        "",
        "<gegevens>",
        *(f"{label}: {value}" for label, value in facts),
    ]
    lines.append("</gegevens>")
    if draft_input.context:
        # The whole block, as a quote section gets it: the policy nodes of the
        # assignment and the chain up to the political input.
        lines += ["", CONTEXT_INSTRUCTION, "", "<beleidscontext>"]
        lines.extend(line.rstrip() for line in draft_input.context)
        lines.append("</beleidscontext>")
    if draft_input.instruction:
        lines += [
            "",
            "<aanwijzing>",
            draft_input.instruction.strip(),
            "</aanwijzing>",
        ]
    for number, example in enumerate(draft_input.examples, start=1):
        lines += [
            "",
            f'<voorbeeld nummer="{number}" rol="{example.role}">',
            "Dit is een standaardtekst van de organisatie. Neem de toon, de "
            "opbouw en de lengte over. Neem de inhoud alleen over waar die "
            "ook voor deze rol en deze opdracht klopt.",
            example.text.strip()[:MAX_EXAMPLE_CHARS],
            "</voorbeeld>",
        ]
    return _TAILORED_SYSTEM, "\n".join(lines)


def parse_sections(answer: str) -> list[tuple[str, str]]:
    """The model's answer as (heading, body) pairs; text before a heading
    belongs to the opening."""
    result: list[tuple[str, list[str]]] = []
    for line in answer.strip().splitlines():
        if line.startswith("## "):
            result.append((line[3:].strip(), []))
        elif result:
            result[-1][1].append(line)
        elif line.strip():
            result.append(("Inleiding", [line]))
    return [(heading, "\n".join(body).strip()) for heading, body in result]


# --- one passage of a vacancy text ---------------------------------------------

# Bump when the passage prompt changes; recorded with every proposal.
PASSAGE_PROMPT_VERSION = "vacature-passage-2026-10-1"

MAX_PASSAGE_TEXT = 12000
# Where the passage comes, in the text that goes along.
PASSAGE_MARK = "<<HIER>>"


@dataclass(frozen=True)
class PassageInput:
    """Everything a proposal for one open place may be based on."""

    role: str
    # What the open place asks for: "beschrijf in twee of drie zinnen ...".
    asked: str
    # The vacancy text as it stands, with the place marked.
    text: str
    scale_band: str | None = None
    fte: Decimal | None = None
    contract_type: ContractType | None = None
    assignment_name: str | None = None
    unit_name: str | None = None
    context: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.role or not self.role.strip():
            raise DraftInputError("Een voorstel heeft minstens de rol nodig.")
        if not self.asked.strip() or PASSAGE_MARK not in self.text:
            raise DraftInputError("Deze plek staat niet meer in de tekst.")
        if len(self.text) > MAX_PASSAGE_TEXT:
            raise DraftInputError("De tekst is te lang voor een voorstel.")

    def free_text(self) -> list[str]:
        """Every piece of text a person typed, for the name check."""
        parts = [
            self.role,
            self.asked,
            self.text,
            self.assignment_name,
            self.unit_name,
            *self.context,
        ]
        return [part for part in parts if part]


ALLOWED_PASSAGE_FIELDS: frozenset[str] = frozenset(f.name for f in fields(PassageInput))


def build_passage_prompt(passage: PassageInput) -> tuple[str, str]:
    """The system and user message for one passage of a vacancy text.

    The answer is the passage alone, as running text, so it can stand in the
    place it was asked for.
    """
    facts: list[tuple[str, str]] = [("Rol", passage.role.strip())]
    if passage.unit_name:
        facts.append(("Onderdeel", passage.unit_name.strip()))
    if passage.scale_band:
        facts.append(("Schaal", passage.scale_band))
    if passage.fte is not None:
        facts.append(("Omvang (fte)", _format_fte(passage.fte)))
    if passage.contract_type is not None:
        facts.append(
            ("Soort contract", CONTRACT_LABELS[ContractType(passage.contract_type)])
        )
    if passage.assignment_name:
        facts.append(("Opdracht", passage.assignment_name.strip()))
    lines = [
        "In de vacaturetekst hieronder staat één plek open, gemarkeerd met "
        f"{PASSAGE_MARK}. Schrijf alleen de tekst voor die plek.",
        "",
        "<gevraagd>",
        passage.asked.strip(),
        "</gevraagd>",
        "",
        "Geef alleen de passage terug: lopende tekst die past in de zin of "
        "alinea eromheen, zonder kop, zonder lijst, zonder aanhalingstekens "
        "en zonder toelichting. Noem de interne naam van de opdracht niet; "
        "beschrijf het team of product in gewone woorden.",
        "",
        "<gegevens>",
        *(f"{label}: {value}" for label, value in facts),
        "</gegevens>",
    ]
    if passage.context:
        lines += ["", CONTEXT_INSTRUCTION, "", "<beleidscontext>"]
        lines.extend(line.rstrip() for line in passage.context)
        lines.append("</beleidscontext>")
    lines += ["", "<vacaturetekst>", passage.text.strip(), "</vacaturetekst>"]
    return _TAILORED_SYSTEM, "\n".join(lines)


def clean_passage(answer: str) -> str:
    """The model's answer as text for one place: no heading, no list, no
    open place of its own, on one line per paragraph."""
    kept = []
    for line in answer.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        kept.append(line.lstrip("-*• ").strip())
    text = " ".join(kept).strip().strip('"“”').strip()
    if not text or "[vul aan" in text or PASSAGE_MARK in text:
        raise DraftInputError(
            "Het taalmodel gaf geen bruikbaar voorstel. Schrijf de passage "
            "zelf of probeer het opnieuw."
        )
    return text
