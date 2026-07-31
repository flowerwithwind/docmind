/** 任务轮询 composable：running/progress/message/error + run()。 */
import { ref } from 'vue'
import { pollTask } from '@/api/http'

export function useTask() {
  const running = ref(false)
  const progress = ref(0)
  const message = ref('')
  const error = ref('')
  const taskId = ref(null)

  async function run(id, { onDone, interval = 600, timeoutMs = 600000 } = {}) {
    running.value = true
    error.value = ''
    progress.value = 0
    message.value = ''
    taskId.value = id
    try {
      const task = await pollTask(id, {
        interval,
        timeoutMs,
        onProgress: (t) => {
          progress.value = t.progress || 0
          message.value = t.message || ''
        },
      })
      progress.value = 100
      if (onDone) onDone(task)
      return task
    } catch (e) {
      error.value = e.message || '任务失败'
      throw e
    } finally {
      running.value = false
    }
  }

  function reset() {
    running.value = false
    progress.value = 0
    message.value = ''
    error.value = ''
    taskId.value = null
  }

  return { running, progress, message, error, taskId, run, reset }
}
