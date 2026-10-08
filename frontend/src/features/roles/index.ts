/**
 * Roles: the fixed list a personnel budget line picks its role from.
 *
 * Usage, in any form:
 *
 *   import { RolePicker } from '@/features/roles';
 *
 *   <RolePicker
 *     label="Rol"
 *     value={form.role}                                   // the role name, or null
 *     onChange={(role) => set({ role: role?.name ?? null })}
 *   />
 *
 * Send the name as the `role` of the budget line; the server finds the role
 * in the catalogue by it. The picker offers "Staat er niet tussen? Voeg ...
 * toe als rol" only when no role has the typed name and the reader may add
 * one. Do not put a free-text role field next to it.
 */
export { RolePicker, type RolePickerProps } from './RolePicker';
export { fetchRoles, roleKeys, type CatalogueRole } from './api';
