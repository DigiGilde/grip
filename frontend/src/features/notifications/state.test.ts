import { describe, expect, it } from 'vitest';
import { blockedText } from './state';

describe('why notifications cannot be switched on here', () => {
  it('says nothing where they can', () => {
    expect(blockedText('off')).toBeNull();
    expect(blockedText('on')).toBeNull();
    expect(blockedText(null)).toBeNull();
  });

  it('tells an iPhone or iPad to install grip first', () => {
    expect(blockedText('needs-install')).toContain('Zet op beginscherm');
  });

  it('tells where to undo a block, since only the browser can', () => {
    expect(blockedText('denied')).toContain('instellingen van de site');
  });
});
