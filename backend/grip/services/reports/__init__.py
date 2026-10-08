"""Read models for the reports: per assignment, steering, and the year account.

Nothing here computes an amount of its own. Money comes from the pricing
service and the calculation module; this package only groups what they
return (per month, per year, per status) and joins it with facts that are
already stored (the accepted quote, the audit log, billing exports).

The routes decide who may see what. These functions return everything.
"""
