import { Stack } from '@/ui/layout';
import { splitSections } from './textWorkApi';

/** One block of a body: a paragraph, or a run of lines that start with "- ". */
function blocksOf(body: string): { list: boolean; lines: string[] }[] {
  const blocks: { list: boolean; lines: string[] }[] = [];
  for (const chunk of body.split(/\n\s*\n/)) {
    let current: { list: boolean; lines: string[] } | null = null;
    for (const line of chunk.split('\n')) {
      const item = line.startsWith('- ');
      if (!current || current.list !== item) {
        current = { list: item, lines: [] };
        blocks.push(current);
      }
      current.lines.push(item ? line.slice(2) : line);
    }
  }
  return blocks.filter((block) => block.lines.some((line) => line.trim()));
}

/** "*nadruk*" as emphasis; everything else is text. */
function inline(text: string) {
  return text
    .split(/(\*[^*\n]+\*)/)
    .map((part, index) =>
      part.length > 2 && part.startsWith('*') && part.endsWith('*') ? (
        <em key={index}>{part.slice(1, -1)}</em>
      ) : (
        part
      ),
    );
}

/**
 * A text of sections as it reads: headings, paragraphs, lists and emphasis.
 * Nothing else is interpreted, so a text can hold no markup of its own. The
 * headings are one step below the heading of the page section they sit in.
 */
export function StructuredText({ text, headingLevel = 3 }: { text: string; headingLevel?: 3 | 4 }) {
  return (
    <Stack gap="group">
      {splitSections(text).map((section, index) => (
        <Stack key={`${section.heading}-${index}`} gap="close">
          {section.heading && (
            <nldd-title size={6} text={section.heading} heading-level={headingLevel} />
          )}
          {blocksOf(section.body).map((block, blockIndex) => (
            <nldd-rich-text key={blockIndex}>
              {block.list ? (
                <ul>
                  {block.lines.map((line, lineIndex) => (
                    <li key={lineIndex}>{inline(line)}</li>
                  ))}
                </ul>
              ) : (
                <p style={{ whiteSpace: 'pre-line' }}>{inline(block.lines.join('\n'))}</p>
              )}
            </nldd-rich-text>
          ))}
        </Stack>
      ))}
    </Stack>
  );
}
