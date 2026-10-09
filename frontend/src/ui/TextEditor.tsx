/**
 * The one editor for text that is stored with marks and shown formatted: a
 * vacancy text, a section of a quote, a standard text.
 *
 * It is the design system's text editor (nldd-text-editor): the text stays
 * plain text with marks, the formatting shows while you write and the marks
 * themselves stand dimmed beside it. The editor has no toolbar of its own;
 * this component gives it one with exactly the formats the text can hold,
 * and brings whatever is typed or pasted back to those (see ./text/marks).
 * A person never has to type a mark.
 *
 * Passages a standard text leaves open, "[vul aan: ...]", are tinted and
 * counted next to the toolbar with a way to step to the next one. A fact the
 * text names by key ("{schaal}") shows as its value and is not typed over; one
 * that is not known yet counts as open (see ./text/facts).
 */
import { useEffect, useImperativeHandle, useRef, useState, type ReactNode, type Ref } from 'react';
import type { EditorView } from '@codemirror/view';
import { orUndef, useNlddEvent } from '@/components/nldd/events';
import { Button } from './Button';
import { nextPlaceToFill, placesToFill, type PlaceToFill, type TextFact } from './text/facts';
import { toStored, type TextMarks } from './text/marks';

if (import.meta.env.MODE !== 'test') void import('./text/registerEditor');

interface ActiveFormats {
  bold: boolean;
  italic: boolean;
  bulletList: boolean;
  orderedList: boolean;
  heading: number;
}

const NOTHING: ActiveFormats = {
  bold: false,
  italic: false,
  bulletList: false,
  orderedList: false,
  heading: 0,
};

/** The part of nldd-text-editor this component talks to. */
interface EditorElement extends HTMLElement {
  value: string;
  updateComplete?: Promise<unknown>;
  toggleBold(): void;
  toggleItalic(): void;
  toggleHeading(level: number): void;
  setList(type: 'none' | 'bullet' | 'ordered'): void;
  focus(): void;
  replaceRange?(from: number, to: number, text: string): void;
  getSelection?(): { start: number; end: number; quote: string; empty: boolean };
  view?: {
    state: { doc: { toString(): string }; selection: { main: { head: number } } };
    dispatch(spec: { selection: { anchor: number; head: number }; scrollIntoView: boolean }): void;
  };
}

export interface TextEditorHandle {
  /** Puts the caret on the n-th passage still to fill (from 0), selected. */
  goToOpenPlace(index: number): void;
  /** What is selected now, in offsets of the text; null without a selection. */
  selection(): { start: number; end: number; text: string } | null;
  /** Writes `text` in the place of an open place; false when that place is gone. */
  fillPlace(place: PlaceToFill, text: string): boolean;
  focus(): void;
}

interface TextEditorProps {
  label: string;
  /** The text in its stored form. */
  value: string;
  onChange: (stored: string) => void;
  /** What this text can hold; the toolbar offers exactly that. */
  marks: TextMarks;
  hint?: string;
  optional?: boolean;
  required?: boolean;
  invalid?: boolean;
  /** How high the editor opens; it grows with the text. */
  rows?: number;
  /** Not to be edited now, for instance while a proposal is being written. */
  disabled?: boolean;
  /** Count the passages "[vul aan: ...]" and offer to step through them. */
  showOpenPlaces?: boolean;
  /** What the text can name by key; each shows as its value. */
  facts?: readonly TextFact[];
  /** Ask for a proposal for a passage still to write; without it nothing is offered. */
  onPropose?: (place: PlaceToFill) => void;
  proposing?: boolean;
  /** A proposal that waits for an answer, shown above the text. */
  proposal?: ReactNode;
  ref?: Ref<TextEditorHandle>;
}

const NO_FACTS: readonly TextFact[] = [];

function ToolButton({
  text,
  label,
  active,
  onPress,
}: {
  text: string;
  label: string;
  active: boolean;
  onPress: () => void;
}) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'click', onPress);
  return (
    <nldd-toggle-button
      ref={ref}
      type="button"
      size="sm"
      text={text}
      accessible-label={label}
      selected={orUndef(active)}
    />
  );
}

export function TextEditor({
  label,
  value,
  onChange,
  marks,
  hint,
  optional,
  required,
  invalid,
  rows = 8,
  disabled,
  showOpenPlaces,
  facts = NO_FACTS,
  onPropose,
  proposing,
  proposal,
  ref,
}: TextEditorProps) {
  const editor = useRef<EditorElement>(null);
  const [active, setActive] = useState<ActiveFormats>(NOTHING);
  // What this component last handed up. A value that differs came from
  // outside (a reload, a conflict) and replaces what the editor holds.
  const handedUp = useRef(value);

  useEffect(() => {
    const el = editor.current;
    if (!el) return;
    if (value !== handedUp.current || el.value === undefined || el.value === '') {
      if (el.value !== value) el.value = value;
      handedUp.current = value;
    }
  }, [value]);

  // Open places are tinted and facts drawn as their value, by an extension
  // to the editor's view. It is handed the facts again when one changes.
  const factsKey = facts.map((fact) => `${fact.key}=${fact.value ?? ''}`).join('\u0000');
  const latestFacts = useRef(facts);
  useEffect(() => {
    latestFacts.current = facts;
  });
  useEffect(() => {
    const el = editor.current;
    if (!el || !showOpenPlaces) return;
    let gone = false;
    void (async () => {
      await el.updateComplete;
      const view = el.view as unknown as EditorView | undefined;
      if (gone || !view) return;
      const { showPlaces } = await import('./text/factPlaces');
      if (!gone) showPlaces(view, latestFacts.current);
    })();
    return () => {
      gone = true;
    };
  }, [factsKey, showOpenPlaces]);

  useNlddEvent(editor, 'input', (event) => {
    const detail = (event as CustomEvent<{ value?: string }>).detail;
    const raw = typeof detail?.value === 'string' ? detail.value : (editor.current?.value ?? '');
    const stored = toStored(raw, marks);
    handedUp.current = stored;
    onChange(stored);
  });
  // On leaving the field the editor shows what is stored: a pasted mark the
  // text does not know has become the nearest one it does.
  useNlddEvent(editor, 'change', () => {
    const el = editor.current;
    if (!el) return;
    const stored = toStored(el.value ?? '', marks);
    if (stored !== el.value) el.value = stored;
  });
  useNlddEvent(editor, 'nldd-text-editor-state', (event) => {
    const formats = (event as CustomEvent<{ active?: ActiveFormats }>).detail?.active;
    if (formats) setActive(formats);
  });

  function select(place: { start: number; end: number }) {
    const el = editor.current;
    if (!el?.view) return;
    el.view.dispatch({
      selection: { anchor: place.start, head: place.end },
      scrollIntoView: true,
    });
    el.focus();
  }

  function goTo(index: number) {
    const text = editor.current?.view?.state.doc.toString();
    if (text === undefined) return;
    const all = placesToFill(text, facts);
    const place = all[index % Math.max(all.length, 1)];
    if (place) select(place);
  }

  // The next place after the caret: a place that was just filled is gone
  // from the list, so a counter of presses would skip the one after it.
  function next(only?: PlaceToFill['kind']): PlaceToFill | null {
    const view = editor.current?.view;
    if (!view) return null;
    const text = view.state.doc.toString();
    const { head } = view.state.selection.main;
    const all = placesToFill(text, facts);
    const here = all.find((place) => place.start <= head && head <= place.end);
    if (only) {
      // The place the caret is on, or the first of that kind after it.
      if (here?.kind === only) return here;
      const wanted = all.filter((place) => place.kind === only);
      return wanted.find((place) => place.start >= head) ?? wanted[0] ?? null;
    }
    return nextPlaceToFill(text, facts, here ? here.end : head);
  }

  function goToNext() {
    const place = next();
    if (place) select(place);
  }

  function propose() {
    const place = next('prose');
    if (!place) return;
    select(place);
    onPropose?.(place);
  }

  useImperativeHandle(ref, () => ({
    goToOpenPlace: goTo,
    selection: () => {
      const picked = editor.current?.getSelection?.();
      if (!picked || picked.empty) return null;
      return { start: picked.start, end: picked.end, text: picked.quote };
    },
    fillPlace: (place, text) => {
      const el = editor.current;
      const doc = el?.view?.state.doc.toString();
      if (!el || doc === undefined || typeof el.replaceRange !== 'function') return false;
      // The text may have moved since the proposal was asked for.
      const at =
        doc.slice(place.start, place.end) === place.text ? place.start : doc.indexOf(place.text);
      if (at < 0) return false;
      el.replaceRange(at, at + place.text.length, text);
      return true;
    },
    focus: () => editor.current?.focus(),
  }));

  const open = showOpenPlaces ? placesToFill(value, facts) : [];
  const canPropose = Boolean(onPropose) && open.some((place) => place.kind === 'prose');
  function press(command: (el: EditorElement) => void) {
    const el = editor.current;
    if (el && typeof el.toggleBold === 'function') command(el);
  }

  return (
    <nldd-form-field
      label={label}
      optional={orUndef(optional)}
      {...(hint ? { 'supporting-label': hint } : {})}
    >
      <nldd-container gap="8">
        <nldd-container layout="wrap" gap="4" vertical-alignment="center">
          {marks.heading ? (
            <ToolButton
              text="Kop"
              label="Maak van deze regel een kop"
              active={active.heading > 0}
              onPress={() => press((el) => el.toggleHeading(marks.heading ?? 2))}
            />
          ) : null}
          <ToolButton
            text="Lijst"
            label="Maak van deze regels een lijst"
            active={active.bulletList}
            onPress={() => press((el) => el.setList(active.bulletList ? 'none' : 'bullet'))}
          />
          {marks.numbered ? (
            <ToolButton
              text="Genummerd"
              label="Maak van deze regels een genummerde lijst"
              active={active.orderedList}
              onPress={() => press((el) => el.setList(active.orderedList ? 'none' : 'ordered'))}
            />
          ) : null}
          {marks.strong ? (
            <ToolButton
              text="Vet"
              label="Zet de selectie vet"
              active={active.bold}
              onPress={() => press((el) => el.toggleBold())}
            />
          ) : null}
          <ToolButton
            text="Cursief"
            label="Zet de selectie cursief"
            active={active.italic}
            onPress={() => press((el) => el.toggleItalic())}
          />
          {open.length > 0 ? (
            <>
              <nldd-spacer />
              <nldd-text size="sm" color="secondary">
                {open.length === 1
                  ? 'Nog 1 plek in te vullen'
                  : `Nog ${open.length} plekken in te vullen`}
              </nldd-text>
              {canPropose ? (
                <Button size="sm" text="Stel voor" loading={proposing} onClick={propose} />
              ) : null}
              <Button size="sm" text="Ga naar de volgende" onClick={goToNext} />
            </>
          ) : null}
        </nldd-container>
        {proposal}
        <nldd-text-editor
          ref={editor}
          appearance="input-field"
          accessible-label={label}
          rows={rows}
          required={orUndef(required)}
          invalid={orUndef(invalid)}
          disabled={orUndef(disabled)}
        />
      </nldd-container>
    </nldd-form-field>
  );
}
