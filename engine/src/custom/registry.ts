import type {ComponentType} from 'react';

/**
 * Custom scene components by name, for `{"kind": "custom", "component": "<name>"}`.
 *
 * This committed file is an empty map and must stay that way. `render_video` writes the real
 * map for the duration of one render (see ./README.md) and restores this file afterwards.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const registry: Record<string, ComponentType<any>> = {};
