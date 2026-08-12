import request from './request'

export function listWorkflowCandidates(workflowCode, nodeCode) {
  if (typeof workflowCode === 'object') {
    return request.get('/workflows/candidates', { params: { task_id: workflowCode.taskId } })
  }
  return request.get('/workflows/candidates', {
    params: { workflow_code: workflowCode, node_code: nodeCode }
  })
}

export function listAwaitingReassignmentTasks() {
  return request.get('/workflows/awaiting-reassignment')
}

export function listReassignmentAudits(params = {}) {
  return request.get('/workflows/reassignment-audits', { params })
}

export function listMyWorkflowTasks(targetType) {
  return request.get('/workflows/my-tasks', {
    params: targetType ? { target_type: targetType } : undefined
  })
}

export function getWorkflowTimeline(instanceId) {
  return request.get(`/workflows/instances/${instanceId}/timeline`)
}

export function approveWorkflowTask(taskId, comment = '') {
  return request.post(`/workflows/tasks/${taskId}/approve`, { comment })
}

export function rejectWorkflowTask(taskId, reason) {
  return request.post(`/workflows/tasks/${taskId}/reject`, { reason })
}

export function reassignWorkflowTask(taskId, userId, reason) {
  return request.post(`/workflows/tasks/${taskId}/reassign`, { user_id: userId, reason })
}
