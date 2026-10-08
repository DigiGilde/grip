/**
 * A stored text as it reads: headings, paragraphs, lists and emphasis, drawn
 * with the design system's rich text. The same form the editor writes, so
 * what a person edits is what they see afterwards. Nothing else in the text
 * has a meaning, and nothing in it is HTML.
 */
import { Fragment } from 'react';
import { textBlocks, type Inline } from './text/marks';

if (import.meta.env.MODE !== 'test') void import('./text/register');

function Runs({ runs }: { runs: Inline[] }) {
  return (
    <>
      {runs.map((run, index) =>
        run.mark === 'strong' ? (
          <strong key={index}>{run.text}</strong>
        ) : run.mark === 'em' ? (
          <em key={index}>{run.text}</em>
        ) : run.mark === 'open' ? (
          // Still to fill in: marked, so it is not read over.
          <mark key={index}>{run.text}</mark>
        ) : (
          <Fragment key={index}>{run.text}</Fragment>
        ),
      )}
    </>
  );
}

interface RichTextProps {
  text: string;
  /** The heading level a "## " or "### " line gets on this page. */
  headingLevel?: 3 | 4;
  /** Closer together, for a text inside a card or a row. */
  spacing?: 'tight';
}

export function RichText({ text, headingLevel = 3, spacing }: RichTextProps) {
  const blocks = textBlocks(text);
  return (
    <nldd-rich-text {...(spacing ? { spacing } : {})}>
      {blocks.map((block, index) => {
        if (block.kind === 'heading') {
          const Heading = headingLevel === 3 ? 'h3' : 'h4';
          return <Heading key={index}>{block.text}</Heading>;
        }
        if (block.kind === 'list') {
          const List = block.ordered ? 'ol' : 'ul';
          return (
            <List key={index}>
              {block.items.map((item, at) => (
                <li key={at}>
                  <Runs runs={item} />
                </li>
              ))}
            </List>
          );
        }
        return (
          <p key={index}>
            {block.lines.map((line, at) => (
              <Fragment key={at}>
                {at > 0 ? <br /> : null}
                <Runs runs={line} />
              </Fragment>
            ))}
          </p>
        );
      })}
    </nldd-rich-text>
  );
}
