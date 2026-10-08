import type { ReactNode } from 'react';
import './register';

/** Bold and italic inside a line: "**vet**" and "*cursief*". */
function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g).map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith('*') && part.endsWith('*') && part.length > 2) {
      return <em key={index}>{part.slice(1, -1)}</em>;
    }
    return part;
  });
}

/**
 * The text of a section as it will read: a blank line starts a paragraph,
 * "- " a list, "1. " a numbered list, "### " a heading. The text is plain;
 * nothing in it is treated as markup beyond these few marks.
 */
export function Prose({ text }: { text: string }) {
  const blocks = text
    .replace(/\r\n/g, '\n')
    .split(/\n\s*\n/)
    .map((block) => block.trim())
    .filter(Boolean);
  return (
    <nldd-rich-text spacing="tight">
      {blocks.map((block, index) => {
        const lines = block.split('\n').map((line) => line.trim());
        if (lines.every((line) => line.startsWith('- '))) {
          return (
            <ul key={index}>
              {lines.map((line, at) => (
                <li key={at}>{inline(line.slice(2))}</li>
              ))}
            </ul>
          );
        }
        if (lines.every((line) => /^\d+\.\s/.test(line))) {
          return (
            <ol key={index}>
              {lines.map((line, at) => (
                <li key={at}>{inline(line.replace(/^\d+\.\s/, ''))}</li>
              ))}
            </ol>
          );
        }
        if (lines.length === 1 && lines[0]?.startsWith('### ')) {
          return <h4 key={index}>{inline(lines[0].slice(4))}</h4>;
        }
        return <p key={index}>{inline(lines.join(' '))}</p>;
      })}
    </nldd-rich-text>
  );
}
