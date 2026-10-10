// Fenced code blocks become nldd-code-viewer, which owns their look and
// highlighting. Only grammars the component knows are passed on.
import { visit } from 'unist-util-visit';

const LANGUAGES = new Set([
  'yaml', 'json', 'javascript', 'typescript', 'css', 'html', 'xml', 'bash',
  'markdown', 'rust', 'gherkin', 'toml', 'sql', 'python',
]);
const ALIASES = {
  sh: 'bash', shell: 'bash', console: 'bash', zsh: 'bash', js: 'javascript',
  ts: 'typescript', yml: 'yaml', py: 'python', md: 'markdown',
};

function text(node) {
  if (node.type === 'text') return node.value;
  return (node.children ?? []).map(text).join('');
}

export function rehypeCodeViewer() {
  return (tree) => {
    visit(tree, 'element', (node, index, parent) => {
      if (node.tagName !== 'pre' || !parent || index === undefined) return;
      const code = node.children.find((c) => c.type === 'element' && c.tagName === 'code');
      if (!code) return;
      const classes = code.properties?.className ?? [];
      const declared = (Array.isArray(classes) ? classes : [])
        .find((c) => typeof c === 'string' && c.startsWith('language-'))
        ?.slice('language-'.length)
        .toLowerCase();
      const language = ALIASES[declared] ?? declared;
      parent.children[index] = {
        type: 'element',
        tagName: 'nldd-code-viewer',
        properties: LANGUAGES.has(language) ? { language } : {},
        children: [{ type: 'text', value: text(code).replace(/\n$/, '') }],
      };
    });
  };
}
