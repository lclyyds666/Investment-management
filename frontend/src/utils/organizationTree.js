export function buildOrganizationTree(rows = []) {
  const flatRows = []
  const flatten = items => items.forEach(item => {
    flatRows.push({ ...item, children: [] })
    flatten(item.children || [])
  })
  flatten(rows)
  const byId = new Map(flatRows.filter(row => row.id != null).map(row => [String(row.id), row]))
  const byCode = new Map(flatRows.filter(row => row.code).map(row => [row.code, row]))
  const resolveParent = row => row.parent_id != null
    ? byId.get(String(row.parent_id))
    : (row.parent_code ? byCode.get(row.parent_code) : null)
  const roots = []
  for (const row of flatRows) {
    const parent = resolveParent(row)
    if (!parent || createsCycle(row, parent, resolveParent)) roots.push(row)
    else parent.children.push(row)
  }
  const sortNodes = nodes => nodes
    .sort((left, right) => ((left.sort_order || 0) - (right.sort_order || 0)) || left.code.localeCompare(right.code))
    .map(node => ({ ...node, children: sortNodes(node.children) }))
  return sortNodes(roots)
}

function createsCycle(row, parent, resolveParent) {
  const visited = new Set()
  let cursor = parent
  while (cursor) {
    if (cursor === row || visited.has(cursor)) return true
    visited.add(cursor)
    cursor = resolveParent(cursor)
  }
  return false
}
