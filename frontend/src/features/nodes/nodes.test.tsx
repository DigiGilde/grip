import { useState } from 'react';
import { waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { mockApi, texts } from '@/features/team/ui/testing';
import { renderApp } from '@/test/utils';
import { edgeTypeLabel, isNodeUri, nodeTypeLabel, uriHost } from './labels';
import { NodePicker } from './NodePicker';
import { ChainList } from './NodeSummary';

afterEach(() => vi.unstubAllGlobals());

const NODE_URI = 'https://corpus.voorbeeldministerie.example/id/node/n-1';

describe('labels', () => {
  it('names the shared node and edge types in Dutch', () => {
    expect(nodeTypeLabel('politieke_input')).toBe('Politieke input');
    expect(nodeTypeLabel('doel')).toBe('Doel');
    expect(edgeTypeLabel('draagt_bij_aan')).toBe('draagt bij aan');
  });

  it('reads the name of a type a corpus defined itself', () => {
    expect(nodeTypeLabel('https://corpus.example/def/type/pilot_project')).toBe('Pilot project');
    expect(edgeTypeLabel('https://corpus.example/def/relatie/financiert')).toBe('financiert');
  });

  it('accepts only absolute web addresses as a node URI', () => {
    expect(isNodeUri(NODE_URI)).toBe(true);
    expect(isNodeUri('  ' + NODE_URI + ' ')).toBe(true);
    expect(isNodeUri('corpus.example/id/node/1')).toBe(false);
    expect(isNodeUri('javascript:alert(1)')).toBe(false);
    expect(isNodeUri('')).toBe(false);
    expect(uriHost(NODE_URI)).toBe('corpus.voorbeeldministerie.example');
    expect(uriHost('geen uri')).toBe('');
  });
});

describe('ChainList', () => {
  it('renders nothing for a node without a chain above it', () => {
    const { container } = renderApp(
      <ChainList chain={{ nodes: [{ uri: 'u-1', type: 'doel', title: 'Een doel' }] }} label="Keten" />,
    );
    expect(container.querySelector('ol')).toBeNull();
  });

  it('names a node of another corpus the chain runs into', () => {
    const { container } = renderApp(
      <ChainList
        label="Keten"
        chain={{
          nodes: [{ uri: 'u-1', type: 'instrument', title: 'Een instrument' }],
          external_node_uris: ['https://corpus.anderministerie.example/id/node/x'],
        }}
      />,
    );
    const steps = [...container.querySelectorAll('ol li')].map((el) => el.textContent ?? '');
    expect(steps).toHaveLength(2);
    expect(steps[1]).toContain('ander corpus (corpus.anderministerie.example)');
  });
});

function Harness({ initial = [] }: { initial?: string[] }) {
  const [value, setValue] = useState<string[]>(initial);
  return (
    <>
      <NodePicker value={value} onChange={setValue} />
      <output data-testid="value">{value.join(',')}</output>
    </>
  );
}

describe('NodePicker', () => {
  it('says so when no corpus is connected and still takes a pasted URI', async () => {
    mockApi({
      '/api/nodes/corpora': {
        problem: 'Er is geen corpus gekoppeld aan deze instantie. Je kunt doorgaan zonder context.',
      },
    });
    const { container } = renderApp(<Harness />);
    await waitFor(() =>
      expect(texts(container, 'nldd-banner[variant="neutral"]')[0]).toContain('geen corpus'),
    );
    expect(container.querySelector('nldd-search-field')).toBeNull();
    expect(texts(container, 'nldd-inline-dialog')).toContain('Nog geen context gekozen');
    expect(texts(container, 'nldd-button')).toContain('Voeg URI toe');
  });

  it('offers the search when a corpus can be asked', async () => {
    mockApi({
      '/api/nodes/corpora': {
        corpora: [
          {
            base_uri: 'https://corpus.voorbeeldministerie.example',
            name: 'Corpus Voorbeeldministerie',
            searchable: true,
          },
        ],
        problem: null,
      },
    });
    const { container } = renderApp(<Harness />);
    await waitFor(() => expect(container.querySelector('nldd-search-field')).not.toBeNull());
    expect(container.textContent).toContain('Corpus: Corpus Voorbeeldministerie');
    // Nothing is searched before the user asks.
    expect(container.querySelector('nldd-table')).toBeNull();
  });

  it('shows a chosen node with its chain, and a URI that cannot be resolved as a URI', async () => {
    const other = 'https://corpus.anderministerie.example/id/node/n-2';
    const api = mockApi({ '/api/nodes/corpora': { problem: 'Er is geen corpus gekoppeld.' } });
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = new URL(String(input), 'http://test');
        api.calls.push(url.pathname);
        let body: unknown = { problem: 'Er is geen corpus gekoppeld.' };
        if (url.pathname === '/api/nodes/lookup') {
          body =
            url.searchParams.get('uri') === NODE_URI
              ? {
                  uri: NODE_URI,
                  resolved: true,
                  node: {
                    uri: NODE_URI,
                    type: 'instrument',
                    title: 'Opdracht bouwsteen Alfa',
                    managing_organisation: { name: 'Voorbeeldministerie' },
                    status: 'actief',
                  },
                  chain: {
                    nodes: [
                      { uri: NODE_URI, type: 'instrument', title: 'Opdracht bouwsteen Alfa' },
                      { uri: 'u-2', type: 'politieke_input', title: 'Motie over hergebruik' },
                    ],
                    edges: [{ from_uri: NODE_URI, to_uri: 'u-2', type: 'vloeit_voort_uit' }],
                  },
                }
              : {
                  uri: other,
                  resolved: false,
                  problem: 'Voor deze URI is geen corpus gekoppeld aan deze instantie.',
                };
        }
        return new Response(JSON.stringify(body), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }),
    );
    const { container } = renderApp(<Harness initial={[NODE_URI, other]} />);
    await waitFor(() => expect(container.textContent).toContain('Motie over hergebruik'));
    const chosen = container.querySelector('ul[aria-label="Gekozen context"]');
    expect(chosen?.querySelectorAll(':scope > li')).toHaveLength(2);
    expect(texts(container, 'nldd-badge')).toEqual(['Instrument']);
    expect(container.textContent).toContain('Voorbeeldministerie · actief');
    expect(container.textContent).toContain('vloeit voort uit');
    await waitFor(() => expect(container.textContent).toContain('geen corpus gekoppeld'));
    expect(container.textContent).toContain(other);
    // Each chosen node can be removed, and the button says which one.
    const labels = [...container.querySelectorAll('nldd-button[text="Verwijder"]')].map((el) =>
      el.getAttribute('accessible-label'),
    );
    expect(labels[0]).toBe('Verwijder Opdracht bouwsteen Alfa uit de context');
  });
});
