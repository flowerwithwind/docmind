import { describe, expect, it, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import ResultChart from '@/components/ResultChart.vue'
import { buildChartOption } from '@/utils/chart'
import * as echarts from 'echarts'

vi.mock('echarts', () => ({
  init: vi.fn(() => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() })),
  use: vi.fn(),
}))

if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
}

async function mountChart(chart) {
  const wrapper = mount(ResultChart, {
    props: { chart },
    global: { plugins: [ElementPlus] },
  })
  await flushPromises()
  return wrapper
}

describe('ResultChart 图表分发', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('bar 类型走 ECharts 柱状图', async () => {
    const wrapper = await mountChart({
      type: 'bar',
      columns: ['月份', '销售额'],
      rows: [['2026-01', 1200000], ['2026-02', 1350000]],
    })
    expect(echarts.init).toHaveBeenCalledTimes(1)
    const option = echarts.init.mock.results[0].value.setOption.mock.calls[0][0]
    expect(option.series[0].type).toBe('bar')
    expect(option.series[0].data).toEqual([1200000, 1350000])
    expect(wrapper.find('.chart-canvas').exists()).toBe(true)
  })

  it('line 类型走 ECharts 折线图（多系列）', async () => {
    const wrapper = await mountChart({
      type: 'line',
      columns: ['月份', '服务器', '交换机'],
      rows: [['2026-01', 120, 45], ['2026-02', 135, 42]],
    })
    expect(echarts.init).toHaveBeenCalledTimes(1)
    const option = echarts.init.mock.results[0].value.setOption.mock.calls[0][0]
    expect(option.series.map((s) => s.type)).toEqual(['line', 'line'])
    expect(option.series.map((s) => s.name)).toEqual(['服务器', '交换机'])
    expect(option.xAxis.data).toEqual(['2026-01', '2026-02'])
  })

  it('table 类型直接渲染表格，不初始化 ECharts', async () => {
    const wrapper = await mountChart({
      type: 'table',
      columns: ['月份', '销售额'],
      rows: [['2026-01', 1200000]],
    })
    expect(echarts.init).not.toHaveBeenCalled()
    expect(wrapper.find('.chart-table').exists()).toBe(true)
    expect(wrapper.findAll('.el-table__row').length).toBe(1)
    expect(wrapper.text()).toContain('2026-01')
  })

  it('空数据展示空态', async () => {
    const wrapper = await mountChart({ type: 'line', columns: [], rows: [] })
    expect(echarts.init).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('暂无图表数据')
  })
})

describe('buildChartOption', () => {
  it('数字串清洗为数值', () => {
    const option = buildChartOption({
      type: 'bar',
      columns: ['月份', '销售额'],
      rows: [['2026-01', '1,200,000']],
    })
    expect(option.series[0].data).toEqual([1200000])
  })
})
