import { readFileSync } from 'node:fs';
import { basename } from 'node:path';
import { defineCollection } from 'astro:content';
import { glob, type Loader } from 'astro/loaders';
import { z } from 'astro/zod';
import { adrMeta, firstHeading } from './lib/docs.mjs';
import { ORGANISATIONS } from './lib/site';

const keepId = ({ entry }: { entry: string }) => entry.replace(/\.md$/, '');

/**
 * A glob loader whose entries get extra data read from the file itself before
 * the schema validates them: the Markdown here keeps its facts in the text
 * (the title, the status line of a decision) rather than in front matter.
 */
function withDerived(loader: Loader, derive: (filePath: string) => Record<string, unknown>): Loader {
  return {
    ...loader,
    load: (context) =>
      loader.load({
        ...context,
        parseData: (props) =>
          context.parseData({
            ...props,
            data: { ...props.data, ...(props.filePath ? derive(props.filePath) : {}) },
          }),
      }),
  };
}

const titleFrom = (filePath: string) => ({ title: firstHeading(readFileSync(filePath, 'utf8')) });

const titled = z.object({ title: z.string().min(1, 'de eerste kop (# ...) ontbreekt') });

/** docs/*.md and the rounds under docs/hierarchie, with docs/README.md as overview. */
const docs = defineCollection({
  loader: withDerived(
    glob({ base: '../docs', pattern: ['*.md', 'hierarchie/*.md'], generateId: keepId }),
    titleFrom,
  ),
  schema: titled,
});

/** The introductions of the decisions and of the Personaboek. */
const intros = defineCollection({
  loader: withDerived(
    glob({ base: '../docs', pattern: ['adr/README.md', 'personas/README.md'], generateId: keepId }),
    titleFrom,
  ),
  schema: titled,
});

const adr = defineCollection({
  loader: withDerived(
    glob({ base: '../docs/adr', pattern: '[0-9][0-9][0-9][0-9]-*.md', generateId: keepId }),
    adrMeta,
  ),
  schema: z
    .object({
      number: z.string().regex(/^\d{4}$/),
      headingNumber: z.string({ error: 'de kop begint niet met het nummer' }),
      title: z.string({ error: 'de eerste kop (# NNNN Titel) ontbreekt' }).min(1),
      status: z.enum(['voorgesteld', 'aanvaard', 'vervangen', 'afgewezen'], {
        error: 'de regel "Status: ..." ontbreekt of heeft een onbekende status',
      }),
      date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
    })
    .refine((d) => d.headingNumber === d.number, {
      message: 'het nummer in de kop verschilt van dat in de bestandsnaam',
      path: ['headingNumber'],
    }),
});

const grip = z.object({
  instantie: z.string().min(1),
  toegang: z.enum(['account', 'gast', 'via-federatie']),
  rechten: z.array(z.string()),
  relaties: z.array(z.string()),
  voorbeeldpersoon: z.string().nullable(),
  dataset: z.string().nullable(),
});

const personas = defineCollection({
  loader: withDerived(
    glob({ base: '../docs/personas', pattern: '[A-Z]*-*.md', generateId: keepId }),
    (filePath) => ({ file: basename(filePath, '.md') }),
  ),
  schema: z
    .object({
      file: z.string(),
      code: z.string().regex(/^(MIN|PRG|GLD|BHO|ODI)-[A-Z]+$/),
      naam: z.string().min(1),
      rol: z.string().min(1),
      organisatie: z.enum(ORGANISATIONS),
      eenheid: z.string().min(1),
      fgr: z.object({
        functie: z.string().min(1),
        familie: z.string().min(1),
        schaal: z.string().min(1),
        url: z.url(),
        inschatting: z.boolean(),
      }),
      mandaat: z.object({
        tekst: z.string().min(1),
        bron: z.string().min(1),
      }),
      grips: z.array(grip),
    })
    .refine((d) => d.code === d.file, {
      message: 'de code verschilt van de bestandsnaam',
      path: ['code'],
    }),
});

export const collections = { docs, intros, adr, personas };
