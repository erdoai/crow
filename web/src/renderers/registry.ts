/**
 * Pluggable content-part renderer registry.
 *
 * Agents emit custom content types in their message content (JSONB array).
 * Renderers transform these into React components for display.
 *
 * External code registers renderers without modifying core Crow:
 *
 *     import { registerRenderer } from '@/renderers/registry'
 *     registerRenderer('my-widget', MyWidgetComponent)
 *
 * Built-in renderers (chart) are auto-registered in ./index.ts
 */

import type { ComponentType } from 'react'

export interface RendererProps {
  /** The full content part object from the message JSONB array. */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data: Record<string, any>
}

const registry = new Map<string, ComponentType<RendererProps>>()

/** Register a React component to render a given content-part type. */
export function registerRenderer(
  contentType: string,
  component: ComponentType<RendererProps>,
): void {
  registry.set(contentType, component)
}

/** Look up a renderer for a content-part type. Returns undefined if none registered. */
export function getRenderer(
  contentType: string,
): ComponentType<RendererProps> | undefined {
  return registry.get(contentType)
}

/** Check whether a content-part type has a registered renderer. */
export function hasRenderer(contentType: string): boolean {
  return registry.has(contentType)
}
