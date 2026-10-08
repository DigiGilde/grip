/** The form behind an assignment: what a person types, and the request it becomes. */
import type { AssignmentDetail, AssignmentInput } from './api';

export interface FormState {
  name: string;
  kind: string;
  clientId: string;
  clientContact: string;
  startDate: string;
  endDate: string;
  notes: string;
}

export function initialState(assignment?: AssignmentDetail): FormState {
  return {
    name: assignment?.name ?? '',
    kind: assignment?.kind ?? 'external',
    clientId: assignment?.client_organisation_id ?? '',
    clientContact: assignment?.client_contact ?? '',
    startDate: assignment?.start_date ?? '',
    endDate: assignment?.end_date ?? '',
    notes: assignment?.notes ?? '',
  };
}

/** What is sent. Creating asks for the least that makes an assignment. */
export function assignmentInput(form: FormState, creating: boolean): AssignmentInput | string {
  if (!form.name.trim()) return 'Geef de opdracht een naam.';
  const external = form.kind === 'external';
  const input: AssignmentInput = {
    name: form.name.trim(),
    kind: form.kind,
    client_organisation_id: external ? form.clientId || null : null,
  };
  if (form.startDate && form.endDate && form.endDate < form.startDate) {
    return 'De einddatum ligt voor de begindatum.';
  }
  // The period is asked at once: budget lines and inzet follow it.
  if (creating) {
    return {
      ...input,
      ...(form.startDate ? { start_date: form.startDate } : {}),
      ...(form.endDate ? { end_date: form.endDate } : {}),
    };
  }
  return {
    ...input,
    client_contact: external ? form.clientContact.trim() || null : null,
    start_date: form.startDate || null,
    end_date: form.endDate || null,
    notes: form.notes.trim() || null,
  };
}
