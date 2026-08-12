<template>
  <section class="responsibility-track" aria-label="岗位责任轨道">
    <ol v-if="tasks.length" class="track-list">
      <li v-for="task in tasks" :key="task.id" class="track-row" data-task-row>
        <div class="sequence" :aria-label="`流程序号 ${task.sequence + 1}`">
          {{ String(task.sequence + 1).padStart(2, '0') }}
        </div>
        <div class="rail" aria-hidden="true"><span /></div>
        <article class="task-card">
          <header class="task-header">
            <div>
              <h4>{{ task.node_name }}</h4>
              <p>{{ task.required_position_name || task.required_position_code }}</p>
            </div>
            <div class="badges">
              <el-tag size="small" effect="plain" :type="task.mode === 'designated_user' ? 'warning' : 'info'">
                {{ task.mode === 'designated_user' ? '指定人员' : '共享岗位' }}
              </el-tag>
              <el-tag size="small" effect="plain" :type="statusMeta(task.status).type">
                {{ statusMeta(task.status).label }}
              </el-tag>
            </div>
          </header>
          <p v-if="task.mode === 'designated_user'" class="designated">
            指定办理人：{{ task.designated_user?.full_name || '待改派' }}
          </p>
          <div v-if="task.actions?.length" class="audit-list">
            <div v-for="entry in task.actions" :key="entry.id" class="audit-entry">
              <template v-if="entry.action === 'reassign'">
                <div class="audit-title">
                  <span>改派</span>
                  <time>{{ formatTime(entry.created_at) }}</time>
                </div>
                <p>{{ entry.previous_assignee_name || '原办理人' }} → {{ entry.new_assignee_name || '待指定' }}</p>
                <p v-if="entry.reason || entry.comment" class="comment">{{ entry.reason || entry.comment }}</p>
              </template>
              <template v-else>
                <div class="audit-title">
                  <span>{{ actionLabel(entry.action) }} · {{ entry.actor_name }}</span>
                  <time>{{ formatTime(entry.created_at) }}</time>
                </div>
                <p class="actor-position">{{ entry.position_name }}</p>
                <p v-if="entry.comment" class="comment">{{ entry.comment }}</p>
              </template>
            </div>
          </div>
          <p v-else class="no-action">尚无办理记录</p>
        </article>
      </li>
    </ol>
    <el-empty v-else :image-size="56" description="暂无可展示的岗位责任轨道" />
  </section>
</template>

<script setup>
defineProps({ tasks: { type: Array, default: () => [] } })

const STATUS = {
  pending: { label: '待激活', type: 'info' },
  active: { label: '办理中', type: 'warning' },
  completed: { label: '已完成', type: 'success' },
  returned: { label: '已退回', type: 'danger' },
  awaiting_reassignment: { label: '待改派', type: 'danger' },
  cancelled: { label: '已取消', type: 'info' }
}

function statusMeta(status) {
  return STATUS[status] || { label: status || '未知', type: 'info' }
}

function actionLabel(action) {
  return { submit: '提交', approve: '通过', return: '退回' }[action] || action
}

function formatTime(value) {
  return value ? String(value).replace('T', ' ').slice(0, 19) : ''
}
</script>

<style scoped>
.responsibility-track { --track-accent: var(--el-color-primary); }
.track-list { list-style: none; margin: 0; padding: 0; }
.track-row { display: grid; grid-template-columns: 34px 18px minmax(0, 1fr); gap: 8px; min-height: 96px; }
.sequence { padding-top: 13px; color: var(--el-text-color-placeholder); font: 600 12px/1 var(--el-font-family); letter-spacing: .08em; }
.rail { position: relative; display: flex; justify-content: center; }
.rail::before { content: ''; position: absolute; inset: 0 auto; width: 1px; background: var(--el-border-color); }
.rail span { z-index: 1; width: 9px; height: 9px; margin-top: 15px; border: 2px solid var(--track-accent); border-radius: 50%; background: var(--el-bg-color); }
.task-card { min-width: 0; margin-bottom: 12px; padding: 12px 14px; border: 1px solid var(--el-border-color-lighter); border-radius: var(--el-border-radius-base); background: var(--el-bg-color); }
.task-header { display: flex; justify-content: space-between; gap: 12px; }
.task-header h4 { margin: 0; color: var(--el-text-color-primary); font-size: 14px; }
.task-header p, .designated, .no-action { margin: 4px 0 0; color: var(--el-text-color-secondary); font-size: 12px; }
.badges { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 6px; }
.designated { color: var(--el-color-warning-dark-2); }
.audit-list { margin-top: 10px; border-top: 1px solid var(--el-border-color-extra-light); }
.audit-entry { padding: 9px 0 0; font-size: 13px; }
.audit-entry + .audit-entry { margin-top: 9px; border-top: 1px dashed var(--el-border-color-extra-light); }
.audit-entry p { margin: 3px 0 0; color: var(--el-text-color-regular); }
.audit-title { display: flex; justify-content: space-between; gap: 12px; font-weight: 600; }
.audit-title time { flex: none; color: var(--el-text-color-placeholder); font-weight: 400; font-size: 12px; }
.audit-entry .actor-position, .audit-entry .comment { color: var(--el-text-color-secondary); }
@media (max-width: 640px) {
  .track-row { grid-template-columns: 28px 14px minmax(0, 1fr); gap: 5px; }
  .task-header, .audit-title { align-items: flex-start; flex-direction: column; gap: 6px; }
  .badges { justify-content: flex-start; }
  .task-card { padding: 11px; }
}
</style>
