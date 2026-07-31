<template>
  <el-table :data="rows" class="compare-table" size="default">
    <el-table-column label="字段" min-width="140">
      <template #default="{ row }">
        <div class="f-label">{{ row.label }}</div>
        <div class="f-key">{{ row.key }}</div>
      </template>
    </el-table-column>
    <el-table-column :label="docAName || '文档 A'" min-width="160">
      <template #default="{ row }">
        <span class="val" :class="{ missing: row.value_a == null || row.value_a === '' }">{{ text(row.value_a) }}</span>
      </template>
    </el-table-column>
    <el-table-column :label="docBName || '文档 B'" min-width="160">
      <template #default="{ row }">
        <span class="val" :class="{ missing: row.value_b == null || row.value_b === '' }">{{ text(row.value_b) }}</span>
      </template>
    </el-table-column>
    <el-table-column label="状态" width="110">
      <template #default="{ row }"><StatusBadge :value="row.status" map="diff" /></template>
    </el-table-column>
    <el-table-column label="差异" width="110" align="right">
      <template #default="{ row }">
        <span v-if="row.delta_pct != null" class="delta" :class="{ up: row.delta_pct > 0, down: row.delta_pct < 0 }">{{ row.delta_pct > 0 ? '+' : '' }}{{ row.delta_pct }}%</span>
        <span v-else class="delta-none">—</span>
      </template>
    </el-table-column>
  </el-table>
</template>
<script setup>
import StatusBadge from '@/components/StatusBadge.vue'
defineProps({ rows: { type: Array, default: () => [] }, docAName: { type: String, default: '' }, docBName: { type: String, default: '' } })
function text(v) {
  if (v == null || v === '') return '—'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}
</script>
<style scoped>
.f-label { font-weight: 600; color: var(--dm-text); font-size: 13px; }
.f-key { font-size: 11px; color: var(--dm-text-faint); font-variant-numeric: tabular-nums; }
.val { font-size: 13px; color: var(--dm-text); word-break: break-all; }
.val.missing { color: var(--dm-text-faint); }
.delta { font-variant-numeric: tabular-nums; font-weight: 600; font-size: 12.5px; }
.delta.up { color: var(--dm-danger); }
.delta.down { color: var(--dm-success); }
.delta-none { color: var(--dm-text-faint); }
.compare-table :deep(.el-table__row:hover td) { background: var(--dm-fill); }
</style>
