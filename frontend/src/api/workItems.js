import request from './request'

export const getWorkItems = () => request.get('/work-items')
export const getContractClosureSummary = (id) => request.get(`/contracts/${id}/closure-summary`)
