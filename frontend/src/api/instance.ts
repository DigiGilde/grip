import { apiGet } from './client';

/** The grip instance this frontend belongs to. */
export interface InstanceInfo {
  name: string;
  base_uri: string;
  /** An instance that holds only fictional example data. */
  example?: boolean;
}

export function fetchInstance(): Promise<InstanceInfo> {
  return apiGet<InstanceInfo>('/api/instance');
}
