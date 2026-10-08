import { useId, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { createPortal } from 'react-dom';
import { orUndef, useNlddEvent } from '@/components/nldd/events';
import { Facts, Quiet, Stack, type Fact } from '@/ui/layout';
import { codeLines } from './format';
import { CopyButton } from './ui';
import './register';

// The design system has no monospace text component; its own token keeps
// the code in the typeface the system uses for code.
const CODE = { fontFamily: 'var(--primitives-font-family-monospace)' } as const;

interface QuoteDetailsProps {
  /** The echtheidskenmerk: the hash of the frozen content. */
  hash: string;
  /** Further facts of the quote: its reference, who made it, its address. */
  facts?: readonly Fact[];
  /** The address of the quote's pdf; its file hash is read from there once the sheet opens. */
  documentHref?: string;
  /** The file hash, where the response already carries it. */
  fileHash?: string | null;
  /** A ready sentence of the server on the file, e.g. that it was fixed after making. */
  fileNote?: string | null;
}

/**
 * The details of a quote behind one quiet button, in a sheet: a sheet is
 * always inside the screen and wide enough to read, which a floating box
 * next to its button is not.
 *
 * The main thing in it is the echtheidskenmerk, said in words for someone
 * who has never heard of a hash.
 */
/** The SHA-256 of the stored pdf, from the header the server sends with it. */
async function fetchFileHash(href: string): Promise<string | null> {
  const response = await fetch(href, { credentials: 'include' });
  const hash = response.headers.get('X-Document-SHA256');
  // Only the header is needed; the file itself is not read.
  void response.body?.cancel();
  return response.ok ? hash : null;
}

export function QuoteDetails({
  hash,
  facts = [],
  documentHref,
  fileHash,
  fileNote,
}: QuoteDetailsProps) {
  const [open, setOpen] = useState(false);
  // The server names the hash of the stored file in a header of the file
  // itself. Asked only when someone opens the details.
  const file = useQuery({
    queryKey: ['quotes', 'file-hash', documentHref],
    queryFn: () => fetchFileHash(documentHref ?? ''),
    // Only where the response did not say it already.
    enabled: open && Boolean(documentHref) && !fileHash,
    retry: false,
    staleTime: Infinity,
  });
  const buttonRef = useRef<HTMLElement>(null);
  const sheetRef = useRef<HTMLElement>(null);
  const barRef = useRef<HTMLElement>(null);
  const titleId = useId();
  const shownFileHash = fileHash || file.data || null;
  useNlddEvent(buttonRef, 'click', () => setOpen(true));
  useNlddEvent(sheetRef, 'close', () => setOpen(false));
  useNlddEvent(barRef, 'dismiss', () => setOpen(false));

  return (
    <>
      <nldd-button ref={buttonRef} size="sm" text="Details" />
      {createPortal(
        <nldd-sheet ref={sheetRef} open={orUndef(open)} placement="right" width="480px">
          <nldd-page>
            <nldd-top-title-bar
              ref={barRef}
              slot="header"
              text="Details van de offerte"
              dismiss-text="Sluit"
              collapse-anchor={titleId}
            />
            <nldd-simple-section>
              <nldd-title
                id={titleId}
                slot="header"
                size={2}
                text="Details van de offerte"
                heading-level={1}
              />
              <Stack gap="group">
                {facts.length > 0 ? (
                  <Facts label="Gegevens van de offerte" facts={facts} labelWidth="140px" />
                ) : null}
                <Stack gap="related">
                  <nldd-title size={5} heading-level={2} text="Echtheidskenmerk" />
                  <nldd-text>
                    Een code die uit de inhoud van deze offerte is berekend. Verandert er ook maar
                    één teken, dan is de code anders.
                  </nldd-text>
                  <nldd-text>
                    Dezelfde code staat in het akkoord van de opdrachtgever. Zo staat vast dat er
                    voor precies deze offerte is getekend.
                  </nldd-text>
                  <Stack gap="tight">
                    {codeLines(hash).map((line) => (
                      <nldd-text key={line} size="sm" style={CODE} data-code-line>
                        {line}
                      </nldd-text>
                    ))}
                  </Stack>
                  <nldd-button-group>
                    <CopyButton text="Kopieer echtheidskenmerk" value={hash} />
                  </nldd-button-group>
                  <Quiet>Technisch: SHA-256 over de vastgelegde inhoud van de offerte.</Quiet>
                </Stack>
                {shownFileHash ? (
                  <Stack gap="related">
                    <nldd-title size={5} heading-level={2} text="Bestandskenmerk" />
                    <nldd-text>
                      Een code die uit het pdf-bestand van deze offerte is berekend. Zo ga je na dat
                      een pdf die je hebt precies dit bestand is.
                    </nldd-text>
                    <Stack gap="tight">
                      {codeLines(shownFileHash).map((line) => (
                        <nldd-text key={line} size="sm" style={CODE} data-file-line>
                          {line}
                        </nldd-text>
                      ))}
                    </Stack>
                    <nldd-button-group>
                      <CopyButton text="Kopieer bestandskenmerk" value={shownFileHash} />
                    </nldd-button-group>
                    {fileNote ? <Quiet>{fileNote}</Quiet> : null}
                  </Stack>
                ) : null}
              </Stack>
            </nldd-simple-section>
          </nldd-page>
        </nldd-sheet>,
        document.body,
      )}
    </>
  );
}
