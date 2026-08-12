import request from './request'

const reasonParams = reason => ({ params: { reason } })

export const getOrganizationTree = () => request.get('/organizations/tree')
export const createOrganization = (payload, reason) => request.post('/organizations', payload, reasonParams(reason))
export const updateOrganization = (id, payload, reason) => request.put(`/organizations/${id}`, payload, reasonParams(reason))
export const listPositions = () => request.get('/organizations/positions')
export const createPosition = (payload, reason) => request.post('/organizations/positions', payload, reasonParams(reason))
export const updatePosition = (id, payload, reason) => request.put(`/organizations/positions/${id}`, payload, reasonParams(reason))
export const listPermissions = () => request.get('/organizations/permissions')
export const replacePositionPermissions = (id, payload, reason) => request.put(`/organizations/positions/${id}/permissions`, payload, reasonParams(reason))
export const getUserAssignments = userId => request.get(`/organizations/users/${userId}/assignments`)
export const replaceUserAssignments = (userId, payload, reason) => request.put(`/organizations/users/${userId}/assignments`, payload, reasonParams(reason))
