"""Command line for the Grist import.

    python -m grip.importers.grist inspect   <document.grist>
    python -m grip.importers.grist check     <document.grist>
    python -m grip.importers.grist propose   <document.grist> --confirmations F
    python -m grip.importers.grist confirm   F --confidence hoog
    python -m grip.importers.grist load      <document.grist> --confirmations F
    python -m grip.importers.grist reconcile <document.grist> --confirmations F

``F`` is the path of the confirmation list (JSON). ``inspect``, ``check``,
``propose`` and ``confirm`` do not touch the database. ``load`` writes in one
transaction and commits only when nothing was refused; with ``--dry-run`` it
always rolls back. Exit codes: 0 fine, 1 errors (nothing written), 2 wrong
use or unreadable input, 3 loaded but the reconciliation shows differences.

docs/import-grist.md describes the whole procedure.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from grip.importers.grist.confirmation import (
    HIGH_CONFIDENCE,
    KINDS,
    ConfirmationError,
    ConfirmationList,
    confirm_by_confidence,
    merge,
    read_confirmations,
)
from grip.importers.grist.document import GristDocument, GristDocumentError
from grip.importers.grist.inspection import render_check, render_inspection
from grip.importers.grist.mapping import (
    Mapping,
    MappingError,
    check_mapping,
    load_mapping,
    unverified_tables,
)
from grip.importers.grist.transform import ImportPlan, Issue, build_plan

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from grip.importers.grist.load import LoadResult
    from grip.importers.grist.reconcile import ReconciliationReport
    from grip.models.person import Person

# The commands that only read a file must work without database settings, so
# everything that imports the models is imported inside the commands that
# need it.

EXIT_OK = 0
EXIT_ERRORS = 1
EXIT_USAGE = 2
EXIT_DIFFERENCES = 3

DEFAULT_DOCUMENT_KEY = "grist"


def _print_issues(title: str, issues: list[Issue]) -> None:
    if not issues:
        return
    order = {"fout": 0, "waarschuwing": 1, "info": 2}
    print(title)
    for issue in sorted(issues, key=lambda i: order.get(i.severity, 3)):
        print(f"  {issue}")
    print()


def _print_counts(title: str, counts: dict[str, int]) -> None:
    if not counts:
        return
    print(title)
    for name, count in sorted(counts.items()):
        print(f"  {name}: {count}")
    print()


def _read_plan(
    args: argparse.Namespace, *, need_confirmations: bool
) -> tuple[GristDocument, Mapping, ImportPlan, ConfirmationList | None]:
    mapping = load_mapping(args.mapping)
    document = GristDocument(args.document)
    check = check_mapping(document, mapping)
    if not check.ok:
        print("\n".join(render_check(check)))
        raise SystemExit(EXIT_USAGE)
    confirmations = None
    path = getattr(args, "confirmations", None)
    if path and Path(path).is_file():
        confirmations = read_confirmations(path)
    elif need_confirmations:
        print(
            "Er is nog geen bevestigingslijst. Maak die eerst met 'propose' en "
            "loop haar na."
        )
        raise SystemExit(EXIT_USAGE)
    plan = build_plan(
        document, mapping, check, confirmations=confirmations, year=args.year
    )
    return document, mapping, plan, confirmations


def cmd_inspect(args: argparse.Namespace) -> int:
    mapping = load_mapping(args.mapping)
    with GristDocument(args.document) as document:
        print(render_inspection(document, mapping), end="")
    return EXIT_OK


def cmd_check(args: argparse.Namespace) -> int:
    mapping = load_mapping(args.mapping)
    with GristDocument(args.document) as document:
        check = check_mapping(document, mapping)
    print("\n".join(render_check(check)))
    return EXIT_OK if check.ok else EXIT_ERRORS


def cmd_propose(args: argparse.Namespace) -> int:
    document, _, plan, earlier = _read_plan(args, need_confirmations=False)
    document.close()
    result = merge(plan.confirmations, earlier)
    result.merged.write(args.confirmations)
    counts = result.merged.counts()
    print(f"Bevestigingslijst geschreven: {args.confirmations}")
    print(
        f"  {len(result.merged.items)} items: {counts['voorstel']} te beoordelen, "
        f"{counts['bevestigd']} bevestigd, {counts['overslaan']} overgeslagen."
    )
    if earlier is not None:
        print(
            f"  Uit de vorige lijst behouden: {result.kept}. Terug naar voorstel "
            f"omdat de bron wijzigde: {len(result.reset)}. Nieuw: {len(result.new)}. "
            f"Vervallen: {len(result.dropped)}."
        )
    by_confidence: dict[str, int] = {}
    for item in result.merged.open_items():
        by_confidence[item.confidence] = by_confidence.get(item.confidence, 0) + 1
    if by_confidence:
        detail = ", ".join(f"{k}: {v}" for k, v in sorted(by_confidence.items()))
        print(f"  Te beoordelen naar zekerheid: {detail}.")
    print()
    _print_issues("Bevindingen bij het lezen:", plan.issues)
    return EXIT_ERRORS if plan.errors else EXIT_OK


def cmd_confirm(args: argparse.Namespace) -> int:
    confirmations = read_confirmations(args.confirmations)
    kinds = tuple(args.kind) if args.kind else KINDS
    changed = confirm_by_confidence(confirmations, args.confidence, kinds)
    confirmations.write(args.confirmations)
    print(f"{len(changed)} items met zekerheid '{args.confidence}' op bevestigd gezet.")
    for key in changed:
        item = confirmations.get(key)
        print(f"  {key}  {item.label if item else ''}")
    return EXIT_OK


async def _actor(session: AsyncSession, email: str | None) -> Person | None:
    if not email:
        return None
    from sqlalchemy import func, select

    from grip.models.person import Person

    person = await session.scalar(
        select(Person).where(func.lower(Person.email) == email.lower())
    )
    if person is None:
        print(f"Geen persoon met e-mailadres {email} in grip.")
        raise SystemExit(EXIT_USAGE)
    return person


def _gate(args: argparse.Namespace, mapping: Mapping, plan: ImportPlan) -> int | None:
    """Reasons not to load at all, before anything is written."""
    unverified = unverified_tables(mapping, set(plan.grist_tables))
    if unverified and not args.allow_unverified_mapping:
        print(
            "De koppeling is nog niet bevestigd voor: "
            + ", ".join(unverified)
            + ". Controleer haar met 'inspect' en 'check' en zet 'verified = true'."
        )
        return EXIT_USAGE
    if plan.unconfirmed and not args.allow_unconfirmed:
        print(
            f"{len(plan.unconfirmed)} items op de bevestigingslijst zijn nog niet "
            "beoordeeld. Loop de lijst na, of geef --allow-unconfirmed om door te "
            "gaan: onbevestigde begrotingsregels worden dan als vast bedrag "
            "geladen, hun inzet niet, en schalen blijven leeg."
        )
        for key in plan.unconfirmed[:20]:
            print(f"  {key}")
        if len(plan.unconfirmed) > 20:
            print(f"  ... en nog {len(plan.unconfirmed) - 20}")
        return EXIT_USAGE
    if plan.errors:
        _print_issues("Het document is niet te laden:", plan.errors)
        return EXIT_ERRORS
    return None


def _print_load(result: LoadResult) -> None:
    _print_counts("Nieuw:", result.created)
    _print_counts("Gewijzigd:", result.updated)
    _print_counts("Ongewijzigd:", result.unchanged)
    _print_issues("Bevindingen bij het laden:", result.issues)


def _finish(report: ReconciliationReport, args: argparse.Namespace) -> int:
    from grip.importers.grist.reconcile import render

    text = render(report, all_rows=args.all_rows)
    print(text, end="")
    if args.report:
        Path(args.report).write_text(text, encoding="utf-8")
        print(f"\nRapport geschreven: {args.report}")
    return EXIT_OK if report.reconciles else EXIT_DIFFERENCES


async def _load(args: argparse.Namespace) -> int:
    from grip.core.database import async_session, close_db
    from grip.importers.grist.load import load_plan
    from grip.importers.grist.reconcile import reconcile

    document, mapping, plan, _ = _read_plan(args, need_confirmations=True)
    document.close()
    _print_counts("Gelezen uit het document:", plan.counts())
    _print_issues("Bevindingen bij het lezen:", plan.issues)
    stop = _gate(args, mapping, plan)
    if stop is not None:
        return stop
    try:
        async with async_session() as session:
            actor = await _actor(session, args.actor_email)
            result = await load_plan(
                session,
                plan,
                document_key=args.document_key,
                actor=actor,
                allow_closed_year=args.allow_closed_year,
            )
            _print_load(result)
            if result.errors:
                await session.rollback()
                print(
                    f"{len(result.errors)} fout(en). Er is niets geschreven; los ze "
                    "op en draai opnieuw."
                )
                return EXIT_ERRORS
            report = await reconcile(session, plan, result)
            if args.dry_run:
                await session.rollback()
                print("Proefrun: er is niets geschreven.\n")
            else:
                await session.commit()
                print("Geladen en vastgelegd.\n")
            return _finish(report, args)
    finally:
        await close_db()


async def _reconcile(args: argparse.Namespace) -> int:
    from grip.core.database import async_session, close_db
    from grip.importers.grist.load import LoadResult
    from grip.importers.grist.reconcile import reconcile
    from grip.importers.grist.refs import RefIndex

    document, _, plan, _ = _read_plan(args, need_confirmations=True)
    document.close()
    try:
        async with async_session() as session:
            refs = RefIndex(session, args.document_key)
            await refs.load()
            loaded = LoadResult()
            tables = plan.grist_tables
            for person in plan.persons:
                if found := refs.get(tables.get("team", ""), person.row_id, "person"):
                    loaded.persons[person.row_id] = found
            for assignment in plan.assignments:
                if found := refs.get(
                    tables.get("assignments", ""), assignment.row_id, "assignment"
                ):
                    loaded.assignments[assignment.row_id] = found
            for line in plan.lines:
                if found := refs.get(
                    tables.get("budget_lines", ""), line.row_id, "budget_line"
                ):
                    loaded.lines[line.row_id] = found
            for allocation in plan.allocations:
                if found := refs.get(
                    tables.get("allocations", ""), allocation.row_id, "allocation"
                ):
                    loaded.allocations[allocation.row_id] = found
            for item in plan.cost_items:
                if found := refs.get(
                    tables.get("cost_items", ""), item.row_id, "cost_item"
                ):
                    loaded.cost_items[item.row_id] = found
            report = await reconcile(session, plan, loaded)
            await session.rollback()
            return _finish(report, args)
    finally:
        await close_db()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m grip.importers.grist",
        description="Import uit een Grist-document (zie docs/import-grist.md).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def document_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("document", help="het gedownloade Grist-document (.grist)")
        p.add_argument("--mapping", help="eigen koppeling (standaard de meegeleverde)")

    def plan_args(p: argparse.ArgumentParser) -> None:
        document_args(p)
        p.add_argument(
            "--confirmations", required=True, help="pad van de bevestigingslijst (JSON)"
        )
        p.add_argument(
            "--year",
            type=int,
            default=None,
            help="jaar van de Tarievenleaflet (standaard uit de koppeling: 2026)",
        )

    def report_args(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--document-key",
            default=DEFAULT_DOCUMENT_KEY,
            help="naam waaronder dit document wordt onthouden; houd die gelijk "
            "tussen runs",
        )
        p.add_argument(
            "--report", help="schrijf het aansluitrapport ook naar dit bestand"
        )
        p.add_argument(
            "--all-rows",
            action="store_true",
            help="toon alle vergeleken waarden, niet alleen de afwijkingen",
        )

    p = sub.add_parser("inspect", help="toon tabellen, kolommen en formules")
    document_args(p)
    p.set_defaults(run=cmd_inspect)

    p = sub.add_parser("check", help="controleer de koppeling tegen het document")
    document_args(p)
    p.set_defaults(run=cmd_check)

    p = sub.add_parser("propose", help="schrijf of ververs de bevestigingslijst")
    plan_args(p)
    p.set_defaults(run=cmd_propose)

    p = sub.add_parser(
        "confirm", help="bevestig in een keer alle open items van een zekerheid"
    )
    p.add_argument("confirmations", help="pad van de bevestigingslijst (JSON)")
    p.add_argument("--confidence", default=HIGH_CONFIDENCE, choices=["hoog", "middel"])
    p.add_argument("--kind", action="append", choices=list(KINDS))
    p.set_defaults(run=cmd_confirm)

    p = sub.add_parser("load", help="laad het document in grip en sluit aan")
    plan_args(p)
    report_args(p)
    p.add_argument("--dry-run", action="store_true", help="schrijf niets weg")
    p.add_argument(
        "--actor-email", help="persoon in grip die in de auditlog als bron staat"
    )
    p.add_argument("--allow-unconfirmed", action="store_true")
    p.add_argument("--allow-unverified-mapping", action="store_true")
    p.add_argument("--allow-closed-year", action="store_true")
    p.set_defaults(run=lambda a: asyncio.run(_load(a)))

    p = sub.add_parser(
        "reconcile", help="sluit opnieuw aan op wat eerder is geladen, zonder te laden"
    )
    plan_args(p)
    report_args(p)
    p.set_defaults(run=lambda a: asyncio.run(_reconcile(a)))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return int(args.run(args))
    except SystemExit as exc:
        # A command that stops early says why itself and passes its code.
        return int(exc.code or 0)
    except (GristDocumentError, MappingError, ConfirmationError) as exc:
        print(f"Fout: {exc}", file=sys.stderr)
        return EXIT_USAGE
