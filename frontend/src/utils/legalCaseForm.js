export function responsibleUserPatch({ isEdit, dirty, name }) {
  if (isEdit && !dirty) return {}
  return { responsible_user_name: name.trim() || null }
}
