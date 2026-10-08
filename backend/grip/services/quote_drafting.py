"""Build the prompt for a draft of one section of a quote. Pure.

What goes to the language model is fixed by construction: ``SectionInput``
has a closed set of fields and nothing else can be passed along. No names of
people, no rates, amounts, cost prices, margins or KPI figures (data classes
B for amounts, D, E and F). Text that a person typed is checked against the
names of the people known to the instance before it is sent.

Which section may be drafted is a choice of the organisation (the text
block's ``draftable``). The costs and the standard texts never are: amounts
come from the budget and terms from the organisation.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, fields
from datetime import date
from decimal import Decimal

from grip.services import quote_prose

# Bump when a prompt changes; stored with every draft.
PROMPT_VERSION = "offerte-2026-10-1"

# The context of an assignment is a block with a budget of its own
# (grip.services.context_brief); this is only the ceiling a caller may not pass.
MAX_CONTEXT_CHARS = 12000
MAX_OTHER_SECTIONS = 6
MAX_TEXT_CHARS = 6000

_SYSTEM = (
    "Je schrijft een onderdeel van een offerte van een organisatie van de "
    "Rijksoverheid aan een andere overheidsorganisatie. Je schrijft helder en "
    "zakelijk Nederlands op taalniveau B1, in de wij-vorm en met u voor de "
    "lezer, zonder jargon en zonder overdrijving. Je gebruikt alleen de "
    "gegevens die je krijgt. Je verzint geen feiten, bedragen, tarieven, namen, "
    "data, aantallen of toezeggingen. Ontbreekt iets, dan laat je het weg. Je "
    "noemt geen namen van personen. Je geeft alleen de tekst van het onderdeel "
    "terug, zonder kop, zonder inleiding of toelichting. Voor een opsomming "
    "begin je elke regel met een streepje en een spatie. Krijg je geen "
    "beleidscontext, dan zeg je niets over beleid of politiek waar de opdracht "
    "uit voortkomt."
)

# How a model is to read the context block. Shared with the vacancy texts.
CONTEXT_INSTRUCTION = (
    "Beleidscontext van de opdracht, uit het corpus van de opdrachtgever. Elke "
    "contextnode is een stuk beleid waar de opdracht naar verwijst; daaronder "
    "staat waar het uit voortkomt, niveau voor niveau, tot aan de politieke "
    "opdracht. Gebruik dit om te zeggen waarom de opdracht er is: noem de "
    "doelen en de politieke opdracht bij hun naam en in hun eigen woorden. "
    "Verzin geen beleid dat hier niet staat. Citeer geen tekst van een motie, "
    "brief of akkoord die je niet hebt gekregen: je kent alleen de titel en de "
    "omschrijving. Noem niet dat je een context hebt gekregen."
)

_REWRITE = (
    "Herschrijf de onderstaande passage. Behoud de inhoud en voeg geen feiten "
    "toe. Geef alleen de herschreven passage terug."
)

# A rewrite is not a draft: the model gets the passage and nothing to write
# from. With the facts of the assignment beside it, a short passage came back
# as a whole new section.
_REWRITE_SYSTEM = (
    "Je herschrijft een passage uit een offerte van een organisatie van de "
    "Rijksoverheid aan een andere overheidsorganisatie. Je schrijft helder en "
    "zakelijk Nederlands op taalniveau B1, in de wij-vorm en met u voor de "
    "lezer. Je geeft alleen de herschreven passage terug: dezelfde inhoud, "
    "ongeveer even lang of korter, zonder kop, zonder toelichting en zonder "
    "aanhalingstekens. Je voegt niets toe wat niet in de passage staat: geen "
    "feiten, bedragen, namen, data of toezeggingen. Een passage die een deel "
    "van een zin is, blijft een deel van een zin dat op dezelfde plek past. Je "
    "schrijft geen nieuw onderdeel en geen inleiding."
)

# A proposal this much longer than the passage is not a rewrite of it.
REWRITE_MAX_FACTOR = 3
REWRITE_MAX_EXTRA_CHARS = 200


def is_runaway_rewrite(passage: str, proposal: str) -> bool:
    """Whether a proposal is far longer than the passage it should rewrite."""
    limit = len(passage.strip()) * REWRITE_MAX_FACTOR + REWRITE_MAX_EXTRA_CHARS
    return len(proposal.strip()) > limit


class SectionInputError(ValueError):
    """The input for a draft may not be sent to the model."""


@dataclass(frozen=True)
class RoleFact:
    """A role on the budget: what is asked, never who or at what rate."""

    role: str
    fte: Decimal | None = None
    period_start: date | None = None
    period_end: date | None = None


@dataclass(frozen=True)
class SectionInput:
    """Everything a draft of a section may be based on. Nothing else."""

    heading: str
    hint: str = ""
    assignment_name: str | None = None
    client_name: str | None = None
    sender_name: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    roles: tuple[RoleFact, ...] = ()
    # Why the assignment exists: the policy nodes it refers to and the chain
    # up to the political input, as lines of one block
    # (grip.services.context_brief). Policy text from the corpus.
    context: tuple[str, ...] = ()
    # The headings of the quote, so the section fits the whole.
    outline: tuple[str, ...] = ()
    # Text of sections of this same quote that a person already settled.
    settled: tuple[tuple[str, str], ...] = ()
    # For a rewrite: the passage and what to do with it.
    passage: str | None = None
    instruction: str | None = None

    def __post_init__(self) -> None:
        if not self.heading.strip():
            raise SectionInputError("Een concept heeft de kop van het onderdeel nodig.")
        if sum(len(line) for line in self.context) > MAX_CONTEXT_CHARS:
            raise SectionInputError("De context voor een concept is te lang.")
        if len(self.settled) > MAX_OTHER_SECTIONS:
            raise SectionInputError("Te veel andere onderdelen voor een concept.")

    def free_text(self) -> list[str]:
        """Every piece of text a person typed, for the name check."""
        parts: list[str | None] = [
            self.heading,
            self.hint,
            self.assignment_name,
            self.passage,
            self.instruction,
            *self.context,
            *self.outline,
            *(role.role for role in self.roles),
        ]
        for heading, body in self.settled:
            parts.extend((heading, body))
        return [part for part in parts if part]


# The whitelist, for tests and for anyone reading: exactly these fields.
ALLOWED_INPUT_FIELDS: frozenset[str] = frozenset(f.name for f in fields(SectionInput))
ALLOWED_ROLE_FIELDS: frozenset[str] = frozenset(f.name for f in fields(RoleFact))


def ensure_no_person_names(section_input: SectionInput, names: Iterable[str]) -> None:
    """Refuse an input that mentions a person known to this instance."""
    found = quote_prose.find_names("\n".join(section_input.free_text()), list(names))
    if found:
        raise SectionInputError(
            "In de gegevens voor het concept staat de naam van een persoon ("
            f"{len(found)} gevonden). Namen gaan niet naar het taalmodel; haal "
            "ze uit de tekst en probeer het opnieuw."
        )


def _fte(value: Decimal) -> str:
    return format(value.normalize(), "f").replace(".", ",")


def _period(start: date | None, end: date | None) -> str | None:
    if start and end:
        return f"van {start.isoformat()} tot en met {end.isoformat()}"
    if start:
        return f"vanaf {start.isoformat()}"
    if end:
        return f"tot en met {end.isoformat()}"
    return None


def build_prompt(section_input: SectionInput) -> tuple[str, str]:
    """The system and user message for a draft or a rewrite of a section."""
    lines: list[str] = []
    if section_input.passage:
        lines.append(_REWRITE)
        if section_input.instruction:
            lines.append(f"Aanwijzing: {section_input.instruction.strip()}")
        lines += ["", "Passage:", section_input.passage.strip()[:MAX_TEXT_CHARS], ""]
        lines.append(f"De passage staat in het onderdeel '{section_input.heading}'.")
        return _REWRITE_SYSTEM, "\n".join(lines)
    else:
        lines.append(
            f"Schrijf een concept voor het onderdeel '{section_input.heading.strip()}' "
            "van de offerte, in 80 tot 220 woorden."
        )
        if section_input.hint:
            lines.append(f"Wat in dit onderdeel hoort: {section_input.hint.strip()}")

    facts: list[tuple[str, str]] = []
    if section_input.assignment_name:
        facts.append(("Opdracht", section_input.assignment_name.strip()))
    if section_input.client_name:
        facts.append(("Opdrachtgever", section_input.client_name.strip()))
    if section_input.sender_name:
        facts.append(("Opdrachtnemer", section_input.sender_name.strip()))
    period = _period(section_input.period_start, section_input.period_end)
    if period:
        facts.append(("Looptijd", period))
    if facts:
        lines += ["", "Gegevens:"]
        lines.extend(f"- {label}: {value}" for label, value in facts)
    if section_input.roles:
        lines += ["", "Gevraagde rollen:"]
        for role in section_input.roles:
            parts = [role.role.strip()]
            if role.fte is not None:
                parts.append(f"{_fte(role.fte)} fte")
            role_period = _period(role.period_start, role.period_end)
            if role_period:
                parts.append(role_period)
            lines.append("- " + ", ".join(parts))
    if section_input.context:
        lines += ["", CONTEXT_INSTRUCTION, ""]
        lines.extend(line.rstrip() for line in section_input.context)
    if section_input.outline:
        lines += ["", "De onderdelen van de offerte, in volgorde:"]
        lines.extend(f"- {heading.strip()}" for heading in section_input.outline)
    if section_input.settled:
        lines += ["", "Wat er in andere onderdelen al staat. Herhaal dit niet:"]
        for heading, body in section_input.settled:
            lines += ["", f"{heading.strip()}:", body.strip()[:MAX_TEXT_CHARS]]
    return _SYSTEM, "\n".join(lines)
