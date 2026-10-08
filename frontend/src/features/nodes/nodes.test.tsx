import { useState } from 'react';
import { waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { texts } from '@/features/team/ui/testing';
import { renderApp } from '@/test/utils';
import type { NodeLookup } from './api';
import { AssignmentContextView } from './AssignmentContextView';
import { edgeTypeLabel, isNodeUri, nodeTypeLabel, uriHost } from './labels';
import { NodeCard } from './NodeCard';
import { NodeDetailSheet } from './NodeDetailSheet';
import { NodePathView } from './NodePathView';
import { NodePicker } from './NodePicker';
import { toTree } from './pathTree';
import { originLine, stepsText } from './summary';

afterEach(() => vi.unstubAllGlobals());

const BASE = 'https://corpus.voorbeeldministerie.example/id/node';
const INSTRUMENT = `${BASE}/instrument`;
const GOAL = `${BASE}/doel`;
const MOTION = `${BASE}/motie`;
const AGREEMENT = `${BASE}/akkoord`;
const ELSEWHERE = 'https://corpus.anderministerie.example/id/node/doel';

/** An instrument under a goal under one political input. */
const ONE_INPUT: NodeLookup = {
  uri: INSTRUMENT,
  resolved: true,
  corpus_name: 'Corpus Voorbeeldministerie',
  node: {
    uri: INSTRUMENT,
    type: 'instrument',
    title: 'Opdracht bouwsteen Alfa',
    description: 'Fictieve omschrijving van het instrument.',
    status: 'actief',
    managing_organisation: { name: 'Voorbeeldministerie' },
    peildatum: '2026-10-08',
  },
  origins: [{ uri: MOTION, title: 'Motie over hergebruik' }],
  steps_to_origin: 2,
  paths: [
    {
      steps: [
        { uri: INSTRUMENT, type: 'instrument', title: 'Opdracht bouwsteen Alfa', resolvable: true, edge_type: 'implementeert' },
        { uri: GOAL, type: 'doel', title: 'Hergebruik van bouwstenen', resolvable: true, edge_type: 'vloeit_voort_uit' },
        { uri: MOTION, type: 'politieke_input', title: 'Motie over hergebruik', resolvable: true },
      ],
    },
  ],
};

const TWO_INPUTS: NodeLookup = {
  ...ONE_INPUT,
  origins: [
    { uri: MOTION, title: 'Motie over hergebruik' },
    { uri: AGREEMENT, title: 'Passage in het akkoord' },
  ],
  paths: [
    ...(ONE_INPUT.paths ?? []),
    {
      steps: [
        { uri: INSTRUMENT, type: 'instrument', title: 'Opdracht bouwsteen Alfa', resolvable: true, edge_type: 'implementeert' },
        { uri: GOAL, type: 'doel', title: 'Hergebruik van bouwstenen', resolvable: true, edge_type: 'draagt_bij_aan' },
        { uri: AGREEMENT, type: 'politieke_input', title: 'Passage in het akkoord', resolvable: true },
      ],
    },
  ],
};

/** The goal above, linked on the same assignment. */
const PARENT: NodeLookup = {
  uri: GOAL,
  resolved: true,
  node: { uri: GOAL, type: 'doel', title: 'Hergebruik van bouwstenen', status: 'actief' },
  origins: [{ uri: MOTION, title: 'Motie over hergebruik' }],
  steps_to_origin: 1,
  paths: [
    {
      steps: [
        { uri: GOAL, type: 'doel', title: 'Hergebruik van bouwstenen', resolvable: true, edge_type: 'vloeit_voort_uit' },
        { uri: MOTION, type: 'politieke_input', title: 'Motie over hergebruik', resolvable: true },
      ],
    },
  ],
};

const UNDER_PARENT: NodeLookup = {
  ...ONE_INPUT,
  falls_under: { uri: GOAL, title: 'Hergebruik van bouwstenen' },
};

/** A node of a second corpus whose chain runs into yet another one. */
const SECOND_CORPUS: NodeLookup = {
  uri: 'https://corpus.tweedeministerie.example/id/node/maatregel',
  resolved: true,
  corpus_name: 'Corpus Tweede Ministerie',
  node: {
    uri: 'https://corpus.tweedeministerie.example/id/node/maatregel',
    type: 'maatregel',
    title: 'Een maatregel elders',
    status: 'vervallen',
    managing_organisation: { name: 'Tweede Ministerie' },
  },
  origins: [],
  paths: [
    {
      steps: [
        { uri: 'https://corpus.tweedeministerie.example/id/node/maatregel', type: 'maatregel', title: 'Een maatregel elders', resolvable: true, edge_type: 'draagt_bij_aan' },
        { uri: ELSEWHERE, external: true, resolvable: false, corpus_name: null },
      ],
    },
  ],
};

const UNRESOLVED: NodeLookup = {
  uri: ELSEWHERE,
  resolved: false,
  problem: 'Voor deze URI is geen corpus gekoppeld aan deze instantie.',
};

function cardText(container: ParentNode): string {
  return container.querySelector('nldd-card')?.textContent ?? '';
}

describe('labels', () => {
  it('names the shared node and edge types in Dutch', () => {
    expect(nodeTypeLabel('politieke_input')).toBe('Politieke input');
    expect(edgeTypeLabel('draagt_bij_aan')).toBe('draagt bij aan');
    expect(nodeTypeLabel('https://corpus.example/def/type/pilot_project')).toBe('Pilot project');
  });

  it('accepts only absolute web addresses as a node URI', () => {
    expect(isNodeUri(INSTRUMENT)).toBe(true);
    expect(isNodeUri('corpus.example/id/node/1')).toBe(false);
    expect(isNodeUri('javascript:alert(1)')).toBe(false);
    expect(uriHost(INSTRUMENT)).toBe('corpus.voorbeeldministerie.example');
  });
});

describe('originLine', () => {
  it('names the political input, counts the others, and gives the distance', () => {
    expect(originLine(ONE_INPUT)).toBe('Komt voort uit: Motie over hergebruik');
    expect(stepsText(ONE_INPUT)).toBe('2 stappen');
    expect(originLine(TWO_INPUTS)).toBe('Komt voort uit: Motie over hergebruik, en 1 andere');
    expect(stepsText(PARENT)).toBe('1 stap');
  });

  it('says what a node falls under instead of repeating the chain', () => {
    expect(originLine(UNDER_PARENT)).toBe('Valt onder: Hergebruik van bouwstenen');
    expect(stepsText(UNDER_PARENT)).toBe('');
  });

  it('says when the chain leaves for another corpus or starts here', () => {
    expect(originLine(SECOND_CORPUS)).toBe('Loopt door in een ander corpus');
    expect(
      originLine({ uri: MOTION, resolved: true, node: { uri: MOTION, type: 'politieke_input', title: 'Motie' } }),
    ).toBe('Dit is een politieke input');
  });
});

describe('NodeCard', () => {
  it('shows only type, title, organisation and where it comes from', () => {
    const { container } = renderApp(<NodeCard item={ONE_INPUT} onOpen={() => {}} />);
    const card = container.querySelector('nldd-card');
    expect(card?.hasAttribute('button')).toBe(true);
    expect(card?.getAttribute('accessible-label')).toBe('Bekijk Opdracht bouwsteen Alfa');
    // The usual status is not worth a tag.
    expect(texts(container, 'nldd-badge')).toEqual(['Instrument']);
    expect(texts(container, 'nldd-title')).toEqual(['Opdracht bouwsteen Alfa']);
    expect(cardText(container)).toContain('Voorbeeldministerie');
    expect(cardText(container)).toContain('Komt voort uit: Motie over hergebruik (2 stappen)');
    // No description, no URI and no chain on the card.
    expect(cardText(container)).not.toContain('Fictieve omschrijving');
    expect(cardText(container)).not.toContain('https://');
    expect(container.querySelector('ol')).toBeNull();
  });

  it('counts a second political input instead of listing it', () => {
    const { container } = renderApp(<NodeCard item={TWO_INPUTS} />);
    expect(cardText(container)).toContain('Motie over hergebruik, en 1 andere');
    expect(cardText(container)).not.toContain('Passage in het akkoord');
    // Without a handler the card is not a button.
    expect(container.querySelector('nldd-card')?.hasAttribute('button')).toBe(false);
  });

  it('marks a node under another linked node in one line', () => {
    const { container } = renderApp(<NodeCard item={UNDER_PARENT} />);
    expect(cardText(container)).toContain('Valt onder: Hergebruik van bouwstenen');
    expect(cardText(container)).not.toContain('Komt voort uit');
  });

  it('tags a status that is not the usual one, for a node of a second corpus', () => {
    const { container } = renderApp(<NodeCard item={SECOND_CORPUS} />);
    expect(texts(container, 'nldd-badge')).toEqual(['Maatregel', 'vervallen']);
    expect(cardText(container)).toContain('Tweede Ministerie');
    expect(cardText(container)).toContain('Loopt door in een ander corpus');
  });

  it('keeps an unresolved URI as a card, with the URI and the reason', () => {
    const { container } = renderApp(<NodeCard item={UNRESOLVED} onOpen={() => {}} />);
    expect(texts(container, 'nldd-badge')).toEqual(['Niet op te halen']);
    expect(cardText(container)).toContain(ELSEWHERE);
    expect(cardText(container)).toContain('geen corpus gekoppeld');
  });

  it('leaves the reason out when one notice above says it', () => {
    const { container } = renderApp(<NodeCard item={UNRESOLVED} hideReason />);
    expect(cardText(container)).toContain(ELSEWHERE);
    expect(cardText(container)).not.toContain('geen corpus gekoppeld');
  });

  it('has the same shape while it is being looked up', () => {
    const { container } = renderApp(<NodeCard item={{ uri: '', resolved: false }} pending onOpen={() => {}} />);
    const card = container.querySelector('nldd-card');
    expect(card?.getAttribute('aria-busy')).toBe('true');
    expect(card?.hasAttribute('button')).toBe(false);
    expect(cardText(container)).toBe('Bezig met ophalen');
  });
});

describe('toTree', () => {
  it('keeps a single path whole', () => {
    const tree = toTree(ONE_INPUT.paths ?? []);
    expect(tree.trunk.map((step) => step.type)).toEqual(['instrument', 'doel', 'politieke_input']);
    expect(tree.branches).toEqual([]);
  });

  it('tells the shared steps once and gives each end point its own way', () => {
    const tree = toTree(TWO_INPUTS.paths ?? []);
    expect(tree.trunk.map((step) => step.title)).toEqual([
      'Opdracht bouwsteen Alfa',
      'Hergebruik van bouwstenen',
    ]);
    // Where the ways part, the relation belongs to each branch.
    expect(tree.trunk[1]?.edge_type).toBeNull();
    expect(tree.branches.map((branch) => branch.lead)).toEqual(['vloeit_voort_uit', 'draagt_bij_aan']);
    expect(tree.branches.map((branch) => branch.steps.map((step) => step.title))).toEqual([
      ['Motie over hergebruik'],
      ['Passage in het akkoord'],
    ]);
  });

  it('gives nothing for a node without paths', () => {
    expect(toTree([])).toEqual({ trunk: [], branches: [] });
  });
});

describe('NodePathView', () => {
  const rows = (list: Element) =>
    [...list.querySelectorAll(':scope > li')].map((row) => ({
      relation: row.classList.contains('grip-path__relation'),
      classes: row.className,
      text: row.textContent ?? '',
    }));

  it('draws one path as steps on a rail with the relation between them', () => {
    const onStep = vi.fn();
    const { container } = renderApp(
      <NodePathView paths={ONE_INPUT.paths ?? []} currentUri={INSTRUMENT} onStep={onStep} />,
    );
    const list = container.querySelector('ol.grip-path') as HTMLElement;
    expect(list.getAttribute('aria-label')).toBe('Pad naar Motie over hergebruik');
    const all = rows(list);
    expect(all.map((row) => row.relation)).toEqual([false, true, false, true, false]);
    expect(all[1]?.text).toBe('implementeert');
    expect(all[3]?.text).toBe('vloeit voort uit');
    // Every step has the same three parts in the same order: kind, title, organisation.
    for (const step of list.querySelectorAll('.grip-path__step')) {
      expect([...step.querySelectorAll('.grip-path__body > nldd-text')].map((el) => el.className)).toEqual([
        'grip-path__kind',
        'grip-path__title',
        'grip-path__by',
      ]);
      expect(step.querySelectorAll('.grip-path__rail')).toHaveLength(3);
    }
    // The node itself is marked quietly and is not a control; the end is marked as the origin.
    expect(all[0]?.classes).toContain('grip-path__step--current');
    expect(all[0]?.classes).toContain('grip-path__step--first');
    expect(all[0]?.text).toBe('InstrumentOpdracht bouwsteen AlfaDeze node');
    expect(list.querySelector('.grip-path__step--current button')).toBeNull();
    expect(all[4]?.classes).toContain('grip-path__step--end');
    expect(all[4]?.classes).toContain('grip-path__step--last');
    expect(all[4]?.text).toBe('Politieke inputMotie over hergebruikHerkomst');
    // No arrows and no parentheses.
    expect(list.textContent).not.toMatch(/[↓→(]/);
    // A step that can be opened is one control: the whole row.
    const buttons = [...list.querySelectorAll('button.grip-path__body')];
    expect(buttons.map((button) => button.getAttribute('aria-label'))).toEqual([
      'Doel: Hergebruik van bouwstenen. Bekijk',
      'Politieke input: Motie over hergebruik. Bekijk',
    ]);
    (buttons[0] as HTMLButtonElement).click();
    expect(onStep).toHaveBeenCalledWith(GOAL);
  });

  it('names the organisation only where it changes along the path', () => {
    const steps = [
      { uri: 'a', type: 'instrument', title: 'A', organisation_name: 'Voorbeeldgilde', edge_type: 'implementeert' },
      { uri: 'b', type: 'doel', title: 'B', organisation_name: 'Voorbeeldministerie', edge_type: 'vloeit_voort_uit' },
      { uri: 'c', type: 'politieke_input', title: 'C', organisation_name: 'Voorbeeldministerie' },
    ];
    const { container } = renderApp(<NodePathView paths={[{ steps }]} currentUri="a" onStep={() => {}} />);
    expect([...container.querySelectorAll('.grip-path__by')].map((el) => el.textContent)).toEqual([
      'Voorbeeldgilde',
      'Voorbeeldministerie',
      '',
    ]);
  });

  it('draws shared steps once and the ways to two political inputs next to each other', () => {
    const { container } = renderApp(
      <NodePathView paths={TWO_INPUTS.paths ?? []} currentUri={INSTRUMENT} onStep={() => {}} />,
    );
    const lists = [...container.querySelectorAll('ol.grip-path')];
    expect(lists.map((list) => list.getAttribute('aria-label'))).toEqual([
      'Wat alle paden delen',
      'Pad naar Motie over hergebruik',
      'Pad naar Passage in het akkoord',
    ]);
    // The goal is on the page once, not once per path.
    expect(container.textContent?.split('Hergebruik van bouwstenen')).toHaveLength(2);
    // The shared rail runs on below its last step; each branch starts with its relation.
    expect(lists[0]?.querySelector('.grip-path__step--last')).toBeNull();
    expect(rows(lists[1] as Element).map((row) => row.text)).toEqual([
      'vloeit voort uit',
      'Politieke inputMotie over hergebruikHerkomst',
    ]);
    expect(rows(lists[2] as Element)[0]?.text).toBe('draagt bij aan');
    const branches = container.querySelector('.grip-path-branches');
    expect(branches?.children).toHaveLength(2);
    expect([...(branches?.querySelectorAll('nldd-text[color="secondary"]') ?? [])]
      .map((el) => el.textContent)
      .filter((text) => text === 'Komt voort uit')).toHaveLength(2);
  });

  it('marks a step in another corpus with the corpus and the way out', () => {
    const { container } = renderApp(
      <NodePathView paths={SECOND_CORPUS.paths ?? []} currentUri={SECOND_CORPUS.uri} onStep={() => {}} />,
    );
    const list = container.querySelector('ol.grip-path') as HTMLElement;
    expect(list.getAttribute('aria-label')).toBe('Pad naar corpus.anderministerie.example');
    const link = list.querySelector('a.grip-path__body') as HTMLAnchorElement;
    expect(link.getAttribute('href')).toBe(ELSEWHERE);
    expect(link.getAttribute('target')).toBe('_blank');
    expect(link.textContent).toBe('Ander corpuscorpus.anderministerie.example');
    expect(link.querySelector('nldd-icon')?.getAttribute('icon')).toBe('external-link');
    // The end in another corpus is not called the origin: the way goes on there.
    expect(list.textContent).not.toContain('Herkomst');
  });

  it('opens a step in another corpus in the sheet when this instance can ask that corpus', () => {
    const onStep = vi.fn();
    const steps = [
      { uri: 'a', type: 'doel', title: 'A', resolvable: true, edge_type: 'draagt_bij_aan' },
      { uri: ELSEWHERE, external: true, resolvable: true, corpus_name: 'Corpus Anderministerie' },
    ];
    const { container } = renderApp(<NodePathView paths={[{ steps }]} currentUri="a" onStep={onStep} />);
    const button = container.querySelector('button.grip-path__body') as HTMLButtonElement;
    expect(button.textContent).toBe('Ander corpusCorpus Anderministerie');
    button.click();
    expect(onStep).toHaveBeenCalledWith(ELSEWHERE);
  });
});

describe('NodeDetailSheet', () => {
  const sheet = () => document.body.querySelector('nldd-sheet') as HTMLElement;

  it('says where the node lives, and shows its description, paths and reference', () => {
    renderApp(
      <NodeDetailSheet uri={INSTRUMENT} known={[TWO_INPUTS]} fetchNode={vi.fn()} scope="t" onClose={() => {}} />,
    );
    expect(sheet().hasAttribute('open')).toBe(true);
    // The corpus by name and the way to the node's own page, before anything else.
    expect(sheet().textContent).toContain('Uit Corpus Voorbeeldministerie');
    const open = sheet().querySelectorAll('nldd-link[text="Open in het corpus"]');
    expect(open).toHaveLength(1);
    expect(open[0]?.getAttribute('href')).toBe(INSTRUMENT);
    expect(sheet().textContent).toContain('Fictieve omschrijving van het instrument.');
    expect(sheet().querySelectorAll('ol.grip-path')).toHaveLength(3);
    expect(sheet().textContent).toContain(INSTRUMENT);
    expect(texts(sheet(), 'nldd-button')).toContain('Kopieer URI');
    expect(sheet().textContent).toContain('De keten is altijd de keten van nu');
  });

  it('says what a node falls under, and explains an unresolved one', () => {
    const { unmount } = renderApp(
      <NodeDetailSheet uri={INSTRUMENT} known={[UNDER_PARENT]} fetchNode={vi.fn()} scope="t" onClose={() => {}} />,
    );
    expect(sheet().textContent).toContain('valt onder Hergebruik van bouwstenen');
    unmount();
    renderApp(
      <NodeDetailSheet uri={ELSEWHERE} known={[UNRESOLVED]} fetchNode={vi.fn()} scope="t" onClose={() => {}} />,
    );
    expect(texts(sheet(), 'nldd-banner')).toEqual(['Deze node is niet op te halen']);
    expect(sheet().textContent).toContain(ELSEWHERE);
  });

  it('stays closed and asks nothing without a node', () => {
    const fetchNode = vi.fn(async () => PARENT);
    renderApp(
      <NodeDetailSheet uri={null} known={[ONE_INPUT]} fetchNode={fetchNode} scope="t" onClose={() => {}} />,
    );
    expect(sheet().hasAttribute('open')).toBe(false);
    expect(fetchNode).not.toHaveBeenCalled();
  });

  it('fetches a node the list does not hold', async () => {
    const fetchNode = vi.fn(async () => PARENT);
    renderApp(
      <NodeDetailSheet uri={GOAL} known={[ONE_INPUT]} fetchNode={fetchNode} scope="t" onClose={() => {}} />,
    );
    await waitFor(() => expect(fetchNode).toHaveBeenCalledWith(GOAL));
    await waitFor(() =>
      expect(sheet().querySelector('nldd-top-title-bar')?.getAttribute('text')).toBe(
        'Hergebruik van bouwstenen',
      ),
    );
    expect(sheet().querySelector('ol')?.getAttribute('aria-label')).toBe(
      'Pad naar Motie over hergebruik',
    );
  });
});

function mockRoutes(routes: Record<string, (url: URL) => unknown>) {
  const calls: string[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), 'http://test');
      calls.push(url.pathname + url.search);
      const answer = routes[url.pathname];
      if (!answer) {
        return new Response(JSON.stringify({ title: 'Niet gevonden', status: 404 }), {
          status: 404,
          headers: { 'Content-Type': 'application/problem+json' },
        });
      }
      return new Response(JSON.stringify(answer(url)), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }),
  );
  return calls;
}

describe('AssignmentContextView', () => {
  it('shows a card per linked node, the lower one marked instead of repeated', async () => {
    mockRoutes({
      '/api/assignments/a-1/context': () => ({
        peildatum: '2026-10-08',
        acceptance_date: '2026-06-03',
        items: [UNDER_PARENT, PARENT],
      }),
    });
    const { container } = renderApp(<AssignmentContextView assignmentId="a-1" count={2} />);
    // While loading: as many card shapes as there are linked nodes.
    expect(container.querySelectorAll('nldd-card[aria-busy="true"]')).toHaveLength(2);
    await waitFor(() => expect(container.querySelectorAll('nldd-card[button]')).toHaveLength(2));
    const [lower, upper] = [...container.querySelectorAll('nldd-card')].map((el) => el.textContent ?? '');
    expect(lower).toContain('Valt onder: Hergebruik van bouwstenen');
    expect(lower).not.toContain('Motie over hergebruik');
    expect(upper).toContain('Komt voort uit: Motie over hergebruik (1 stap)');
    // The peildatum is a small choice at the edge; the explanation is in the detail.
    const choices = [...container.querySelectorAll('select option')].map((el) => el.textContent);
    expect(choices[0]).toBe('Zoals het nu is');
    expect(choices[1]).toContain('Bij akkoord');
    expect(container.textContent).not.toContain('De keten is altijd');
    expect(container.querySelector('ol')).toBeNull();
  });

  it('says once that no corpus is connected, and still shows the references', async () => {
    mockRoutes({
      '/api/assignments/a-1/context': () => ({
        peildatum: '2026-10-08',
        notice: 'Er is geen corpus gekoppeld aan deze instantie, dus de context kan niet worden opgehaald.',
        items: [
          { uri: INSTRUMENT, resolved: false },
          { uri: ELSEWHERE, resolved: false },
        ],
      }),
    });
    const { container } = renderApp(<AssignmentContextView assignmentId="a-1" count={2} />);
    await waitFor(() => expect(texts(container, 'nldd-banner')).toHaveLength(1));
    expect(texts(container, 'nldd-banner')[0]).toContain('geen corpus gekoppeld');
    expect(texts(container, 'nldd-badge')).toEqual(['Niet op te halen', 'Niet op te halen']);
    expect(container.textContent).toContain(ELSEWHERE);
    // No peildatum to choose when nothing was accepted.
    expect(container.querySelector('select')).toBeNull();
  });

  it('asks nothing for an assignment without context', () => {
    const calls = mockRoutes({});
    const { container } = renderApp(<AssignmentContextView assignmentId="a-1" count={0} />);
    expect(texts(container, 'nldd-inline-dialog')).toEqual(['Deze opdracht heeft geen context']);
    expect(calls).toEqual([]);
  });
});

function Harness({ initial = [] }: { initial?: string[] }) {
  const [value, setValue] = useState<string[]>(initial);
  return <NodePicker value={value} onChange={setValue} />;
}

describe('NodePicker', () => {
  it('says so when no corpus is connected and still takes a pasted URI', async () => {
    mockRoutes({
      '/api/nodes/corpora': () => ({
        problem: 'Er is geen corpus gekoppeld aan deze instantie. Je kunt doorgaan zonder context.',
      }),
    });
    const { container } = renderApp(<Harness />);
    await waitFor(() =>
      expect(texts(container, 'nldd-banner[variant="neutral"]')[0]).toContain('geen corpus'),
    );
    expect(container.querySelector('nldd-search-field')).toBeNull();
    expect(texts(container, 'nldd-inline-dialog')).toContain('Nog geen context gekozen');
    expect(texts(container, 'nldd-button')).toContain('Voeg URI toe');
  });

  it('offers the search when a corpus can be asked, and searches nothing unasked', async () => {
    mockRoutes({
      '/api/nodes/corpora': () => ({
        corpora: [{ base_uri: 'https://corpus.voorbeeldministerie.example', name: 'Corpus Voorbeeldministerie', searchable: true }],
        problem: null,
      }),
    });
    const { container } = renderApp(<Harness />);
    await waitFor(() => expect(container.querySelector('nldd-search-field')).not.toBeNull());
    expect(container.textContent).toContain('Corpus: Corpus Voorbeeldministerie');
    expect(container.querySelector('nldd-table')).toBeNull();
  });

  it('lists the chosen nodes as the same cards, each with a way to remove it', async () => {
    mockRoutes({
      '/api/nodes/corpora': () => ({ problem: 'Er is geen corpus gekoppeld.' }),
      '/api/nodes/lookup': (url) =>
        url.searchParams.get('uri') === INSTRUMENT ? ONE_INPUT : UNRESOLVED,
    });
    const { container } = renderApp(<Harness initial={[INSTRUMENT, ELSEWHERE]} />);
    await waitFor(() => expect(container.textContent).toContain('Komt voort uit: Motie over hergebruik'));
    await waitFor(() => expect(container.textContent).toContain('geen corpus gekoppeld'));
    expect(container.querySelectorAll('nldd-card')).toHaveLength(2);
    const labels = [...container.querySelectorAll('nldd-button[text="Verwijder"]')].map((el) =>
      el.getAttribute('accessible-label'),
    );
    expect(labels[0]).toBe('Verwijder Opdracht bouwsteen Alfa uit de context');
    // The remove control sits above the card's own click-through.
    const lifted = container.querySelector('nldd-card [slot="footer"]') as HTMLElement;
    expect(lifted.style.zIndex).toBe('1');
  });
});
