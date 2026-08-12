import request from './request'

export const getPortalApplications = () => request.get('/portal/applications')
export const getMyPortalPermissions = () => request.get('/portal/me/permissions')
