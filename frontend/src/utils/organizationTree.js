export function buildOrganizationTree(rows = []) {
  const flatRows = []
  const flatten = items => items.forEach(item => {
    flatRows.push({ ...item, children: [] })
    flatten(item.children || [])
  })
  flatten(rows)
  const byCode = new Map(flatRows.map(row => [row.code, row]))
  const roots = []
  for (const row of flatRows) {
    const parent = row.parent_code ? byCode.get(row.parent_code) : null
    if (parent && parent !== row) parent.children.push(row)
    else roots.push(row)
  }
  const sortNodes = nodes => nodes
    .sort((left, right) => ((left.sort_order || 0) - (right.sort_order || 0)) || left.code.localeCompare(right.code))
    .map(node => ({ ...node, children: sortNodes(node.children) }))
  return sortNodes(roots)
}
