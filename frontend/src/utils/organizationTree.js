export function buildOrganizationTree(rows = []) {
  const flatRows = []
  const flatten = items => items.forEach(item => {
    flatRows.push({ ...item, children: [] })
    flatten(item.children || [])
  })
  flatten(rows)
  const byId = new Map(flatRows.filter(row => row.id != null).map(row => [String(row.id), row]))
  const byCode = new Map(flatRows.filter(row => row.code).map(row => [row.code, row]))
  const roots = []
  for (const row of flatRows) {
    const parent = row.parent_id != null
      ? byId.get(String(row.parent_id))
      : (row.parent_code ? byCode.get(row.parent_code) : null)
    if (!parent || parent === row || createsCycle(row, parent, byId)) roots.push(row)
    else parent.children.push(row)
  }
  const sortNodes = nodes => nodes
    .sort((left, right) => ((left.sort_order || 0) - (right.sort_order || 0)) || left.code.localeCompare(right.code))
    .map(node => ({ ...node, children: sortNodes(node.children) }))
  return sortNodes(roots)
}

function createsCycle(row, parent, byId) {
  const rowId = row.id == null ? null : String(row.id)
  const visited = new Set()
  let cursor = parent
  while (cursor) {
    const cursorId = cursor.id == null ? null : String(cursor.id)
    if (cursorId === rowId || visited.has(cursorId)) return true
    visited.add(cursorId)
    cursor = cursor.parent_id == null ? null : byId.get(String(cursor.parent_id))
  }
  return false
}
