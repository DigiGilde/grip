"""Unit tests for rules R1 to R14, one group per rule."""

from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction

import pytest
from conftest import EUR, RATES_2026, make_card

from grip.calc import (
    AmountSource,
    BillabilityTarget,
    CostCoverage,
    CostItem,
    CoverageBasis,
    CoverageExceededError,
    InvalidInputError,
    InvoiceLine,
    InvoiceLineKind,
    MismatchDirection,
    MissingPersonScaleError,
    MissingRateCardError,
    MissingRateError,
    MissingScaleBandError,
    Month,
    PartialMonths,
    RateBook,
    RateCardStatus,
    allocation_amount,
    allocation_months,
    assignment_totals,
    billing_lines,
    budget_line_months,
    budget_line_status,
    budgeted,
    budgeted_by_year,
    category_mismatches,
    closed_month_amount,
    cost_item_coverage,
    coverage_amount,
    forecast,
    kpi_realisation,
    kpi_target,
    person_monthly_rate,
    rate_category,
    round_cents,
    subtotals_by_year,
    used,
)

HOSTING = CostItem("hosting", budgeted_cents=20_000 * EUR)
HOSTING_INVOICES = (
    InvoiceLine(
        "HOST-26-01", "hosting", InvoiceLineKind.ACTUAL, 10_000 * EUR, date(2026, 3, 1)
    ),
    InvoiceLine(
        "HOST-26-02", "hosting", InvoiceLineKind.ESTIMATE, 5_000 * EUR, date(2026, 9, 1)
    ),
    InvoiceLine(
        "OTHER-1", "licences", InvoiceLineKind.ACTUAL, 999 * EUR, date(2026, 3, 1)
    ),
)


class TestRounding:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (Fraction(1, 2), 1),
            (Fraction(3, 2), 2),
            (Fraction(5, 2), 3),
            (Fraction(-1, 2), -1),
            (Fraction(-5, 2), -3),
            (Fraction(149, 100), 1),
            (Fraction(7), 7),
            (Fraction(0), 0),
        ],
    )
    def test_half_away_from_zero(self, value, expected):
        assert round_cents(value) == expected


class TestR1Rate:
    def test_rate_follows_scale_and_category(self, rates, scales):
        assert rate_category(rates, scales, "p-d", Month(2026, 3)) == "D"
        assert person_monthly_rate(rates, scales, "p-d", Month(2026, 3)) == 18_000 * EUR

    def test_rate_uses_the_card_of_the_year_of_the_month(self, rates, scales):
        assert person_monthly_rate(rates, scales, "p-d", Month(2027, 1)) == 18_900 * EUR

    def test_scale_change_mid_year(self, rates, scales):
        assert (
            person_monthly_rate(rates, scales, "p-move", Month(2026, 6)) == 15_000 * EUR
        )
        assert (
            person_monthly_rate(rates, scales, "p-move", Month(2026, 7)) == 18_000 * EUR
        )

    def test_scale_to_category_mapping_is_per_year(self, scales):
        moved = {**{s: "A" for s in range(8, 18)}, 14: "E"}
        book = RateBook(
            cards=(
                make_card(2026, RATES_2026),
                make_card(2027, RATES_2026, scales=moved),
            )
        )
        assert rate_category(book, scales, "p-d", Month(2026, 1)) == "D"
        assert rate_category(book, scales, "p-d", Month(2027, 1)) == "E"

    def test_missing_rate_card_is_an_error(self, rates, scales):
        with pytest.raises(MissingRateCardError) as error:
            person_monthly_rate(rates, scales, "p-d", Month(2028, 1))
        assert error.value.year == 2028

    def test_draft_card_does_not_price_unless_asked(self, scales):
        cards = (make_card(2026, RATES_2026, status=RateCardStatus.DRAFT),)
        with pytest.raises(MissingRateCardError):
            person_monthly_rate(RateBook(cards), scales, "p-d", Month(2026, 1))
        assert (
            person_monthly_rate(
                RateBook(cards, include_draft=True), scales, "p-d", Month(2026, 1)
            )
            == 18_000 * EUR
        )

    def test_closed_card_still_prices(self, scales):
        cards = (make_card(2026, RATES_2026, status=RateCardStatus.CLOSED),)
        assert (
            person_monthly_rate(RateBook(cards), scales, "p-d", Month(2026, 1))
            == 18_000 * EUR
        )

    def test_person_without_scale_is_an_error(self, rates, scales):
        with pytest.raises(MissingPersonScaleError):
            person_monthly_rate(rates, scales, "nobody", Month(2026, 1))

    def test_unmapped_scale_and_missing_band_are_errors(self, scales):
        book = RateBook(cards=(make_card(2026, {"A": 9_000}, scales={14: "D"}),))
        with pytest.raises(MissingRateError):
            person_monthly_rate(book, scales, "p-d", Month(2026, 1))
        with pytest.raises(MissingScaleBandError):
            person_monthly_rate(book, scales, "p-c", Month(2026, 1))


class TestR2R3Allocation:
    def test_whole_month(self, rates, scales, allocation):
        months = allocation_months(
            allocation(start=date(2026, 3, 1), end=date(2026, 3, 31), fte_pct="80"),
            rates,
            scales,
        )
        assert len(months) == 1
        assert months[0].fraction == 1
        assert months[0].cents == 14_400 * EUR
        assert months[0].category == "D"

    def test_sum_over_months(self, rates, scales, allocation):
        assert (
            allocation_amount(allocation(fte_pct="50"), rates, scales) == 108_000 * EUR
        )

    def test_period_across_two_rate_cards(self, rates, scales, allocation):
        alloc = allocation(start=date(2026, 7, 1), end=date(2027, 6, 30))
        months = allocation_months(alloc, rates, scales)
        assert [m.monthly_rate_cents for m in months] == [18_000 * EUR] * 6 + [
            18_900 * EUR
        ] * 6
        assert allocation_amount(alloc, rates, scales) == 221_400 * EUR
        assert subtotals_by_year(months) == {2026: 108_000 * EUR, 2027: 113_400 * EUR}
        assert allocation_amount(alloc, rates, scales, year=2027) == 113_400 * EUR

    def test_month_without_rate_card_is_an_error_not_zero(
        self, rates, scales, allocation
    ):
        with pytest.raises(MissingRateCardError):
            allocation_amount(
                allocation(start=date(2027, 7, 1), end=date(2028, 6, 30)), rates, scales
            )

    def test_scale_change_mid_year_is_priced_per_month(self, rates, scales, allocation):
        assert (
            allocation_amount(allocation(person_id="p-move"), rates, scales)
            == 198_000 * EUR
        )

    def test_partial_months_calendar_days(self, rates, scales, allocation):
        alloc = allocation(start=date(2026, 1, 16), end=date(2026, 3, 10))
        months = allocation_months(alloc, rates, scales)
        assert [m.fraction for m in months] == [
            Fraction(16, 31),
            Fraction(1),
            Fraction(10, 31),
        ]
        assert [m.cents for m in months] == [929_032, 1_800_000, 580_645]
        assert allocation_amount(alloc, rates, scales) == 3_309_677

    def test_partial_months_whole_months(self, rates, scales, allocation):
        alloc = allocation(start=date(2026, 1, 16), end=date(2026, 3, 10))
        assert (
            allocation_amount(
                alloc, rates, scales, partial_months=PartialMonths.WHOLE_MONTHS
            )
            == 54_000 * EUR
        )

    def test_partial_months_grist_datedif(self, rates, scales, allocation):
        alloc = allocation(start=date(2026, 1, 16), end=date(2026, 3, 10))
        months = allocation_months(
            alloc, rates, scales, partial_months=PartialMonths.GRIST_DATEDIF
        )
        assert [m.month for m in months] == [Month(2026, 1), Month(2026, 2)]
        assert sum(m.cents for m in months) == 36_000 * EUR

    @pytest.mark.parametrize("strategy", list(PartialMonths))
    def test_strategies_agree_on_whole_months(
        self, rates, scales, allocation, strategy
    ):
        alloc = allocation(start=date(2026, 2, 1), end=date(2026, 11, 30), fte_pct="60")
        assert (
            allocation_amount(alloc, rates, scales, partial_months=strategy)
            == 108_000 * EUR
        )

    def test_end_before_start_is_rejected(self, rates, scales, allocation):
        with pytest.raises(ValueError):
            allocation_amount(
                allocation(start=date(2026, 3, 1), end=date(2026, 2, 1)), rates, scales
            )

    def test_floats_are_rejected(self, rates, scales, allocation):
        alloc = allocation()
        object.__setattr__(alloc, "fte_pct", 80.0)
        with pytest.raises(InvalidInputError):
            allocation_amount(alloc, rates, scales)

    @pytest.mark.parametrize("strategy", list(PartialMonths))
    @pytest.mark.parametrize(
        ("start", "end", "pct"),
        [
            (date(2026, 1, 10), date(2026, 4, 20), "100"),
            (date(2026, 2, 28), date(2027, 2, 27), "37.5"),
            (date(2026, 12, 31), date(2027, 1, 1), "12.34"),
            (date(2026, 5, 5), date(2026, 5, 5), "100"),
        ],
    )
    def test_months_add_up_to_total_and_years(
        self, rates, scales, allocation, strategy, start, end, pct
    ):
        alloc = allocation(start=start, end=end, fte_pct=pct)
        months = allocation_months(alloc, rates, scales, partial_months=strategy)
        total = allocation_amount(alloc, rates, scales, partial_months=strategy)
        assert sum(m.cents for m in months) == total
        assert sum(subtotals_by_year(months).values()) == total
        assert all(m.cents == round_cents(m.exact) for m in months)

    @pytest.mark.parametrize(
        "boundary", [date(2026, 2, 1), date(2026, 3, 1), date(2027, 1, 1)]
    )
    def test_split_at_month_boundary_keeps_total(
        self, rates, scales, allocation, boundary
    ):
        start, end = date(2026, 1, 10), date(2027, 2, 20)
        whole = allocation_amount(
            allocation(start=start, end=end, fte_pct="70"), rates, scales
        )
        first = allocation(
            start=start, end=boundary - timedelta(days=1), fte_pct="70", id="a"
        )
        second = allocation(start=boundary, end=end, fte_pct="70", id="b")
        assert (
            allocation_amount(first, rates, scales)
            + allocation_amount(second, rates, scales)
            == whole
        )


class TestR4R5Budgeted:
    def test_worked_example_personnel(self, rates, personnel_line):
        # Productmanager, 0.8 FTE, category D, 2026: 0.8 x 12 x 18,000 = 172,800.
        assert budgeted(personnel_line(fte="0.8"), rates) == 172_800 * EUR

    def test_personnel_line_across_years(self, rates, personnel_line):
        line = personnel_line(fte="0.5", start=date(2026, 7, 1), end=date(2027, 6, 30))
        assert budgeted_by_year(line, rates) == {2026: 54_000 * EUR, 2027: 56_700 * EUR}
        assert budgeted(line, rates) == 110_700 * EUR
        assert budgeted(line, rates, year=2026) == 54_000 * EUR
        assert len(budget_line_months(line, rates)) == 12

    def test_personnel_line_without_rate_card(self, rates, personnel_line):
        with pytest.raises(MissingRateCardError):
            budgeted(
                personnel_line(start=date(2028, 1, 1), end=date(2028, 12, 31)), rates
            )

    def test_fixed_line_is_its_amount(self, rates, fixed_line):
        line = fixed_line(amount=25_000 * EUR, year=2027)
        assert budgeted(line, rates) == 25_000 * EUR
        assert budgeted_by_year(line, rates) == {2027: 25_000 * EUR}
        assert budgeted(line, rates, year=2026) == 0
        assert budget_line_months(line, rates) == ()

    def test_incomplete_lines_are_rejected(self, rates, personnel_line, fixed_line):
        with pytest.raises(InvalidInputError):
            budgeted(fixed_line(year=None), rates)
        line = personnel_line()
        object.__setattr__(line, "rate_category", None)
        with pytest.raises(InvalidInputError):
            budgeted(line, rates)


class TestR6Forecast:
    def test_sum_of_actual_and_estimate(self):
        assert forecast(HOSTING, HOSTING_INVOICES) == 15_000 * EUR

    def test_no_invoice_lines(self):
        assert forecast(CostItem("empty", 0), HOSTING_INVOICES) == 0

    def test_year_filter_uses_the_period(self):
        lines = (
            *HOSTING_INVOICES,
            InvoiceLine(
                "HOST-27-01",
                "hosting",
                InvoiceLineKind.ESTIMATE,
                4_000 * EUR,
                date(2027, 1, 1),
            ),
            InvoiceLine("HOST-xx", "hosting", InvoiceLineKind.ESTIMATE, 1_000 * EUR),
        )
        assert forecast(HOSTING, lines, year=2026) == 15_000 * EUR
        assert forecast(HOSTING, lines, year=2027) == 4_000 * EUR
        assert forecast(HOSTING, lines) == 20_000 * EUR


class TestR7R8Coverage:
    def test_worked_example(self):
        # 30 percent of a hosting contract with a forecast of 15,000 = 4,500.
        coverage = CostCoverage("cov-1", "hosting", "line-1", Decimal("30"))
        assert coverage_amount(coverage, HOSTING, HOSTING_INVOICES) == 4_500 * EUR

    def test_basis_budgeted(self):
        coverage = CostCoverage("cov-1", "hosting", "line-1", Decimal("30"))
        assert (
            coverage_amount(
                coverage, HOSTING, HOSTING_INVOICES, basis=CoverageBasis.BUDGETED
            )
            == 6_000 * EUR
        )

    def test_covered_and_uncovered_remainder(self):
        coverages = (
            CostCoverage("cov-1", "hosting", "line-1", Decimal("30")),
            CostCoverage("cov-2", "hosting", "line-2", Decimal("50")),
            CostCoverage("cov-3", "licences", "line-1", Decimal("100")),
        )
        result = cost_item_coverage(HOSTING, HOSTING_INVOICES, coverages)
        assert result.basis_cents == 15_000 * EUR
        assert result.pct_total == Decimal("80")
        assert result.covered_cents == 12_000 * EUR
        assert result.uncovered_cents == 3_000 * EUR

    def test_exactly_one_hundred_percent_is_allowed(self):
        coverages = (
            CostCoverage("cov-1", "hosting", "line-1", Decimal("33.33")),
            CostCoverage("cov-2", "hosting", "line-2", Decimal("66.67")),
        )
        result = cost_item_coverage(HOSTING, HOSTING_INVOICES, coverages)
        assert result.covered_cents == 15_000 * EUR
        assert result.uncovered_cents == 0

    def test_above_one_hundred_percent_is_an_error(self):
        coverages = (
            CostCoverage("cov-1", "hosting", "line-1", Decimal("70")),
            CostCoverage("cov-2", "hosting", "line-2", Decimal("40")),
        )
        with pytest.raises(CoverageExceededError) as error:
            cost_item_coverage(HOSTING, HOSTING_INVOICES, coverages)
        assert error.value.pct_total == Decimal("110")

    def test_coverage_of_another_cost_item_is_rejected(self):
        coverage = CostCoverage("cov-1", "licences", "line-1", Decimal("30"))
        with pytest.raises(InvalidInputError):
            coverage_amount(coverage, HOSTING, HOSTING_INVOICES)


class TestR9R10R11Totals:
    def _context(self, rates, scales, allocations=(), coverages=()):
        return {
            "allocations": allocations,
            "coverages": coverages,
            "cost_items": (HOSTING,),
            "invoice_lines": HOSTING_INVOICES,
            "rates": rates,
            "scales": scales,
        }

    def test_used_is_allocations_plus_coverage(
        self, rates, scales, allocation, personnel_line
    ):
        line = personnel_line()
        context = self._context(
            rates,
            scales,
            allocations=(
                allocation(fte_pct="50"),
                allocation(fte_pct="100", budget_line_id="other", id="alloc-2"),
            ),
            coverages=(
                CostCoverage("cov-1", "hosting", "line-1", Decimal("30")),
                CostCoverage("cov-2", "hosting", "other", Decimal("50")),
            ),
        )
        assert used(line, **context) == (108_000 + 4_500) * EUR

    def test_available(self, rates, scales, allocation, personnel_line):
        status = budget_line_status(
            personnel_line(),
            **self._context(rates, scales, allocations=(allocation(fte_pct="50"),)),
        )
        assert status.budgeted_cents == 216_000 * EUR
        assert status.used_cents == 108_000 * EUR
        assert status.available_cents == 108_000 * EUR
        assert not status.overrun

    def test_negative_available_is_an_overrun(self, rates, scales, fixed_line):
        coverages = (CostCoverage("cov-1", "hosting", "line-fixed", Decimal("100")),)
        status = budget_line_status(
            fixed_line(amount=10_000 * EUR),
            **self._context(rates, scales, coverages=coverages),
        )
        assert status.available_cents == -5_000 * EUR
        assert status.overrun

    def test_coverage_basis_is_passed_through(self, rates, scales, fixed_line):
        coverages = (CostCoverage("cov-1", "hosting", "line-fixed", Decimal("100")),)
        context = self._context(rates, scales, coverages=coverages)
        assert (
            used(fixed_line(), coverage_basis=CoverageBasis.BUDGETED, **context)
            == 20_000 * EUR
        )

    def test_coverage_of_unknown_cost_item_is_rejected(self, rates, scales, fixed_line):
        coverages = (CostCoverage("cov-1", "unknown", "line-fixed", Decimal("10")),)
        with pytest.raises(InvalidInputError):
            used(fixed_line(), **self._context(rates, scales, coverages=coverages))

    def test_assignment_totals(
        self, rates, scales, allocation, personnel_line, fixed_line
    ):
        lines = (
            personnel_line(),
            fixed_line(amount=10_000 * EUR),
            personnel_line(id="line-x", assignment_id="assignment-2"),
        )
        context = self._context(
            rates,
            scales,
            allocations=(
                allocation(fte_pct="50"),
                allocation(budget_line_id="line-x", id="a2"),
            ),
            coverages=(CostCoverage("cov-1", "hosting", "line-fixed", Decimal("100")),),
        )
        totals = assignment_totals("assignment-1", lines, **context)
        assert [s.budget_line_id for s in totals.lines] == ["line-1", "line-fixed"]
        assert totals.budgeted_cents == 226_000 * EUR
        assert totals.used_cents == 123_000 * EUR
        assert totals.available_cents == 103_000 * EUR
        assert not totals.overrun
        assert [s.overrun for s in totals.lines] == [False, True]


class TestR12R13Kpi:
    def test_worked_example_realisation(self, rates, scales, allocation):
        # 12 months at 100 percent, category D: 216,000.
        assert (
            kpi_realisation("p-d", 2026, (allocation(),), rates, scales)
            == 216_000 * EUR
        )

    def test_realisation_counts_only_the_year_and_the_person(
        self, rates, scales, allocation
    ):
        allocations = (
            allocation(start=date(2026, 7, 1), end=date(2027, 6, 30)),
            allocation(person_id="p-c", id="alloc-c"),
        )
        assert kpi_realisation("p-d", 2026, allocations, rates, scales) == 108_000 * EUR
        assert kpi_realisation("p-d", 2027, allocations, rates, scales) == 113_400 * EUR
        assert kpi_realisation("p-d", 2025, allocations, rates, scales) == 0

    def test_realisation_uses_established_actuals(self, rates, scales, allocation):
        actuals = {("alloc-1", Month(2026, 3)): Decimal("50")}
        assert (
            kpi_realisation(
                "p-d", 2026, (allocation(),), rates, scales, actuals=actuals
            )
            == 207_000 * EUR
        )

    def test_worked_example_target(self, rates, scales):
        # 90 percent x 12 x 18,000 = 194,400.
        target = BillabilityTarget("p-d", 2026, Decimal("90"))
        assert kpi_target(target, rates, scales) == 194_400 * EUR

    def test_target_follows_a_scale_change(self, rates, scales):
        target = BillabilityTarget("p-move", 2026, Decimal("90"))
        assert kpi_target(target, rates, scales) == 178_200 * EUR

    def test_target_skips_months_without_scale(self, rates):
        from grip.calc import PersonScale

        joined = (PersonScale("p-new", date(2026, 10, 1), 14),)
        target = BillabilityTarget("p-new", 2026, Decimal("100"))
        assert kpi_target(target, rates, joined) == 54_000 * EUR

    def test_target_without_rate_card_is_an_error(self, rates, scales):
        with pytest.raises(MissingRateCardError):
            kpi_target(BillabilityTarget("p-d", 2028, Decimal("90")), rates, scales)


class TestR14CategoryMismatch:
    def test_no_signal_when_categories_match(
        self, rates, scales, allocation, personnel_line
    ):
        assert (
            category_mismatches(personnel_line(), (allocation(),), rates, scales) == ()
        )

    def test_signal_when_person_bills_higher(
        self, rates, scales, allocation, personnel_line
    ):
        line = personnel_line(category="C")
        (mismatch,) = category_mismatches(line, (allocation(),), rates, scales)
        assert mismatch.person_id == "p-d"
        assert (mismatch.line_category, mismatch.person_category) == ("C", "D")
        assert (mismatch.first_month, mismatch.last_month) == (
            Month(2026, 1),
            Month(2026, 12),
        )
        assert mismatch.direction is MismatchDirection.OVERRUN

    def test_signal_when_person_bills_lower(
        self, rates, scales, allocation, personnel_line
    ):
        (mismatch,) = category_mismatches(
            personnel_line(), (allocation(person_id="p-c"),), rates, scales
        )
        assert mismatch.direction is MismatchDirection.UNDERRUN

    def test_signal_only_for_the_months_that_differ(
        self, rates, scales, allocation, personnel_line
    ):
        (mismatch,) = category_mismatches(
            personnel_line(), (allocation(person_id="p-move"),), rates, scales
        )
        assert (mismatch.first_month, mismatch.last_month) == (
            Month(2026, 1),
            Month(2026, 6),
        )
        assert mismatch.person_category == "C"

    def test_other_lines_and_fixed_lines_give_no_signal(
        self, rates, scales, allocation, personnel_line, fixed_line
    ):
        other = allocation(person_id="p-c", budget_line_id="elsewhere")
        assert category_mismatches(personnel_line(), (other,), rates, scales) == ()
        assert category_mismatches(fixed_line(), (allocation(),), rates, scales) == ()


class TestMonthlyClose:
    def test_planned_amount_is_the_proposal(self, rates, scales, allocation):
        amount = closed_month_amount(
            allocation(fte_pct="80"), Month(2026, 3), rates, scales
        )
        assert amount.cents == 14_400 * EUR
        assert amount.source is AmountSource.PLANNED

    def test_actual_overrides_planned(self, rates, scales, allocation):
        amount = closed_month_amount(
            allocation(fte_pct="80"),
            Month(2026, 3),
            rates,
            scales,
            actual_fte_pct=Decimal("50"),
        )
        assert amount.cents == 9_000 * EUR
        assert amount.fte_pct == Decimal("50")
        assert amount.source is AmountSource.ACTUAL

    def test_actual_counts_over_the_whole_month(self, rates, scales, allocation):
        alloc = allocation(start=date(2026, 3, 16), end=date(2026, 6, 30))
        planned = closed_month_amount(alloc, Month(2026, 3), rates, scales)
        actual = closed_month_amount(
            alloc, Month(2026, 3), rates, scales, actual_fte_pct=Decimal("50")
        )
        assert planned.fraction == Fraction(16, 31)
        assert actual.cents == 9_000 * EUR

    def test_actual_of_zero_is_not_the_same_as_no_actual(
        self, rates, scales, allocation
    ):
        amount = closed_month_amount(
            allocation(), Month(2026, 3), rates, scales, actual_fte_pct=Decimal("0")
        )
        assert amount.cents == 0
        assert amount.source is AmountSource.ACTUAL

    def test_month_outside_the_allocation_is_rejected(self, rates, scales, allocation):
        with pytest.raises(InvalidInputError):
            closed_month_amount(allocation(), Month(2027, 1), rates, scales)

    def test_month_that_the_strategy_does_not_count(self, rates, scales, allocation):
        alloc = allocation(start=date(2026, 1, 16), end=date(2026, 3, 10))
        amount = closed_month_amount(
            alloc,
            Month(2026, 3),
            rates,
            scales,
            partial_months=PartialMonths.GRIST_DATEDIF,
        )
        assert amount.cents == 0

    def test_billing_lines(self, rates, scales, allocation, personnel_line):
        lines = (
            personnel_line(),
            personnel_line(id="line-2", assignment_id="assignment-2"),
        )
        allocations = (
            allocation(fte_pct="80"),
            allocation(
                person_id="p-c", budget_line_id="line-2", id="alloc-c", fte_pct="100"
            ),
            allocation(
                person_id="p-move",
                start=date(2026, 7, 1),
                end=date(2026, 12, 31),
                id="later",
            ),
        )
        actuals = {("alloc-1", Month(2026, 3)): Decimal("50")}
        result = billing_lines(
            Month(2026, 3), allocations, lines, rates, scales, actuals=actuals
        )
        assert [
            (b.assignment_id, b.person_id, b.amount_cents, b.source) for b in result
        ] == [
            ("assignment-1", "p-d", 9_000 * EUR, AmountSource.ACTUAL),
            ("assignment-2", "p-c", 15_000 * EUR, AmountSource.PLANNED),
        ]
        assert result[0].category == "D"
        assert result[0].monthly_rate_cents == 18_000 * EUR

    def test_billing_lines_reject_stray_actuals_and_unknown_lines(
        self, rates, scales, allocation, personnel_line
    ):
        with pytest.raises(InvalidInputError):
            billing_lines(
                Month(2026, 3),
                (allocation(),),
                (personnel_line(),),
                rates,
                scales,
                actuals={("unknown", Month(2026, 3)): Decimal("50")},
            )
        with pytest.raises(InvalidInputError):
            billing_lines(Month(2026, 3), (allocation(),), (), rates, scales)
