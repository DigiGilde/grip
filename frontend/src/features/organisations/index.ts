/**
 * Organisations: the list clients and contractors are picked from.
 *
 * Usage, in any form:
 *
 *   import { OrganisationPicker } from '@/features/organisations';
 *
 *   <OrganisationPicker
 *     label="Opdrachtgever"
 *     value={form.clientOrganisationId}            // string | null
 *     onChange={(organisation) => set({ clientOrganisationId: organisation?.id ?? null })}
 *   />
 *
 * The picker searches the whole list on the server, shows each result with
 * its abbreviation and its place in the hierarchy, and ends with one action
 * to add an organisation that is not in the list. Do not put a separate
 * "new organisation" text field next to it: adding goes through the picker.
 */
export { OrganisationPicker, type OrganisationPickerProps } from './OrganisationPicker';
export { organisationPlace, organisationText } from './text';
export {
  fetchOrganisation,
  organisationKeys,
  searchOrganisations,
  type Organisation,
} from './api';
