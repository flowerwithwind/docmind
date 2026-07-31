import { describe, expect, it, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import TableQaTab from '@/views/detail/TableQaTab.vue'
import { api } from '@/api/index'
import * as echarts from 'echarts'

vi.mock('@/api/index', () => ({
  api: {
    listQaTables: vi.fn(),
    getDocument: vi.fn(),
    tableQa: vi.fn(),
  },
}))

vi.mock('echarts', () => ({
  init: vi.fn(() => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() })),
  use: vi.fn(),
}))

// jsdom 缺少 ResizeObserver，Element Plus 表格/下拉组件需要
if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
}

const REGISTERED = [
  { id: 'demo_sales', name: '演示销售表', columns: ['月份', '产品', '销售额', '销量'], row_count: 6, source: 'demo', created_at: '' },
]

const DEMO_RESULT = {
  answer: '「销售额」合计：5,460,000（共 6 条数值记录）',
  sql: 'SELECT SUM(c3) AS 结果 FROM t',
  columns: ['结果'],
  rows: [[5460000]],
  chart: { type: 'table', columns: ['结果'], rows: [[5460000]] },
  source: 'demo',
  tables: ['demo_sales'],
  metrics: { elapsed_ms: 12, attempts: 1, tokens: 0, intent: 'aggregate', table_id: 'demo_sales', table_name: '演示销售表', row_count: 6, fallback_reason: '未配置 API Key，规则降级' },
}

const LLM_RESULT = {
  answer: '查询到 2 行结果',
  sql: 'SELECT 月份, 销售额 FROM t LIMIT 100',
  columns: ['月份', '销售额'],
  rows: [['2026-01', 1200000], ['2026-02', 1350000]],
  chart: { type: 'line', columns: ['月份', '销售额'], rows: [['2026-01', 1200000], ['2026-02', 1350000]] },
  source: 'llm',
  tables: ['demo_sales'],
  metrics: { elapsed_ms: 830, attempts: 1, tokens: 120, intent: 'list', table_id: 'demo_sales', table_name: '演示销售表', row_count: 6, fallback_reason: '' },
}

async function mountTab({ chunks = [] } = {}) {
  api.listQaTables.mockResolvedValue(REGISTERED)
  api.getDocument.mockResolvedValue({ chunks })
  const wrapper = mount(TableQaTab, {
    props: { docId: 1 },
    global: { plugins: [ElementPlus] },
  })
  await flushPromises()
  return wrapper
}

async function pickTable(wrapper, key) {
  await wrapper.findComponent({ name: 'ElSelect' }).setValue(key)
  await wrapper.vm.$nextTick()
}

async function typeQuestion(wrapper, text) {
  await wrapper.find('textarea').setValue(text)
  await wrapper.vm.$nextTick()
}

async function clickAsk(wrapper) {
  const btn = wrapper.findAll('button').find((b) => b.text().includes('提问'))
  await btn.trigger('click')
  await flushPromises()
  await wrapper.vm.$nextTick()
}

describe('TableQaTab 表格问答', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('渲染查询结果表格（llm 来源）', async () => {
    api.tableQa.mockResolvedValue(LLM_RESULT)
    const wrapper = await mountTab()
    await pickTable(wrapper, 'table:demo_sales')
    await typeQuestion(wrapper, '列出销售额')
    await clickAsk(wrapper)

    expect(api.tableQa).toHaveBeenCalledWith({ question: '列出销售额', table_id: 'demo_sales' })
    expect(wrapper.text()).toContain('查询到 2 行结果')
    expect(wrapper.text()).toContain('LLM 生成')
    expect(wrapper.find('.table-card').findAll('.el-table__row').length).toBe(2)
    expect(wrapper.text()).toContain('2026-01')
    expect(wrapper.text()).toContain('1200000')
    expect(wrapper.text()).toContain('SELECT 月份, 销售额 FROM t LIMIT 100')
  })

  it('chart.type=line 时用 ECharts 渲染并分发正确类型', async () => {
    api.tableQa.mockResolvedValue(LLM_RESULT)
    const wrapper = await mountTab()
    await pickTable(wrapper, 'table:demo_sales')
    await typeQuestion(wrapper, '按月看销售额')
    await clickAsk(wrapper)

    expect(echarts.init).toHaveBeenCalled()
    const option = echarts.init.mock.results[0].value.setOption.mock.calls[0][0]
    expect(option.series[0].type).toBe('line')
    expect(option.xAxis.data).toEqual(['2026-01', '2026-02'])
  })

  it('chart.type=table 时直接渲染表格且不初始化 ECharts', async () => {
    api.tableQa.mockResolvedValue(DEMO_RESULT)
    const wrapper = await mountTab()
    await pickTable(wrapper, 'table:demo_sales')
    await typeQuestion(wrapper, '销售额合计多少？')
    await clickAsk(wrapper)

    expect(echarts.init).not.toHaveBeenCalled()
    expect(wrapper.find('.chart-card').findAll('.el-table__row').length).toBe(1)
  })

  it('source=demo 或 fallback_reason 存在时显示规则降级徽标', async () => {
    api.tableQa.mockResolvedValue(DEMO_RESULT)
    const wrapper = await mountTab()
    await pickTable(wrapper, 'table:demo_sales')
    await typeQuestion(wrapper, '销售额合计多少？')
    await clickAsk(wrapper)

    expect(wrapper.find('.demo-badge').exists()).toBe(true)
    expect(wrapper.find('.demo-badge').text()).toContain('规则降级')
    expect(wrapper.text()).toContain('降级原因：未配置 API Key，规则降级')
    expect(wrapper.text()).toContain('耗时 12 ms')
  })

  it('未选择表格时给出明确提示且不调用接口', async () => {
    const wrapper = await mountTab()
    await typeQuestion(wrapper, '有多少行？')
    await wrapper.find('textarea').trigger('keydown.enter')
    await flushPromises()

    expect(wrapper.text()).toContain('请先选择要查询的表格')
    expect(api.tableQa).not.toHaveBeenCalled()
  })

  it('问题为空时给出明确提示且不调用接口', async () => {
    const wrapper = await mountTab()
    await pickTable(wrapper, 'table:demo_sales')
    await wrapper.find('textarea').trigger('keydown.enter')
    await flushPromises()

    expect(wrapper.text()).toContain('请输入问题后再提问')
    expect(api.tableQa).not.toHaveBeenCalled()
  })

  it.each([
    [400, '问题不能为空', '请求参数有误（400）'],
    [404, '表格不存在：t999', '表格或文档不存在（404）'],
    [409, '文档尚未完成解析，请稍后重试', '文档尚未完成解析（409）'],
  ])('接口报错 %s 时展示明确错误提示', async (status, message, title) => {
    const err = new Error(message)
    err.status = status
    api.tableQa.mockRejectedValueOnce(err)
    const wrapper = await mountTab()
    await pickTable(wrapper, 'table:demo_sales')
    await typeQuestion(wrapper, '查询数据')
    await clickAsk(wrapper)

    expect(wrapper.find('.error-card').exists()).toBe(true)
    expect(wrapper.find('.error-card').text()).toContain(title)
    expect(wrapper.find('.error-card').text()).toContain(message)
  })

  it('文档内表格块可选，并使用 doc_id 提问', async () => {
    api.tableQa.mockResolvedValue(LLM_RESULT)
    const wrapper = await mountTab({
      chunks: [{ id: 7, kind: 'table', title: '财务报表', page: 3, content: '| 月份 | 销售额 |' }],
    })
    expect(wrapper.vm.docTables).toHaveLength(1)
    expect(wrapper.vm.docTables[0].label).toContain('财务报表')
    await pickTable(wrapper, 'doc:7')
    await typeQuestion(wrapper, '销售额多少？')
    await clickAsk(wrapper)

    expect(api.tableQa).toHaveBeenCalledWith({ question: '销售额多少？', doc_id: 1 })
  })
})
