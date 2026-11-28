import { describe, expect, it } from 'vitest';
import type { UndeliveredMessage } from './api';
import { standing } from './undelivered';

const MESSAGE: UndeliveredMessage = {
  id: 'm-1',
  kind: 'Offerte',
  reason: 'De ontvanger kent deze instantie niet',
  since: '2026-11-28T09:00:00Z',
  retry_until: '2026-12-05T09:00:00Z',
  final: false,
};

const plain = (text: string) => text.replace(/ | /g, ' ');

describe('standing', () => {
  it('says why, since when and until when grip tries', () => {
    const text = plain(standing(MESSAGE));
    expect(text).toMatch(/^De ontvanger kent deze instantie niet\. Sinds 28 nov/);
    expect(text).toMatch(/Grip probeert het tot 5 dec.* 2026.*\.$/);
  });

  it('says that a final message does not arrive by itself any more', () => {
    const text = plain(standing({ ...MESSAGE, final: true, retry_until: null }));
    expect(text).toMatch(/\. Komt niet meer vanzelf aan\.$/);
    expect(text).not.toContain('probeert');
  });

  it('says that a message sent again is on its way', () => {
    const text = plain(standing({ ...MESSAGE, retry_until: null }));
    expect(text).toMatch(/\. Wordt opnieuw verstuurd\.$/);
  });
});
