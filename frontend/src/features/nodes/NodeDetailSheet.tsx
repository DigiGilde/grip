import { ExternalLink } from '@/ui/Icon';
import { useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useQuery } from '@tanstack/react-query';
import { orUndef, useNlddEvent } from '@/components/nldd/events';
import { Button } from '@/features/assignments/ui';
import { type Fact, Facts, LoadError, Loading, Quiet, SectionHeading, Stack } from '@/ui/layout';
import { formatDate, formatPeriod } from '@/lib/format';
import type { NodeLookup } from './api';
import { nodeTypeLabel } from './labels';
import { NodePathView } from './NodePathView';
import { notableStatus } from './summary';
import './register';

export interface NodeDetailSheetProps {
  /** The node to show; null closes the sheet. */
  uri: string | null;
  /** What the list already knows about a node, shown at once while the rest loads. */
  known: readonly NodeLookup[];
  /** Fetches a node the list does not hold: a step on a path. */
  fetchNode: (uri: string) => Promise<NodeLookup>;
  /** Part of the query key, so answers of another assignment or date are not reused. */
  scope: string;
  onClose: () => void;
}

function CopyUri({ uri }: { uri: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    void navigator.clipboard
      ?.writeText(uri)
      .then(() => setCopied(true))
      .catch(() => setCopied(false));
  };
  return (
    <Stack gap="close">
      <nldd-text size="sm" style={{ overflowWrap: 'anywhere' }}>
        {uri}
      </nldd-text>
      <div>
        <Button text="Kopieer URI" size="sm" onClick={copy} />
      </div>
      <nldd-text size="sm" color="secondary" aria-live="polite">
        {copied ? 'De URI is gekopieerd.' : ''}
      </nldd-text>
    </Stack>
  );
}

/** Where the node lives: the corpus by name, and the way to its own page there. */
function Source({ item }: { item: NodeLookup }) {
  return (
    <nldd-container layout="wrap" gap="16">
      {item.corpus_name ? <Quiet>Uit {item.corpus_name}</Quiet> : null}
      <ExternalLink href={item.uri} text="Open in het corpus" />
    </nldd-container>
  );
}

function Detail({ item, onStep }: { item: NodeLookup; onStep: (uri: string) => void }) {
  const node = item.node;
  if (!node) {
    return (
      <Stack gap="group">
        <nldd-banner
          variant="neutral"
          size="sm"
          text="Deze node is niet op te halen"
          supporting-text={item.problem ?? 'De verwijzing blijft bewaard zoals hij is.'}
        />
        <CopyUri key={item.uri} uri={item.uri} />
      </Stack>
    );
  }
  const status = notableStatus(node.status);
  const facts: Fact[] = [
    { label: 'Soort', value: nodeTypeLabel(node.type) },
    { label: 'Beheerd door', value: node.managing_organisation?.name ?? '' },
    { label: 'Status', value: status },
    { label: 'Geldig', value: formatPeriod(node.valid_from, node.valid_until) },
  ].filter((fact) => fact.value !== '');
  const paths = item.paths ?? [];
  return (
    <Stack gap="group">
      <Stack gap="related">
        <Source item={item} />
        {node.description ? <nldd-text>{node.description}</nldd-text> : null}
        <Facts label="Gegevens van de node" facts={facts} labelWidth="140px" />
      </Stack>

      <Stack gap="related">
        <SectionHeading text="Waar dit uit voortkomt" level={2} />
        {item.falls_under ? (
          <Quiet>
            Deze node valt onder {item.falls_under.title}, die ook aan deze opdracht is gekoppeld.
          </Quiet>
        ) : null}
        {paths.length === 0 ? (
          <Quiet>
            {node.type === 'politieke_input'
              ? 'Dit is zelf een politieke input: hier begint de keten.'
              : 'Het corpus kent voor deze node geen keten naar een politieke input.'}
          </Quiet>
        ) : (
          <NodePathView paths={paths} currentUri={item.uri} onStep={onStep} />
        )}
        <Quiet>
          Titel en status zijn die van {node.peildatum ? formatDate(node.peildatum) : 'vandaag'}. De
          keten is altijd de keten van nu: een corpus bewaart niet hoe de verbanden vroeger liepen.
        </Quiet>
      </Stack>

      <Stack gap="related">
        <SectionHeading text="Verwijzing" level={2} />
        <CopyUri key={item.uri} uri={item.uri} />
      </Stack>
    </Stack>
  );
}

/**
 * The detail of a node, on demand: its description, where it comes from as
 * paths, and the reference itself. A step on a path opens in the same sheet,
 * with the way back in the title bar. The sheet stays in the document while
 * closed, so its animation runs and focus returns to what opened it.
 */
export function NodeDetailSheet({ uri, known, fetchNode, scope, onClose }: NodeDetailSheetProps) {
  const sheetRef = useRef<HTMLElement>(null);
  const barRef = useRef<HTMLElement>(null);
  const titleId = useId();
  // The steps taken from the node the sheet was opened on.
  // Kept with the node they started from, so opening another card starts anew.
  const [walk, setWalk] = useState<{ from: string | null; steps: string[] }>({
    from: null,
    steps: [],
  });
  const trail = walk.from === uri ? walk.steps : [];
  const setTrail = (change: (steps: string[]) => string[]) =>
    setWalk({ from: uri, steps: change(trail) });

  const current = trail[trail.length - 1] ?? uri;
  const fromList = known.find((item) => item.uri === current);
  const query = useQuery({
    queryKey: ['nodes', 'detail', scope, current],
    queryFn: () => fetchNode(current as string),
    enabled: current !== null && fromList === undefined,
    retry: false,
  });
  const item = fromList ?? query.data;

  useNlddEvent(sheetRef, 'close', onClose);
  useNlddEvent(barRef, 'back', () => setTrail((steps) => steps.slice(0, -1)));

  const title = item?.node?.title ?? (current ? 'Node' : '');
  return createPortal(
    <nldd-sheet ref={sheetRef} open={orUndef(uri !== null)} placement="right" width="720px">
      <nldd-page>
        <nldd-top-title-bar
          ref={barRef}
          slot="header"
          text={title}
          dismiss-text="Sluit"
          collapse-anchor={titleId}
          {...(trail.length > 0 ? { 'back-text': 'Terug' } : {})}
        />
        <nldd-simple-section>
          <nldd-title id={titleId} slot="header" size={2} text={title} heading-level={1} />
          {current && !item && query.isPending ? <Loading text="Bezig met ophalen" /> : null}
          {query.isError && !item ? (
            <LoadError error={query.error} retry={() => void query.refetch()} />
          ) : null}
          {item ? (
            <Detail item={item} onStep={(next) => setTrail((steps) => [...steps, next])} />
          ) : null}
        </nldd-simple-section>
      </nldd-page>
    </nldd-sheet>,
    document.body,
  );
}
