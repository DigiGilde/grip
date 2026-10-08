import { RichText } from '@/ui/RichText';
import './register';

/**
 * The text of a section as it will read. It is the shared display of a stored
 * text (`@/ui/RichText`), so a quote reads on screen as the editor showed it.
 */
export function Prose({ text }: { text: string }) {
  return <RichText text={text} headingLevel={4} spacing="tight" />;
}
