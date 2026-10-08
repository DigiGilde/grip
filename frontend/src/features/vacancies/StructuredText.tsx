import { RichText } from '@/ui/RichText';
import { Stack } from '@/ui/layout';
import { splitSections } from './textWorkApi';

/**
 * A text of sections as it reads: each "## " heading as a heading one step
 * below the page section it sits in, and under it the body through the
 * shared display of a stored text (`@/ui/RichText`), so it reads as the
 * editor showed it.
 */
export function StructuredText({ text, headingLevel = 3 }: { text: string; headingLevel?: 3 | 4 }) {
  return (
    <Stack gap="group">
      {splitSections(text).map((section, index) => (
        <Stack key={`${section.heading}-${index}`} gap="close">
          {section.heading && (
            <nldd-title size={6} text={section.heading} heading-level={headingLevel} />
          )}
          <RichText text={section.body} headingLevel={4} />
        </Stack>
      ))}
    </Stack>
  );
}
