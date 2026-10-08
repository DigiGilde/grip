import { beforeEach, describe, expect, it, vi } from 'vitest';

const startAuthentication = vi.fn();
vi.mock('@simplewebauthn/browser', () => ({
  startAuthentication: (...args: unknown[]) => startAuthentication(...args),
  startRegistration: vi.fn(),
}));
const apiPost = vi.fn();
vi.mock('@/api/client', () => ({
  apiPost: (...args: unknown[]) => apiPost(...args),
  apiGet: vi.fn(),
  apiDelete: vi.fn(),
}));

import { navigation, leaveForDecision, type DecisionIntent } from '@/features/quotes/proof';
import { confirmWithPasskey } from './api';

const STEP = {
  options_url: '/api/proof/intents/1/passkey/options',
  verify_url: '/api/proof/intents/1/passkey',
};

function intent(passkey: DecisionIntent['passkey']): DecisionIntent {
  return {
    id: '1',
    authorize_url: '/api/proof/intents/1/authorize',
    expires_at: '2026-10-08T12:00:00Z',
    reauthentication: true,
    passkey,
  };
}

describe('confirming a decision with a passkey', () => {
  beforeEach(() => {
    startAuthentication.mockReset();
    apiPost.mockReset();
    vi.stubGlobal('PublicKeyCredential', function PublicKeyCredential() {});
  });

  it('asks the device with the server options and sends its answer back', async () => {
    apiPost
      .mockResolvedValueOnce({ options_json: '{"challenge":"abc"}' })
      .mockResolvedValueOnce({});
    startAuthentication.mockResolvedValue({ id: 'cred' });
    expect(await confirmWithPasskey(STEP)).toBe(true);
    expect(startAuthentication).toHaveBeenCalledWith({ optionsJSON: { challenge: 'abc' } });
    expect(apiPost).toHaveBeenLastCalledWith(STEP.verify_url, { credential: '{"id":"cred"}' });
  });

  it('is never a condition: a closed prompt or a refusal lets the decision go on', async () => {
    apiPost.mockResolvedValueOnce({ options_json: '{}' });
    startAuthentication.mockRejectedValue(
      Object.assign(new Error('nee'), { name: 'NotAllowedError' }),
    );
    expect(await confirmWithPasskey(STEP)).toBe(false);
    apiPost.mockRejectedValueOnce(new Error('server'));
    expect(await confirmWithPasskey(STEP)).toBe(false);
    expect(await confirmWithPasskey(null)).toBe(false);
  });

  it('leaves for the identity provider at once when there is no passkey', () => {
    const go = vi.spyOn(navigation, 'go').mockImplementation(() => undefined);
    leaveForDecision(intent(null));
    expect(go).toHaveBeenCalledWith('/api/proof/intents/1/authorize');
    expect(apiPost).not.toHaveBeenCalled();
    go.mockRestore();
  });

  it('asks for the passkey first and leaves afterwards, whatever the device says', async () => {
    const go = vi.spyOn(navigation, 'go').mockImplementation(() => undefined);
    apiPost.mockRejectedValue(new Error('geen verbinding'));
    leaveForDecision(intent(STEP));
    expect(go).not.toHaveBeenCalled();
    await vi.waitFor(() => expect(go).toHaveBeenCalledWith('/api/proof/intents/1/authorize'));
    go.mockRestore();
  });
});
