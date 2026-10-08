/** The way from an idea to an agreed assignment, for a potential assignment. */
import type { AssignmentDetail } from './api';
import type { AssignmentTabKey } from './paths';

export interface Step {
  text: string;
  /** The tab where this step is done, when the reader has it. */
  tab?: AssignmentTabKey;
}

/** "Eva Eigenaar of Pim Planner", the people who run the assignment. */
export function ownersText(assignment: AssignmentDetail): string {
  const names = assignment.roles.map((holder) => holder.name);
  if (names.length === 0) return 'De eigenaar van de opdracht';
  if (names.length === 1) return names[0] ?? '';
  return `${names.slice(0, -1).join(', ')} of ${names[names.length - 1]}`;
}

export interface NextSteps {
  items: Step[];
  /** 1-based number of the step the assignment is at. */
  current: number;
  /** One sentence saying what to do now. */
  advice: string;
  /** The one thing to do now, for a reader who can do it. */
  action: { text: string; tab: AssignmentTabKey } | null;
}

/** The steps and where the assignment stands; null once it is no longer potential. */
export function nextSteps(assignment: AssignmentDetail): NextSteps | null {
  if (assignment.phase !== 'potential') return null;
  const money = assignment.permissions.read_financial;
  const items: Step[] = [
    { text: 'Begroting opstellen', ...(money ? { tab: 'budget' as const } : {}) },
    { text: 'Offerte maken', ...(money ? { tab: 'quote' as const } : {}) },
    { text: 'Offerte aanbieden', ...(money ? { tab: 'quote' as const } : {}) },
    { text: 'Akkoord van de opdrachtgever' },
  ];
  const hasQuote = assignment.pipeline_amount_source === 'quote';
  if (assignment.status === 'verbally_agreed') {
    return {
      items,
      current: 4,
      advice:
        'De opdrachtgever heeft mondeling akkoord gegeven. Leg het getekende akkoord vast om de opdracht te laten ingaan.',
      action: money ? { text: 'Ga naar de offerte', tab: 'quote' } : null,
    };
  }
  if (assignment.status === 'quoted') {
    return {
      items,
      current: 4,
      advice: 'De offerte is uitgegeven. De opdracht gaat in zodra de opdrachtgever akkoord geeft.',
      action: money ? { text: 'Ga naar de offerte', tab: 'quote' } : null,
    };
  }
  if (hasQuote) {
    return {
      items,
      current: 3,
      advice: money
        ? 'Er is een offerte gemaakt. Bied die aan de opdrachtgever aan.'
        : `Er is een offerte gemaakt. ${ownersText(assignment)} biedt die aan de opdrachtgever aan.`,
      action: money ? { text: 'Bied de offerte aan', tab: 'quote' } : null,
    };
  }
  return {
    items,
    current: 1,
    advice: money
      ? 'Dit is nog een potentiële opdracht. Stel de begroting op en maak daar een offerte van.'
      : `Dit is nog een potentiële opdracht. ${ownersText(assignment)} maakt eerst de begroting.`,
    action: money ? { text: 'Maak de begroting', tab: 'budget' } : null,
  };
}
