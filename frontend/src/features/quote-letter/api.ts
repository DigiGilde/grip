import { apiGet, apiPatch, apiPost } from '@/api/client';

export interface SenderContact {
  name: string;
  role: string;
  email: string;
  phone: string;
}

export interface SenderSignatory {
  on_behalf_of: string;
  name: string;
  title: string;
  organisation: string;
}

export interface Sender {
  organisation: string;
  part_of: string[];
  unit: string;
  visiting_address: string[];
  postal_address: string[];
  orders_email: string;
  website: string;
  contact: SenderContact;
  signatory: SenderSignatory;
}

/** A section of a quote: prose a person writes, or a standard text. */
export interface TextBlock {
  key: string;
  heading: string;
  body: string;
  hint: string;
  included: boolean;
  with_costs: boolean;
  numbered: boolean;
  draftable: boolean;
}

export interface LetterTexts {
  opening: string;
  closing: string;
  billing_annex: boolean;
}

export interface QuoteSender {
  sender: Sender;
  text_blocks: TextBlock[];
  letter: LetterTexts;
  ai_disclosure: boolean;
  drafting_available: boolean;
  profiles: string[];
  placeholders: string[];
}

export const senderKeys = { all: ['quote-sender'] as const };

export const fetchQuoteSender = () => apiGet<QuoteSender>('/api/quote-sender');

export const saveQuoteSender = (
  change: Partial<Pick<QuoteSender, 'sender' | 'text_blocks' | 'letter' | 'ai_disclosure'>>,
) => apiPatch<QuoteSender>('/api/quote-sender', change);

export const applyProfile = (name: string) =>
  apiPost<QuoteSender>(`/api/quote-sender/profiles/${encodeURIComponent(name)}`);
