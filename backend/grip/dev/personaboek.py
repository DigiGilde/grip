"""Build the standalone Personaboek HTML from docs/personas/*.md.

Run via ``just personaboek``. Needs markdown-it-py, which the recipe supplies
with ``uv run --with`` so the backend dependencies stay untouched.
"""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

import yaml

from grip.dev.markdown_pages import new_markdown, rewrite_targets, shift_headings

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INPUT = REPO_ROOT / "docs" / "personas"
DEFAULT_OUTPUT = REPO_ROOT / "artifacts" / "personaboek.html"

REQUIRED_KEYS = (
    "code",
    "naam",
    "rol",
    "organisatie",
    "eenheid",
    "fgr",
    "mandaat",
    "grips",
)
ORGANISATIONS = (
    "Voorbeeldministerie",
    "Voorbeeldprogramma",
    "DigiGilde voorbeeld",
    "Voorbeeldbeheerorganisatie",
)
ACCESS_LABELS = {
    "account": "Account",
    "gast": "Gast",
    "via-federatie": "Via federatie",
}
FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)


class PersonaError(Exception):
    """A persona file is invalid."""


@dataclass
class Persona:
    meta: dict[str, Any]
    body: str
    path: Path

    @property
    def code(self) -> str:
        return str(self.meta["code"])


def parse_persona(path: Path) -> Persona:
    text = path.read_text(encoding="utf-8")
    match = FRONT_MATTER.match(text)
    if not match:
        raise PersonaError(f"{path.name}: front matter ontbreekt")
    try:
        meta = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise PersonaError(
            f"{path.name}: front matter is geen geldige YAML ({exc})"
        ) from exc
    if not isinstance(meta, dict):
        raise PersonaError(f"{path.name}: front matter is geen mapping")
    missing = [key for key in REQUIRED_KEYS if key not in meta]
    if missing:
        raise PersonaError(
            f"{path.name}: verplichte sleutel(s) ontbreken: {', '.join(missing)}"
        )
    if str(meta["code"]) != path.stem:
        raise PersonaError(
            f"{path.name}: code {meta['code']!r} komt niet overeen met de bestandsnaam"
        )
    if not isinstance(meta["grips"], list):
        raise PersonaError(f"{path.name}: grips moet een lijst zijn")
    for key in ("fgr", "mandaat"):
        if not isinstance(meta[key], dict):
            raise PersonaError(f"{path.name}: {key} moet een mapping zijn")
    return Persona(meta=meta, body=match.group(2), path=path)


def load_personas(directory: Path) -> tuple[str, list[Persona]]:
    if not directory.is_dir():
        raise PersonaError(f"{directory} bestaat niet")
    intro = ""
    personas: list[Persona] = []
    seen: dict[str, Path] = {}
    for path in sorted(directory.glob("*.md")):
        if path.name == "README.md":
            intro = path.read_text(encoding="utf-8")
            continue
        persona = parse_persona(path)
        if persona.code in seen:
            raise PersonaError(
                f"code {persona.code} komt voor in {seen[persona.code].name} "
                f"en {path.name}"
            )
        seen[persona.code] = path
        personas.append(persona)
    if not personas:
        raise PersonaError(f"geen persona's gevonden in {directory}")
    return intro, personas


PERSONA_LINK = re.compile(r"(?:\./)?([\w-]+)\.md(#.*)?")


def _renderer(codes: set[str]) -> Callable[[str, int], str]:
    """Links to a persona become anchors in the book; links into docs/ become text."""
    md = new_markdown()

    def link(href: str) -> str | None:
        if href.startswith("#") or href.startswith(("http://", "https://", "mailto:")):
            return href
        local = PERSONA_LINK.fullmatch(href)
        if local:
            name = local.group(1)
            if name == "README":
                return "#inhoud"
            if name not in codes:
                return None
            return f"#{name}"
        return None

    def render(text: str, shift: int = 0) -> str:
        tokens = md.parse(text)
        shift_headings(tokens, shift)
        rewrite_targets(tokens, link, lambda _src: None)
        return md.renderer.render(tokens, md.options, {})

    return render


def _e(value: object) -> str:
    return escape("" if value is None else str(value))


def _link(url: object, label: object) -> str:
    url_s = str(url or "")
    if url_s.startswith(("http://", "https://")):
        return f'<a href="{escape(url_s)}" rel="noopener">{_e(label)}</a>'
    return _e(label)


def _facts(meta: dict[str, Any]) -> str:
    fgr, mandaat = meta["fgr"], meta["mandaat"]
    schaal = f", schaal {_e(fgr.get('schaal'))}" if fgr.get("schaal") else ""
    badge = (
        ' <span class="badge badge-warn">eigen inschatting</span>'
        if fgr.get("inschatting")
        else ""
    )
    bron = str(mandaat.get("bron") or "")
    if bron.startswith(("http://", "https://")):
        bron_html = f' <span class="badge">bron: {_link(bron, "link")}</span>'
    else:
        bron_html = f' <span class="badge badge-warn">{_e(bron or "aanname")}</span>'
    functie = _link(fgr.get("url"), fgr.get("functie"))
    return (
        '<dl class="facts">'
        f"<dt>Functie (FGR)</dt><dd>{functie}{schaal}{badge}"
        f'<br><span class="muted">Familie: {_e(fgr.get("familie"))}</span></dd>'
        f"<dt>Mandaat</dt><dd>{_e(mandaat.get('tekst'))}{bron_html}</dd>"
        "</dl>"
    )


def _code_list(items: list[Any]) -> str:
    return ", ".join(f"<code>{_e(i)}</code>" for i in items) or "-"


def _optional_list(label: str, items: list[Any] | None) -> str:
    if not items:
        return ""
    return f"<dt>{label}</dt><dd>{_code_list(items)}</dd>"


def _look_in(grip: dict[str, Any]) -> str:
    person = grip.get("voorbeeldpersoon")
    hint = (
        f"Kies daar voorbeeldpersoon {_e(person)} in het accountmenu "
        "(online: na het inloggen)."
        if person
        else "Kies daar een voorbeeldpersoon in het accountmenu."
    )
    return (
        '<p class="lookin">'
        f'<a class="grip-link" data-instance="{_e(grip.get("instantie"))}" hidden>'
        "Kijk in deze grip</a>"
        f' <span class="muted">{hint}</span></p>'
    )


def _grip_card(grip: dict[str, Any], level: int = 4) -> str:
    toegang = str(grip.get("toegang", ""))
    if grip.get("voorbeeldpersoon") or grip.get("dataset"):
        voorbeeld = (
            f"{_e(grip.get('voorbeeldpersoon') or '-')}"
            f' <span class="muted">in dataset</span> {_e(grip.get("dataset") or "-")}'
        )
    else:
        voorbeeld = '<span class="muted">nog niet in een dataset</span>'
    return (
        '<li class="card">'
        f"<h{level}>{_e(grip.get('instantie'))}</h{level}>"
        f'<p><span class="badge">{_e(ACCESS_LABELS.get(toegang, toegang))}</span></p>'
        "<dl>"
        f"{_optional_list('Rechten', grip.get('rechten'))}"
        f"{_optional_list('Relaties', grip.get('relaties'))}"
        f"<dt>Voorbeeld</dt><dd>{voorbeeld}</dd>"
        f"</dl>{_look_in(grip)}</li>"
    )


def _instances(persona: Persona) -> list[str]:
    return [
        str(g.get("instantie")) for g in persona.meta["grips"] if g.get("instantie")
    ]


LEADING_H1 = re.compile(r"\A\s*# [^\n]*\n")


def _article(persona: Persona, render: Callable[[str, int], str], top: int = 2) -> str:
    """``top`` is the heading level of the persona's name; the rest follows."""
    m = persona.meta
    body = LEADING_H1.sub("", persona.body, count=1)
    cards = "".join(_grip_card(g, top + 2) for g in m["grips"])
    grips_html = (
        f'<section class="grips"><h{top + 1}>Grips</h{top + 1}><ul class="cards">{cards}</ul></section>'
        if cards
        else ""
    )
    search = " ".join(str(m[k]) for k in ("code", "naam", "rol", "eenheid")).lower()
    return (
        f'<article id="{_e(persona.code)}" class="persona" '
        f'data-org="{_e(m["organisatie"])}" '
        f'data-instances="{_e("|".join(_instances(persona)))}" '
        f'data-search="{_e(search)}">'
        "<header>"
        f'<p class="code">{_e(persona.code)}</p>'
        f"<h{top}>{_e(m['naam'])}</h{top}>"
        f'<p class="rol">{_e(m["rol"])}</p>'
        f'<p class="org">{_e(m["organisatie"])} &middot; {_e(m["eenheid"])}</p>'
        "</header>"
        f"{_facts(m)}{grips_html}"
        f'<div class="body">{render(body, top - 1)}</div>'
        "</article>"
    )


def _chips(kind: str, values: list[str]) -> str:
    return "".join(
        f'<label class="chip"><input type="checkbox" data-kind="{kind}" '
        f'value="{_e(v)}"><span>{_e(v)}</span></label>'
        for v in values
    )


def build_html(
    intro: str,
    personas: list[Persona],
) -> str:
    """Render the standalone book: one file with its own script."""
    render = _renderer({p.code for p in personas})
    present = {str(p.meta["organisatie"]) for p in personas}
    orgs = [o for o in ORGANISATIONS if o in present]
    orgs += sorted(present - set(orgs))
    instances = sorted({i for p in personas for i in _instances(p)})

    nav_groups = []
    for org in orgs:
        items = "".join(
            f'<li data-code="{_e(p.code)}"><a href="#{_e(p.code)}">'
            f'<span class="code">{_e(p.code)}</span> {_e(p.meta["naam"])}</a></li>'
            for p in personas
            if p.meta["organisatie"] == org
        )
        nav_groups.append(
            f'<section class="navgroup"><h2>{_e(org)}</h2><ul>{items}</ul></section>'
        )

    return (
        TEMPLATE.replace("{css}", CSS)
        .replace("{script}", f"<script>{JS}</script>")
        .replace("{count}", str(len(personas)))
        .replace("{org_chips}", _chips("org", orgs))
        .replace("{inst_chips}", _chips("inst", instances))
        .replace("{nav}", "".join(nav_groups))
        .replace("{intro}", render(intro, 0) if intro.strip() else "")
        .replace("{articles}", "".join(_article(p, render) for p in personas))
    )


def generate(input_dir: Path, output: Path) -> int:
    intro, personas = load_personas(input_dir)
    html = build_html(intro, personas)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    return len(personas)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    try:
        count = generate(args.input, args.output)
    except PersonaError as exc:
        print(f"personaboek: {exc}", file=sys.stderr)
        return 1
    print(f"personaboek: {count} persona's naar {args.output}")
    return 0


CSS = """
:root{--accent:#154273;--accent-contrast:#fff;--bg:#fff;--surface:#f3f3f3;--text:#1a1a1a;
--muted:#555;--border:#cfcfcf;--warn-bg:#fff3cd;--warn-text:#5c4300;--focus:#e17000;
--s1:.25rem;--s2:.5rem;--s3:.75rem;--s4:1rem;--s6:1.5rem;--s8:2rem;
--font:"RijksSansVF","Rijksoverheid Sans",system-ui,-apple-system,"Segoe UI",sans-serif}
@media (prefers-color-scheme:dark){:root{--accent:#8fb8e8;--accent-contrast:#0b1f33;--bg:#14181d;
--surface:#1d232a;--text:#eceff2;--muted:#a9b3bd;--border:#38424d;--warn-bg:#4a3a0a;--warn-text:#ffe29a}}
*{box-sizing:border-box}
body{margin:0;font:1rem/1.6 var(--font);color:var(--text);background:var(--bg);
display:grid;grid-template-columns:20rem 1fr;min-height:100vh}
a{color:var(--accent)}
:focus-visible{outline:3px solid var(--focus);outline-offset:2px}
.skip{position:absolute;left:-999px}
.skip:focus{left:var(--s2);top:var(--s2);background:var(--bg);padding:var(--s2);z-index:9}
.sidebar{position:sticky;top:0;height:100vh;overflow:auto;background:var(--surface);
border-right:1px solid var(--border);padding:var(--s4)}
.sidebar h1{font-size:1.25rem;margin:0 0 var(--s4);color:var(--accent)}
.filters fieldset{border:0;margin:0 0 var(--s4);padding:0}
.filters legend,.filters label.q{font-weight:700;font-size:.875rem;padding:0;margin-bottom:var(--s1)}
.filters label.q{display:block}
.filters input[type=search]{width:100%;font:inherit;padding:var(--s2);border:1px solid var(--border);
border-radius:4px;background:var(--bg);color:var(--text)}
.chip{display:inline-block;margin:0 var(--s1) var(--s1) 0;position:relative}
.chip input{position:absolute;opacity:0}
.chip span{display:inline-block;padding:var(--s1) var(--s3);border:1px solid var(--accent);
border-radius:999px;font-size:.875rem;cursor:pointer;color:var(--accent)}
.chip input:checked+span{background:var(--accent);color:var(--accent-contrast)}
.chip input:focus-visible+span{outline:3px solid var(--focus);outline-offset:2px}
.navgroup h2{font-size:.875rem;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);
margin:var(--s4) 0 var(--s1)}
.navgroup[hidden],.navgroup li[hidden]{display:none}
.navgroup ul{list-style:none;margin:0;padding:0}
.navgroup a{display:block;padding:var(--s1) var(--s2);border-radius:4px;text-decoration:none;color:var(--text)}
.navgroup a:hover{background:var(--border)}
.navgroup .code{font-family:ui-monospace,monospace;font-size:.8125rem;color:var(--accent);font-weight:700}
#status{font-size:.875rem;color:var(--muted)}
main{padding:var(--s8);max-width:60rem}
.intro{margin-bottom:var(--s8)}
article.persona{border-top:4px solid var(--accent);padding-top:var(--s4);margin-bottom:calc(var(--s8)*2)}
article[hidden]{display:none}
article header .code{font-family:ui-monospace,monospace;font-weight:700;color:var(--accent);margin:0}
article header h2{font-size:2rem;margin:0;line-height:1.2}
article header .rol{font-size:1.25rem;margin:var(--s1) 0 0}
article header .org{color:var(--muted);margin:var(--s1) 0 var(--s4)}
.facts{display:grid;grid-template-columns:10rem 1fr;gap:var(--s2) var(--s4);background:var(--surface);
padding:var(--s4);border-radius:6px;margin:0 0 var(--s6)}
.facts dt{font-weight:700}.facts dd{margin:0}
.muted{color:var(--muted)}
.badge{display:inline-block;font-size:.75rem;font-weight:700;padding:0 var(--s2);border-radius:999px;
border:1px solid var(--border);background:var(--bg)}
.badge-warn{background:var(--warn-bg);color:var(--warn-text);border-color:transparent}
.cards{list-style:none;margin:0 0 var(--s6);padding:0;display:grid;gap:var(--s4);
grid-template-columns:repeat(auto-fill,minmax(16rem,1fr))}
.card{border:1px solid var(--border);border-radius:6px;padding:var(--s3) var(--s4)}
.card h4{margin:0 0 var(--s1);font-size:1rem;color:var(--accent)}
.card p{margin:0 0 var(--s2)}.card .lookin{margin:var(--s3) 0 0;font-size:.875rem}.card dl{margin:0;font-size:.875rem}
.card dt{font-weight:700;margin-top:var(--s2)}.card dd{margin:0}
.grips h3{margin:0 0 var(--s3)}
table{border-collapse:collapse;width:100%;margin:var(--s4) 0;font-size:.9375rem;display:block;overflow-x:auto}
th,td{border:1px solid var(--border);padding:var(--s2) var(--s3);text-align:left;vertical-align:top}
th{background:var(--surface)}
code{font-family:ui-monospace,monospace;font-size:.875em;background:var(--surface);
padding:0 var(--s1);border-radius:3px}
h1,h2,h3{line-height:1.25}
@media (max-width:50rem){body{display:block}.sidebar{position:static;height:auto}
main{padding:var(--s4)}.facts{grid-template-columns:1fr}}
@media print{body{display:block;color:#000;background:#fff;font-size:11pt}
.sidebar,.skip{display:none!important}main{padding:0;max-width:none}
article.persona{break-before:page;border-top:0;margin:0}article[hidden]{display:block!important}
.intro{break-after:page}a{color:#000}.facts,.card{break-inside:avoid}}
"""

JS = """
(function(){
var q=document.getElementById('q'),status=document.getElementById('status');
var boxes=[].slice.call(document.querySelectorAll('.filters input[type=checkbox]'));
var arts=[].slice.call(document.querySelectorAll('article.persona'));
function apply(){
var term=q.value.trim().toLowerCase();
var orgs=boxes.filter(function(b){return b.checked&&b.dataset.kind==='org'}).map(function(b){return b.value});
var inst=boxes.filter(function(b){return b.checked&&b.dataset.kind==='inst'}).map(function(b){return b.value});
var shown=0;
arts.forEach(function(a){
var ok=(!term||a.dataset.search.indexOf(term)>-1)
&&(!orgs.length||orgs.indexOf(a.dataset.org)>-1)
&&(!inst.length||a.dataset.instances.split('|').some(function(i){return inst.indexOf(i)>-1}));
a.hidden=!ok;
var li=document.querySelector('li[data-code="'+a.id+'"]');if(li)li.hidden=!ok;
if(ok)shown++;
});
document.querySelectorAll('.navgroup').forEach(function(g){
g.hidden=!g.querySelector('li:not([hidden])');});
status.textContent=shown+' van '+arts.length+' persona\\u2019s';
}
q.addEventListener('input',apply);
boxes.forEach(function(b){b.addEventListener('change',apply)});
apply();
fetch('config.json').then(function(r){return r.json()}).then(function(c){
document.querySelectorAll('a.grip-link').forEach(function(a){
var i=(c.instances||[]).filter(function(x){return x.name===a.dataset.instance})[0];
if(i&&i.url){a.href=i.url;a.hidden=false}});
}).catch(function(){});
})();
"""

TEMPLATE = """<!doctype html>
<html lang="nl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>Personaboek</title>
<style>{css}</style>
</head>
<body>
<a class="skip" href="#inhoud">Naar de inhoud</a>
<header class="sidebar">
<h1>Personaboek</h1>
<form class="filters" role="search" aria-label="Persona's filteren" onsubmit="return false">
<p><label class="q" for="q">Zoeken</label><input id="q" type="search" autocomplete="off"></p>
<fieldset><legend>Organisatie</legend>{org_chips}</fieldset>
<fieldset><legend>Grip-instantie</legend>{inst_chips}</fieldset>
<p id="status" role="status" aria-live="polite">{count} persona&rsquo;s</p>
</form>
<nav aria-label="Persona's">{nav}</nav>
</header>
<main id="inhoud">
<section class="intro">{intro}</section>
{articles}
</main>
{script}
</body>
</html>
"""

if __name__ == "__main__":
    raise SystemExit(main())
