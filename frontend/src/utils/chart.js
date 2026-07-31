/** 表格问答图表工具：把后端 chart 数据（columns/rows）转换为 ECharts option（line/bar）。 */

function toNumber(value) {
  if (typeof value === 'number') return value
  const n = Number(String(value ?? '').replace(/[,，\s]/g, ''))
  return Number.isFinite(n) ? n : 0
}

export function buildChartOption(chart = {}) {
  const columns = chart.columns || []
  const rows = chart.rows || []
  const type = chart.type === 'bar' ? 'bar' : 'line'
  const categories = rows.map((r, i) => (columns[0] ? String(r[0] ?? i + 1) : `第 ${i + 1} 行`))
  const seriesColumns = columns.length > 1 ? columns.slice(1) : columns
  const series = seriesColumns.map((col, si) => ({
    name: col,
    type,
    smooth: type === 'line',
    data: rows.map((r) => toNumber(columns.length > 1 ? r[si + 1] : r[si])),
  }))
  const multi = series.length > 1
  return {
    tooltip: { trigger: 'axis' },
    legend: multi ? { top: 0, type: 'scroll' } : undefined,
    grid: { left: 48, right: 24, top: multi ? 36 : 24, bottom: 44 },
    xAxis: {
      type: 'category',
      data: categories,
      axisLabel: { rotate: categories.some((c) => String(c).length > 6) ? 30 : 0 },
    },
    yAxis: { type: 'value' },
    series,
  }
}
