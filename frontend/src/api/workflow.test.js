import { beforeEach, describe, expect, it, vi } from 'vitest'

const request = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('./request', () => ({ default: request }))

import {
  approveWorkflowTask,
  getWorkflowTimeline,
  listMyWorkflowTasks,
  listWorkflowCandidates,
  reassignWorkflowTask,
  listAwaitingReassignmentTasks,
  listReassignmentAudits,
  rejectWorkflowTask
} from './workflow'

describe('workflow api', () => {
  beforeEach(() => vi.clearAllMocks())

  it('uses the workflow envelope routes and backend field names', () => {
    listWorkflowCandidates('supply.contract.v2', 'company_leader')
    listMyWorkflowTasks('contract')
    getWorkflowTimeline(41)
    approveWorkflowTask(51, '同意')
    rejectWorkflowTask(52, '补充资料')
    reassignWorkflowTask(53, 12, '任职调整')
    listAwaitingReassignmentTasks()
    listReassignmentAudits()

    expect(request.get).toHaveBeenNthCalledWith(1, '/workflows/candidates', { params: { workflow_code: 'supply.contract.v2', node_code: 'company_leader' } })
    expect(request.get).toHaveBeenCalledWith('/workflows/awaiting-reassignment')
    expect(request.get).toHaveBeenCalledWith('/workflows/reassignment-audits')
    expect(request.get).toHaveBeenNthCalledWith(2, '/workflows/my-tasks', { params: { target_type: 'contract' } })
    expect(request.get).toHaveBeenNthCalledWith(3, '/workflows/instances/41/timeline')
    expect(request.post).toHaveBeenNthCalledWith(1, '/workflows/tasks/51/approve', { comment: '同意' })
    expect(request.post).toHaveBeenNthCalledWith(2, '/workflows/tasks/52/reject', { reason: '补充资料' })
    expect(request.post).toHaveBeenNthCalledWith(3, '/workflows/tasks/53/reassign', { user_id: 12, reason: '任职调整' })
  })
})
