/**
 * The staffing of one assignment: per role what is asked, who fills it and
 * what is open. No amounts. A team member gets `names` and nothing of time.
 */
import { apiGet } from '@/api/client';
import type { BoardBar } from '@/features/allocations/board/api';

export interface RoleMonth {
  month: string;
  asked_pct: string;
  filled_pct: string;
  open_pct: string;
  over: boolean;
  closed: boolean;
}

export interface RoleGap {
  /** First days of the first and the last month of the gap. */
  start: string;
  end: string;
  open_fte: string;
}

export interface RoleBar extends BoardBar {
  /** The person is hired but has not started yet. */
  starts_on?: string | null;
  before_start?: boolean;
  outside_role_period?: boolean;
}

export interface RoleStaffing {
  budget_line_id: string;
  description: string;
  role?: string | null;
  fte?: string;
  start_date?: string | null;
  end_date?: string | null;
  months?: RoleMonth[];
  bars: RoleBar[];
  gaps?: RoleGap[];
  fully_staffed?: boolean;
  names?: string[];
  can_fill?: boolean;
}

export interface AssignmentStaffing {
  assignment_id: string;
  months: string[];
  current_month: string;
  closed_months?: string[];
  tentative: boolean;
  roles: RoleStaffing[];
  role_count?: number;
  staffed_count?: number;
  open_fte?: string | null;
  open_from?: string | null;
  overbooked_count?: number;
}

export const staffingKeys = {
  assignment: (id: string) => ['allocations', 'staffing', id] as const,
};

export const fetchAssignmentStaffing = (id: string) =>
  apiGet<AssignmentStaffing>(`/api/assignments/${id}/staffing`);
