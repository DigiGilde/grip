"""Import from a Grist document download.

The steps, each its own module: read the document (``document``), check the
declarative mapping against it (``mapping``), judge the formulas behind the
open questions (``formulas``), propose what free text means (``freetext``)
and have a person confirm it (``confirmation``), turn it all into a plan
(``transform``), load the plan through the service layer (``load``) and
compare Grist's amounts with grip's (``reconcile``). ``cli`` ties them
together; docs/import-grist.md is the procedure for the person doing it.
"""
