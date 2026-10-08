import { describe, expect, it } from 'vitest';
import { filledRoleLabel, roleLabel, typeConsequence } from './newVacancy';

const role = {
  budget_line_id: 'l1',
  assignment_id: 'a1',
  assignment_name: 'Opdracht Alfa',
  description: 'Adviseur',
  role: 'Adviseur',
  fte: '1.000',
  declarable: true,
};

describe('roles offered for a new vacancy', () => {
  it('says how much of an open role is open, and when the assignment is not agreed', () => {
    expect(roleLabel({ ...role, unfilled_fte: '0.500' })).toBe(
      'Opdracht Alfa: Adviseur (0,5 fte open)',
    );
    expect(roleLabel({ ...role, unfilled_fte: '1.000', tentative: true })).toBe(
      'Opdracht Alfa: Adviseur (1 fte open, onder voorbehoud)',
    );
  });

  it('says who fills a filled role and until when, only when the server gave it', () => {
    expect(
      filledRoleLabel({
        ...role,
        filled_by: [{ person_name: 'Voorbeeld Een', until: '2026-12-31' }],
      }),
    ).toBe('Opdracht Alfa: Adviseur (ingevuld door Voorbeeld Een t/m 31 dec 2026)');
    expect(filledRoleLabel(role)).toBe('Opdracht Alfa: Adviseur (ingevuld)');
  });

  it('gives the consequence of the chosen type only', () => {
    expect(typeConsequence('gerede')).toBe('Wordt niet opengesteld: de kandidaat is bekend.');
    expect(typeConsequence('beoogd')).toBe('Wordt niet opengesteld: de kandidaat is bekend.');
    expect(typeConsequence('regulier')).toBe('');
  });
});
