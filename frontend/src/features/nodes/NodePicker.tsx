import { useRef, useState } from 'react';
import { useQueries, useQuery } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { orUndef, useNlddEvent } from '@/components/nldd/events';
import { Button, TextInput } from '@/features/assignments/ui';
import { EmptyNotice, ErrorNotice, FilterSelect, Loading, SectionHeading } from '@/ui/layout';
import {
  fetchCorpora,
  lookupNode,
  nodeKeys,
  searchNodes,
  type CorpusNode,
  type NodeLookup,
} from './api';
import { isNodeUri, nodeTypeLabel } from './labels';
import { NodeCard, NodeCardGrid } from './NodeCard';
import { NodeDetailSheet } from './NodeDetailSheet';
import './register';

interface NodePickerProps {
  /** The chosen node URIs, in the order they were added. */
  value: readonly string[];
  onChange: (uris: string[]) => void;
  /** Most URIs a request may carry. */
  max?: number;
}

function SearchBox({
  value,
  onInput,
  onSearch,
  disabled,
}: {
  value: string;
  onInput: (value: string) => void;
  onSearch: (value: string) => void;
  disabled?: boolean;
}) {
  const ref = useRef<HTMLElement>(null);
  const read = (event: Event): string => {
    const detail = (event as CustomEvent<{ value?: unknown }>).detail;
    return typeof detail?.value === 'string' ? detail.value : '';
  };
  useNlddEvent(ref, 'input', (event) => onInput(read(event)));
  useNlddEvent(ref, 'search', (event) => onSearch(read(event)));
  return (
    <nldd-search-field
      ref={ref}
      value={value}
      placeholder="Zoek een node op titel"
      accessible-label="Zoek een node op titel"
      show-search-button
      disabled={orUndef(disabled)}
    />
  );
}

function ResultRow({
  node,
  chosen,
  onAdd,
}: {
  node: CorpusNode;
  chosen: boolean;
  onAdd: () => void;
}) {
  const organisation = node.managing_organisation?.name ?? '';
  return (
    <nldd-table-row>
      <nldd-text-cell text={nodeTypeLabel(node.type)} />
      <nldd-text-cell
        text={node.title}
        {...(node.description ? { 'supporting-text': node.description } : {})}
      />
      <nldd-text-cell text={organisation} />
      <nldd-cell>
        {chosen ? (
          <nldd-text size="sm">Toegevoegd</nldd-text>
        ) : (
          <Button
            text="Voeg toe"
            size="sm"
            accessibleLabel={`Voeg ${node.title} toe als context`}
            onClick={onAdd}
          />
        )}
      </nldd-cell>
    </nldd-table-row>
  );
}

/**
 * Pick the nodes an assignment follows from. Searches the corpora this
 * instance has a contract with, shows the chain up to the political input
 * for each chosen node, and accepts a pasted URI. Context is optional: when
 * no corpus is connected or one does not answer, the picker says so and the
 * user goes on without, or with bare URIs.
 */
export function NodePicker({ value, onChange, max = 50 }: NodePickerProps) {
  const corpora = useQuery({ queryKey: nodeKeys.corpora(), queryFn: fetchCorpora });
  const searchable = (corpora.data?.corpora ?? []).filter((corpus) => corpus.searchable);

  const [corpus, setCorpus] = useState('');
  const [draft, setDraft] = useState('');
  const [term, setTerm] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pasted, setPasted] = useState('');
  const [pasteError, setPasteError] = useState<string | null>(null);
  const [openUri, setOpenUri] = useState<string | null>(null);

  const activeCorpus = corpus || searchable[0]?.base_uri || '';
  const search = useQuery({
    queryKey: nodeKeys.search(activeCorpus, term ?? '', page),
    queryFn: () => searchNodes(activeCorpus, term ?? '', page),
    enabled: activeCorpus !== '' && term !== null,
  });

  // Each chosen URI is looked up so the user sees what was picked, with its
  // chain. A lookup that fails leaves the bare URI in place.
  const lookups = useQueries({
    queries: value.map((uri) => ({
      queryKey: nodeKeys.lookup(uri),
      queryFn: () => lookupNode(uri),
      retry: false,
    })),
  });

  const full = value.length >= max;
  const add = (uri: string) => {
    if (!value.includes(uri) && !full) onChange([...value, uri]);
  };
  const remove = (uri: string) => onChange(value.filter((item) => item !== uri));

  const addPasted = () => {
    const uri = pasted.trim();
    if (!isNodeUri(uri)) {
      setPasteError('Een node-URI begint met https:// en verwijst naar een node in een corpus.');
      return;
    }
    if (value.includes(uri)) {
      setPasteError('Deze URI staat al bij de context.');
      return;
    }
    setPasteError(null);
    add(uri);
    setPasted('');
  };

  const results = search.data?.results ?? [];
  const total = search.data?.total ?? 0;
  const pageSize = search.data?.page_size ?? 10;
  const lastPage = Math.max(1, Math.ceil(total / pageSize));

  return (
    <nldd-container gap="16">
      <nldd-text>
        Context is de politieke wens, het doel of het instrument waar deze aanvraag uit volgt.
        Je kiest nodes uit een corpus of plakt een URI. Context is niet verplicht.
      </nldd-text>

      <SectionHeading text="Gekozen context" level={3} />
      {value.length === 0 ? (
        <EmptyNotice
          text="Nog geen context gekozen"
          supportingText="Je kunt de aanvraag ook zonder context versturen."
        />
      ) : (
        <NodeCardGrid label="Gekozen context">
          {value.map((uri, index) => {
            const lookup = lookups[index];
            const item: NodeLookup = lookup?.data ?? {
              uri,
              resolved: false,
              problem: 'Deze URI kon niet worden opgezocht. Hij blijft bewaard zoals hij is.',
            };
            const name = item.node?.title ?? uri;
            return (
              <NodeCard
                key={uri}
                item={item}
                pending={lookup?.isPending}
                onOpen={setOpenUri}
                action={
                  <Button
                    text="Verwijder"
                    size="sm"
                    appearance="neutral-transparent"
                    accessibleLabel={`Verwijder ${name} uit de context`}
                    onClick={() => remove(uri)}
                  />
                }
              />
            );
          })}
        </NodeCardGrid>
      )}
      {full ? (
        <nldd-banner
          variant="warning"
          size="sm"
          text={`Een aanvraag draagt ten hoogste ${max} nodes als context.`}
        />
      ) : null}

      <SectionHeading text="Zoek in een corpus" level={3} />
      {corpora.isPending ? <Loading text="Bezig met ophalen van de corpora" /> : null}
      {corpora.isError ? <ErrorNotice message={errorMessage(corpora.error)} /> : null}
      {corpora.data?.problem ? (
        <nldd-banner variant="neutral" size="sm" text={corpora.data.problem} />
      ) : null}
      {searchable.length > 0 ? (
        <nldd-container gap="8">
          {searchable.length > 1 ? (
            <FilterSelect
              label="Corpus"
              value={activeCorpus}
              onChange={(next) => {
                setCorpus(next);
                setPage(1);
              }}
              options={searchable.map((item) => ({ value: item.base_uri, label: item.name }))}
            />
          ) : (
            <nldd-text size="sm">Corpus: {searchable[0]?.name}</nldd-text>
          )}
          <SearchBox
            value={draft}
            onInput={setDraft}
            onSearch={(submitted) => {
              setDraft(submitted);
              setTerm(submitted.trim());
              setPage(1);
            }}
          />
          {search.isFetching ? <Loading text="Bezig met zoeken" /> : null}
          {search.isError ? <ErrorNotice message={errorMessage(search.error)} /> : null}
          {search.data?.problem ? (
            <nldd-banner variant="warning" size="sm" text={search.data.problem} />
          ) : null}
          {search.isSuccess && !search.data.problem && results.length === 0 ? (
            <EmptyNotice
              text="Geen nodes gevonden"
              supportingText="Probeer een ander woord, of plak de URI van de node hieronder."
            />
          ) : null}
          {results.length > 0 ? (
            <>
              <nldd-text size="sm" aria-live="polite">
                {total} {total === 1 ? 'node' : 'nodes'} gevonden
                {lastPage > 1 ? `, pagina ${page} van ${lastPage}` : ''}
              </nldd-text>
              <nldd-table
                accessible-label="Gevonden nodes"
                columns="150px minmax(220px,2fr) minmax(160px,1fr) 130px"
              >
                <nldd-table-row slot="header">
                  <nldd-text-cell text="Soort" />
                  <nldd-text-cell text="Titel" />
                  <nldd-text-cell text="Beheerd door" />
                  <nldd-text-cell text="Actie" />
                </nldd-table-row>
                {results.map((node) => (
                  <ResultRow
                    key={node.uri}
                    node={node}
                    chosen={value.includes(node.uri)}
                    onAdd={() => add(node.uri)}
                  />
                ))}
              </nldd-table>
              {lastPage > 1 ? (
                <nldd-button-group>
                  <Button
                    text="Vorige"
                    size="sm"
                    disabled={page <= 1}
                    onClick={() => setPage((current) => Math.max(1, current - 1))}
                  />
                  <Button
                    text="Volgende"
                    size="sm"
                    disabled={page >= lastPage}
                    onClick={() => setPage((current) => Math.min(lastPage, current + 1))}
                  />
                </nldd-button-group>
              ) : null}
            </>
          ) : null}
        </nldd-container>
      ) : null}

      <SectionHeading text="Plak een URI" level={3} />
      {pasteError ? <nldd-banner variant="critical" size="sm" text={pasteError} /> : null}
      <TextInput
        label="Node-URI"
        value={pasted}
        onChange={setPasted}
        optional
        keyboard="url"
        hint="Bijvoorbeeld uit de adresbalk van het corpus."
        invalid={pasteError !== null}
      />
      <div>
        <Button text="Voeg URI toe" onClick={addPasted} disabled={full} />
      </div>
      <NodeDetailSheet
        uri={openUri}
        known={lookups.flatMap((lookup) => (lookup.data ? [lookup.data] : []))}
        fetchNode={lookupNode}
        scope="picker"
        onClose={() => setOpenUri(null)}
      />
    </nldd-container>
  );
}
