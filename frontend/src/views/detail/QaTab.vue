<template>
  <div class="qa-tab">
    <div class="qa-split">
      <!-- 会话列表 -->
      <aside class="sessions">
        <div class="sessions-head">
          <span>会话</span>
          <el-button size="small" type="primary" circle @click="newSession"><el-icon><Plus /></el-icon></el-button>
        </div>
        <div v-if="sessionsLoading" class="sess-loading"><SkeletonLoader :rows="3" /></div>
        <div v-else class="sess-list">
          <div v-for="s in sessions" :key="s.id" class="sess" :class="{ active: currentSession && currentSession.id === s.id }" @click="selectSession(s.id)">
            <span class="sess-title">{{ s.title }}</span>
            <el-icon class="sess-del" @click.stop="removeSession(s.id)"><Delete /></el-icon>
          </div>
          <div v-if="!sessions.length" class="sess-empty">暂无会话<br />输入问题自动创建</div>
        </div>
      </aside>

      <!-- 消息区 -->
      <div class="chat">
        <div v-if="capabilities && !capabilities.llm" class="degraded"><el-icon><InfoFilled /></el-icon>当前未配置 API Key，问答运行在<strong>演示检索模式</strong>（规则降级回答）</div>

        <div ref="scrollRef" class="messages">
          <!-- 空态 -->
          <div v-if="!messages.length" class="welcome">
            <div class="w-avatar"><el-icon :size="26"><ChatDotRound /></el-icon></div>
            <div class="w-title">向这份文档提问</div>
            <div class="w-sub">回答会标注引用，点击角标可定位原文</div>
            <div class="w-questions">
              <el-button v-for="q in questions" :key="q" size="small" plain @click="quickAsk(q)">{{ q }}</el-button>
            </div>
          </div>

          <div v-for="m in messages" :key="m.id" class="msg-row" :class="m.role">
            <div class="bubble" :class="[m.role, { failed: m.failed }]">
              <StreamText v-if="m.role === 'assistant' && m.streaming" :text="m.content" :active="m.streaming" />
              <MarkdownView v-else-if="m.role === 'assistant'" :content="m.content" />
              <div v-else class="user-text">{{ m.content }}</div>
              <div v-if="m.failed" class="fail-actions">
                <el-button size="small" type="danger" plain @click="retry(m)">重试</el-button>
              </div>
              <div v-if="m.citations && m.citations.length" class="cites">
                <span v-for="(c, i) in m.citations" :key="i" class="cite" @click="openCite(c)">[{{ i + 1 }}]</span>
              </div>
              <div v-if="m.source" class="src-tag">{{ m.source === 'rule' ? '演示检索模式' : 'LLM 回答' }}</div>
            </div>
          </div>
        </div>

        <!-- 输入区 -->
        <div class="composer">
          <el-input v-model="draft" type="textarea" :rows="2" resize="none" placeholder="输入问题，Enter 发送，Shift+Enter 换行"
                    @keydown.enter.exact.prevent="send" @keydown.enter.shift.exact="() => {}" />
          <div class="composer-foot">
            <span class="scope">提问范围：{{ docName }}</span>
            <div class="composer-ops">
              <el-button v-if="streaming" @click="stop"><el-icon><VideoPause /></el-icon>停止</el-button>
              <el-button type="primary" :disabled="streaming || !draft.trim()" @click="send"><el-icon><Promotion /></el-icon>发送</el-button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <SourceDrawer v-model="drawerVisible" :citation="activeCitation" :chunk="activeChunk" />
  </div>
</template>
<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Delete, ChatDotRound, InfoFilled, VideoPause, Promotion } from '@element-plus/icons-vue'
import { api } from '@/api/index'
import { streamChat } from '@/api/chat'
import MarkdownView from '@/components/MarkdownView.vue'
import StreamText from '@/components/StreamText.vue'
import SourceDrawer from '@/components/SourceDrawer.vue'
import SkeletonLoader from '@/components/SkeletonLoader.vue'
const props = defineProps({ docId: { type: Number, required: true }, docName: { type: String, default: '' } })
const sessions = ref([])
const sessionsLoading = ref(true)
const currentSession = ref(null)
const messages = ref([])
const draft = ref('')
const streaming = ref(false)
const questions = ref([])
const capabilities = ref(null)
const chunkMap = ref({})
const controller = ref(null)
const scrollRef = ref(null)
const drawerVisible = ref(false)
const activeCitation = ref(null)
const activeChunk = ref(null)
let tempSeq = -1
async function loadSessions() {
  sessionsLoading.value = true
  try {
    const all = await api.listSessions()
    sessions.value = all.filter((s) => (s.doc_ids || []).includes(props.docId))
    if (!currentSession.value && sessions.value.length) selectSession(sessions.value[0].id)
  } catch (e) {
    ElMessage.error(e.message || '会话加载失败')
  } finally {
    sessionsLoading.value = false
  }
}
async function selectSession(id) {
  try {
    const data = await api.getSession(id)
    currentSession.value = data.session
    messages.value = data.messages.map((m) => ({ ...m, streaming: false, failed: false }))
    scrollBottom()
  } catch (e) {
    ElMessage.error(e.message || '会话加载失败')
  }
}
async function newSession() {
  try {
    const s = await api.createSession({ doc_ids: [props.docId], title: '新会话' })
    sessions.value.unshift(s)
    currentSession.value = s
    messages.value = []
  } catch (e) {
    ElMessage.error(e.message || '创建失败')
  }
}
async function removeSession(id) {
  try {
    await api.deleteSession(id)
    sessions.value = sessions.value.filter((s) => s.id !== id)
    if (currentSession.value && currentSession.value.id === id) {
      currentSession.value = null
      messages.value = []
    }
  } catch (e) {
    ElMessage.error(e.message || '删除失败')
  }
}
function scrollBottom() { nextTick(() => { const el = scrollRef.value; if (el) el.scrollTop = el.scrollHeight }) }
async function send() {
  const q = draft.value.trim()
  if (!q || streaming.value) return
  draft.value = ''
  if (!currentSession.value) await newSession()
  const sessionId = currentSession.value.id
  messages.value.push({ id: tempSeq--, role: 'user', content: q, citations: [], source: 'user' })
  const assistant = { id: tempSeq--, role: 'assistant', content: '', citations: [], source: '', streaming: true, failed: false }
  messages.value.push(assistant)
  scrollBottom()
  streaming.value = true
  const ac = new AbortController()
  controller.value = ac
  try {
    await streamChat(props.docId, {
      question: q,
      session_id: sessionId,
      doc_ids: [props.docId],
      stream: true,
    }, {
      onDelta: (text) => { assistant.content += text; scrollBottom() },
      onDone: () => {},
      onError: (msg) => { assistant.failed = true; assistant.content = assistant.content || msg },
    }, ac.signal)
  } catch (e) {
    if (e.name !== 'AbortError') {
      assistant.failed = true
      assistant.content = assistant.content || (e.message || '生成失败')
    }
  } finally {
    assistant.streaming = false
    streaming.value = false
    try {
      const data = await api.getSession(sessionId)
      const idx = messages.value.indexOf(assistant)
      if (idx >= 0) messages.value.splice(idx, 1)
      const last = data.messages[data.messages.length - 1]
      if (last && last.role === 'assistant') {
        messages.value.push({ ...last, streaming: false, failed: assistant.failed })
      }
    } catch { /* 刷新失败不阻塞 */ }
    scrollBottom()
  }
}
function stop() { if (controller.value) controller.value.abort() }
function quickAsk(q) { draft.value = q; send() }
function retry(m) {
  const q = m.content
  messages.value = messages.value.filter((x) => x.id !== m.id)
  draft.value = q
  send()
}
function openCite(c) {
  activeCitation.value = c
  activeChunk.value = chunkMap.value[c.chunk_id] || null
  drawerVisible.value = true
}
onMounted(async () => {
  loadSessions()
  try {
    const info = await api.demoInfo()
    questions.value = info.questions || []
    const settings = await api.getSettings()
    capabilities.value = settings.capabilities
  } catch { /* 降级：问题与能力提示不可用时不阻塞 */ }
  try {
    const data = await api.getDocument(props.docId)
    const map = {}
    for (const c of data.chunks || []) map[c.id] = c
    chunkMap.value = map
  } catch { /* ignore */ }
})
</script>
<style scoped>
.qa-split { display: flex; gap: 16px; height: calc(100vh - 240px); min-height: 420px; }
.sessions { width: 220px; flex-shrink: 0; background: var(--dm-card); border: 1px solid var(--dm-border); border-radius: var(--dm-radius); display: flex; flex-direction: column; }
.sessions-head { display: flex; align-items: center; justify-content: space-between; padding: 12px 14px; border-bottom: 1px solid #f1f5f9; font-size: 13px; font-weight: 600; }
.sess-list { flex: 1; overflow-y: auto; padding: 8px; display: flex; flex-direction: column; gap: 4px; }
.sess { display: flex; align-items: center; gap: 6px; padding: 9px 10px; border-radius: 8px; cursor: pointer; font-size: 12.5px; color: var(--dm-text); }
.sess:hover { background: #f8fafc; }
.sess.active { background: var(--dm-primary-light); color: var(--dm-primary); font-weight: 600; }
.sess-title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sess-del { color: var(--dm-text-muted); opacity: 0; } .sess:hover .sess-del { opacity: 1; } .sess-del:hover { color: var(--dm-danger); }
.sess-empty { padding: 24px 12px; text-align: center; font-size: 12px; color: var(--dm-text-muted); line-height: 1.8; }
.sess-loading { padding: 12px; }
.chat { flex: 1; min-width: 0; background: var(--dm-card); border: 1px solid var(--dm-border); border-radius: var(--dm-radius); display: flex; flex-direction: column; overflow: hidden; }
.degraded { display: flex; align-items: center; gap: 8px; padding: 9px 16px; background: #e8f4f8; color: var(--dm-teal); font-size: 12.5px; border-bottom: 1px solid #cde9f2; }
.messages { flex: 1; overflow-y: auto; padding: 20px 24px; display: flex; flex-direction: column; gap: 16px; }
.welcome { display: flex; flex-direction: column; align-items: center; padding: 48px 20px 24px; text-align: center; }
.w-avatar { width: 56px; height: 56px; border-radius: 16px; background: var(--dm-primary-light); color: var(--dm-primary); display: flex; align-items: center; justify-content: center; margin-bottom: 14px; }
.w-title { font-size: 17px; font-weight: 700; color: var(--dm-text); margin-bottom: 6px; }
.w-sub { font-size: 12.5px; color: var(--dm-text-muted); margin-bottom: 18px; }
.w-questions { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; max-width: 520px; }
.msg-row { display: flex; }
.msg-row.user { justify-content: flex-end; }
.bubble { max-width: 78%; border-radius: 12px; padding: 10px 14px; font-size: 13.5px; line-height: 1.7; position: relative; }
.bubble.user { background: var(--dm-primary); color: #fff; border-radius: 12px 4px 12px 12px; }
.bubble.assistant { background: #fff; border: 1px solid var(--dm-border); border-radius: 4px 12px 12px 12px; }
.bubble.failed { border-color: #f3c1c1; background: #fdf6f6; }
.user-text { white-space: pre-wrap; word-break: break-word; }
.cites { display: flex; gap: 6px; margin-top: 8px; flex-wrap: wrap; }
.cite { min-width: 22px; height: 22px; padding: 0 5px; border-radius: 6px; background: var(--dm-primary-light); color: var(--dm-primary); font-size: 11px; display: inline-flex; align-items: center; justify-content: center; cursor: pointer; transition: transform .15s; }
.cite:hover { transform: scale(1.08); background: #d7e5fb; }
.src-tag { margin-top: 6px; font-size: 10.5px; color: var(--dm-text-muted); }
.fail-actions { margin-top: 8px; }
.composer { border-top: 1px solid var(--dm-border); padding: 12px 14px; background: #fbfcfe; }
.composer :deep(.el-textarea__inner) { border-radius: 10px; font-size: 13.5px; line-height: 1.6; }
.composer-foot { display: flex; align-items: center; justify-content: space-between; margin-top: 8px; }
.scope { font-size: 12px; color: var(--dm-text-muted); }
.composer-ops { display: flex; gap: 8px; }
</style>
