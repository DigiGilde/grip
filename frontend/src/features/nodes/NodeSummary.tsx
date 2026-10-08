import type { ReactNode } from 'react';
import type { CorpusNode, NodeChain, NodeLookup } from './api';
import { edgeTypeLabel, nodeTypeLabel, uriHost } from './labels';
import './register';

function organisationName(node: CorpusNode): string {
  return node.managing_organisation?.name ?? '';
}

/** One line under a node: who manages it and its status. */
function nodeFacts(node: CorpusNode): string {
  return [organisationName(node), node.status ?? ''].filter(Boolean).join(' · ');
}

/**
 * The way from a node up to the political input it follows from, as an
 * ordered list: each step names the relation to the next node. The chain a
 * corpus returns starts at the node that was asked for.
 */
export function ChainList({ chain, label }: { chain: NodeChain; label: string }) {
  const nodes = chain.nodes ?? [];
  const edges = chain.edges ?? [];
  if (nodes.length <= 1 && (chain.external_node_uris ?? []).length === 0) return null;
  const relation = (index: number): string => {
    const from = nodes[index]?.uri;
    const to = nodes[index + 1]?.uri;
    const edge = edges.find(
      (candidate) =>
        (candidate.from_uri === from && candidate.to_uri === to) ||
        (candidate.from_uri === to && candidate.to_uri === from),
    );
    return edge ? edgeTypeLabel(edge.type) : '';
  };
  return (
    <ol aria-label={label} style={{ margin: 0, paddingInlineStart: '1.25rem' }}>
      {nodes.map((node, index) => (
        <li key={node.uri}>
          <nldd-text size="sm">
            <strong>{nodeTypeLabel(node.type)}</strong>: {node.title}
            {organisationName(node) ? ` (${organisationName(node)})` : ''}
            {index < nodes.length - 1 && relation(index) ? `, ${relation(index)}` : ''}
          </nldd-text>
        </li>
      ))}
      {(chain.external_node_uris ?? []).map((uri) => (
        <li key={uri}>
          <nldd-text size="sm">
            Loopt door in een ander corpus ({uriHost(uri)}): {uri}
          </nldd-text>
        </li>
      ))}
    </ol>
  );
}

/**
 * A context node as a person reads it: type, title, who manages it, and the
 * chain up to the political input. A URI that could not be resolved stays
 * visible as a URI, with the reason.
 */
export function NodeSummary({ item, action }: { item: NodeLookup; action?: ReactNode }) {
  const node = item.node;
  return (
    <nldd-container gap="4">
      <nldd-container layout="wrap" gap="8">
        {node ? (
          <>
            <nldd-badge color="accent" text={nodeTypeLabel(node.type)} />
            <nldd-text>
              <strong>{node.title}</strong>
            </nldd-text>
          </>
        ) : (
          <nldd-text>
            <strong>{item.uri}</strong>
          </nldd-text>
        )}
        {action}
      </nldd-container>
      {node && nodeFacts(node) ? <nldd-text size="sm">{nodeFacts(node)}</nldd-text> : null}
      {node?.description ? <nldd-text size="sm">{node.description}</nldd-text> : null}
      {node ? (
        <nldd-text size="sm">{item.uri}</nldd-text>
      ) : (
        <nldd-text size="sm">{item.problem ?? 'Deze URI kon niet worden opgezocht.'}</nldd-text>
      )}
      {item.chain ? (
        <ChainList chain={item.chain} label={`Keten van ${node?.title ?? item.uri}`} />
      ) : null}
    </nldd-container>
  );
}
