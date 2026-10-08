/**
 * The node endpoints: the corpora this instance can search, searching one,
 * and resolving a URI to a node with its chain. A corpus that is missing or
 * silent is never an error here: the answer carries a `problem` sentence.
 */
import { apiGet } from '@/api/client';

export interface NodeOrganisation {
  name?: string | null;
  tooi_uri?: string | null;
}

export interface CorpusNode {
  uri: string;
  type: string;
  title: string;
  description?: string | null;
  status?: string | null;
  corpus?: string | null;
  managing_organisation?: NodeOrganisation | null;
  valid_from?: string | null;
  valid_until?: string | null;
  peildatum?: string | null;
  type_details?: Record<string, unknown> | null;
}

export interface ChainEdge {
  from_uri: string;
  to_uri: string;
  type: string;
}

export interface NodeChain {
  nodes?: CorpusNode[];
  edges?: ChainEdge[];
  external_node_uris?: string[];
  complete?: boolean;
}

export interface Corpus {
  base_uri: string;
  name: string;
  searchable: boolean;
}

export interface Corpora {
  corpora?: Corpus[];
  problem?: string | null;
}

export interface NodeSearch {
  results?: CorpusNode[];
  page: number;
  page_size: number;
  total: number;
  problem?: string | null;
}

/** A political input a node follows from, or another linked node. */
export interface NodeOrigin {
  uri: string;
  title: string;
}

export interface PathStep {
  uri: string;
  title?: string | null;
  type?: string | null;
  /** The step lies in another corpus than the node the path starts at. */
  external?: boolean;
  corpus_name?: string | null;
  /** Whether this instance can ask the corpus of the step for the node. */
  resolvable?: boolean;
  /** The relation between this step and the next; absent on the last. */
  edge_type?: string | null;
}

export interface NodePath {
  steps?: PathStep[];
}

export interface NodeLookup {
  uri: string;
  resolved: boolean;
  problem?: string | null;
  node?: CorpusNode | null;
  chain?: NodeChain | null;
  corpus_name?: string | null;
  /** The political inputs at the end of the chain, nearest first. */
  origins?: NodeOrigin[];
  steps_to_origin?: number | null;
  /** Per end point one path: to a political input, or into another corpus. */
  paths?: NodePath[];
  /** Another linked node this node's chain passes through. */
  falls_under?: NodeOrigin | null;
}

export interface AssignmentContext {
  peildatum: string;
  acceptance_date?: string | null;
  /** Why nothing could be resolved at all; said once instead of per node. */
  notice?: string | null;
  items?: NodeLookup[];
}

export const nodeKeys = {
  corpora: () => ['nodes', 'corpora'] as const,
  search: (corpus: string, q: string, page: number) => ['nodes', 'search', corpus, q, page] as const,
  lookup: (uri: string) => ['nodes', 'lookup', uri] as const,
  context: (assignmentId: string, peildatum: string) =>
    ['nodes', 'context', assignmentId, peildatum] as const,
  contextNode: (assignmentId: string, peildatum: string, uri: string) =>
    ['nodes', 'context-node', assignmentId, peildatum, uri] as const,
};

export function fetchCorpora(): Promise<Corpora> {
  return apiGet<Corpora>('/api/nodes/corpora');
}

export function searchNodes(corpus: string, q: string, page = 1): Promise<NodeSearch> {
  return apiGet<NodeSearch>('/api/nodes/search', { corpus, q, page, page_size: 10 });
}

export function lookupNode(uri: string): Promise<NodeLookup> {
  return apiGet<NodeLookup>('/api/nodes/lookup', { uri });
}

/** `peildatum`: empty for today, `acceptance`, or a date. */
export function fetchAssignmentContext(
  assignmentId: string,
  peildatum: string,
): Promise<AssignmentContext> {
  return apiGet<AssignmentContext>(`/api/assignments/${assignmentId}/context`, { peildatum });
}

/** One node on a chain of an assignment's context, for whoever may read the assignment. */
export function fetchContextNode(
  assignmentId: string,
  uri: string,
  peildatum: string,
): Promise<NodeLookup> {
  return apiGet<NodeLookup>(`/api/assignments/${assignmentId}/context/node`, { uri, peildatum });
}
