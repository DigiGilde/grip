/**
 * How the editor draws the places of a text: a fact as a chip with its value,
 * and a passage still to write as tinted text.
 *
 * The stored text keeps the key ("{schaal}"); the chip only replaces how it
 * looks. The caret steps over a chip as over one character, so a value is
 * never edited as text: it changes where the fact is kept. A fact that is not
 * known yet reads as where to fill it.
 *
 * This is an extension to the CodeMirror view inside nldd-text-editor. The
 * design system has annotations for tinting, but those always carry a count
 * badge, which means nothing on an open place.
 */
import { RangeSetBuilder, StateEffect, StateField } from '@codemirror/state';
import {
  Decoration,
  EditorView,
  ViewPlugin,
  WidgetType,
  type DecorationSet,
  type ViewUpdate,
} from '@codemirror/view';
import type { TextFact } from './facts';

const setFacts = StateEffect.define<ReadonlyMap<string, TextFact>>();

const factsField = StateField.define<ReadonlyMap<string, TextFact>>({
  create: () => new Map(),
  update(value, transaction) {
    for (const effect of transaction.effects) if (effect.is(setFacts)) return effect.value;
    return value;
  },
});

const capitalised = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

class FactChip extends WidgetType {
  constructor(readonly fact: TextFact) {
    super();
  }

  override eq(other: FactChip): boolean {
    return (
      other.fact.key === this.fact.key &&
      other.fact.value === this.fact.value &&
      other.fact.instruction === this.fact.instruction
    );
  }

  override toDOM(): HTMLElement {
    const { fact } = this;
    const chip = document.createElement('span');
    chip.className = fact.value === null ? 'cm-grip-fact cm-grip-open' : 'cm-grip-fact';
    chip.textContent = fact.value ?? fact.instruction;
    // Where the value comes from, on hover and for a screen reader.
    chip.title = capitalised(fact.source);
    chip.setAttribute(
      'aria-label',
      fact.value === null ? fact.instruction : `${fact.value}, ${fact.source}`,
    );
    return chip;
  }

  override ignoreEvent(): boolean {
    return false;
  }
}

const openMark = Decoration.mark({ class: 'cm-grip-open' });
const PLACE = /\{([a-z_]+)\}|\[vul aan:[^\]\n]*\]/g;

function build(view: EditorView): { all: DecorationSet; atomic: DecorationSet } {
  const facts = view.state.field(factsField);
  const all = new RangeSetBuilder<Decoration>();
  const atomic = new RangeSetBuilder<Decoration>();
  for (const match of view.state.doc.toString().matchAll(PLACE)) {
    const from = match.index;
    const to = from + match[0].length;
    if (match[1] === undefined) {
      all.add(from, to, openMark);
      continue;
    }
    const fact = facts.get(match[1]);
    if (!fact) continue;
    const chip = Decoration.replace({ widget: new FactChip(fact) });
    all.add(from, to, chip);
    atomic.add(from, to, chip);
  }
  return { all: all.finish(), atomic: atomic.finish() };
}

const places = ViewPlugin.fromClass(
  class {
    all: DecorationSet;
    atomic: DecorationSet;

    constructor(view: EditorView) {
      ({ all: this.all, atomic: this.atomic } = build(view));
    }

    update(update: ViewUpdate) {
      const factsChanged = update.transactions.some((transaction) =>
        transaction.effects.some((effect) => effect.is(setFacts)),
      );
      if (update.docChanged || factsChanged) {
        ({ all: this.all, atomic: this.atomic } = build(update.view));
      }
    }
  },
  {
    decorations: (plugin) => plugin.all,
    provide: (plugin) =>
      EditorView.atomicRanges.of((view) => view.plugin(plugin)?.atomic ?? Decoration.none),
  },
);

// The tint and the corner of the editor's own tokens, so a place looks like
// part of this editor. A known fact is quiet: a dotted line under the value.
const theme = EditorView.baseTheme({
  '.cm-grip-open': {
    backgroundColor: 'var(--_text-editor-annotation-token-background-color)',
    borderRadius: 'var(--_text-editor-token-corner-radius)',
    paddingBlock: 'var(--_text-editor-token-block-padding-fit)',
    boxDecorationBreak: 'clone',
    WebkitBoxDecorationBreak: 'clone',
  },
  '.cm-grip-fact': {
    borderBottom: 'var(--primitives-border-width-sm, thin) dotted currentColor',
    cursor: 'default',
  },
  '.cm-grip-fact.cm-grip-open': {
    borderBottom: 'none',
    paddingInline: 'var(--_text-editor-token-inline-padding)',
  },
});

const installed = new WeakSet<EditorView>();

/** Draw the places of the text in this view, with these facts. */
export function showPlaces(view: EditorView, facts: readonly TextFact[]): void {
  const byKey = new Map(facts.map((fact) => [fact.key, fact]));
  if (!installed.has(view)) {
    installed.add(view);
    // On its own: a field added in a transaction does not see that
    // transaction's other effects.
    view.dispatch({ effects: StateEffect.appendConfig.of([factsField, places, theme]) });
  }
  view.dispatch({ effects: setFacts.of(byKey) });
}
