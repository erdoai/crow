/**
 * Auto-registers built-in content renderers.
 * Import this module once (e.g. in main.tsx) to activate them.
 */

import { registerRenderer } from './registry'
import { ChartRenderer } from './chart'

registerRenderer('chart', ChartRenderer)
