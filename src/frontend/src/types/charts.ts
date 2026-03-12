/**
 * Shared ECharts callback parameter types.
 * Use these instead of `any` in chart components for better type safety.
 */

/** Axis-trigger tooltip formatter params (array when trigger: 'axis'). */
export interface AxisTooltipParam {
  axisValue: string
  marker: string
  seriesName: string
  value: number
}

/** Heatmap cell params: [monthIndex, yearIndex, value]. */
export interface HeatmapDataParam {
  data: [number, number, number | string]
}

/** Legend select changed event params. */
export interface LegendSelectParams {
  selected: Record<string, boolean>
}

/** Bar/candlestick itemStyle color callback params (volume color: data[2]=1 red, -1 green). */
export interface BarColorParams {
  data: unknown[]
}

/** ECharts axis link xAxisIndex value (e.g. 'all' for synced axis). */
export type AxisLinkXAxisIndex = 'all' | number | number[]
