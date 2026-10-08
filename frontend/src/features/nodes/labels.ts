/** Dutch names for the node and edge types of the shared vocabulary. */

const NODE_TYPE_LABELS: Record<string, string> = {
  politieke_input: 'Politieke input',
  dossier: 'Dossier',
  doel: 'Doel',
  instrument: 'Instrument',
  beleidskader: 'Beleidskader',
  maatregel: 'Maatregel',
  probleem: 'Probleem',
  effect: 'Effect',
  beleidsoptie: 'Beleidsoptie',
  bron: 'Bron',
};

const EDGE_TYPE_LABELS: Record<string, string> = {
  implementeert: 'implementeert',
  draagt_bij_aan: 'draagt bij aan',
  vloeit_voort_uit: 'vloeit voort uit',
  vereist: 'vereist',
  evalueert: 'evalueert',
  vervangt: 'vervangt',
  onderdeel_van: 'is onderdeel van',
  leidt_tot: 'leidt tot',
  adresseert: 'adresseert',
  meet: 'meet',
};

/** The last part of a type that a corpus defined itself (a full URI). */
function ownTypeName(type: string): string {
  const tail = type.replace(/[/#]+$/, '').split(/[/#]/).pop() ?? type;
  return tail.replace(/[_-]+/g, ' ');
}

export function nodeTypeLabel(type: string): string {
  if (type in NODE_TYPE_LABELS) return NODE_TYPE_LABELS[type] as string;
  const name = type.includes('://') ? ownTypeName(type) : type.replace(/_/g, ' ');
  return name.charAt(0).toUpperCase() + name.slice(1);
}

export function edgeTypeLabel(type: string): string {
  if (type in EDGE_TYPE_LABELS) return EDGE_TYPE_LABELS[type] as string;
  return type.includes('://') ? ownTypeName(type) : type.replace(/_/g, ' ');
}

/** What a URI points at when it could not be resolved: its host. */
export function uriHost(uri: string): string {
  try {
    return new URL(uri).host;
  } catch {
    return '';
  }
}

/** A string is a usable node URI when it is an absolute http(s) address. */
export function isNodeUri(value: string): boolean {
  try {
    const url = new URL(value.trim());
    return (url.protocol === 'https:' || url.protocol === 'http:') && url.host !== '';
  } catch {
    return false;
  }
}
