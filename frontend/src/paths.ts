/** Every path in the application, in one place so links and routes cannot drift. */
export const PATHS = {
  statusOverview: '/',
  assignments: '/opdrachten',
  allocations: '/inzet',
  costs: '/kosten',
  rates: '/tarieven',
  team: '/team',
  login: '/inloggen',
  noAccess: '/geen-toegang',
} as const;
