<template>
  <section v-if="suggestions.length" class="suggestions" aria-label="建议问题">
    <p class="suggestions__label">可直接询问</p>
    <div class="suggestions__items">
      <button
        v-for="suggestion in suggestions"
        :key="suggestionText(suggestion)"
        class="suggestions__item"
        type="button"
        :aria-label="`询问：${suggestionText(suggestion)}`"
        @click="$emit('select', suggestionText(suggestion))"
      >
        {{ suggestionText(suggestion) }}
      </button>
    </div>
  </section>
</template>

<script setup>
defineProps({
  suggestions: { type: Array, default: () => [] }
})

defineEmits(['select'])

function suggestionText(suggestion) {
  return typeof suggestion === 'string' ? suggestion : suggestion?.content || suggestion?.title || ''
}
</script>

<style scoped>
.suggestions { padding: 20px; border: 1px solid var(--ai-rule); background: var(--surface-solid); }
.suggestions__label { margin: 0 0 10px; color: var(--el-text-color-secondary); font: 12px var(--font-data); }
.suggestions__items { display: flex; flex-wrap: wrap; gap: 8px; }
.suggestions__item { min-height: 32px; padding: 6px 10px; border: 1px solid var(--ai-rule-strong); border-radius: var(--radius-xs); background: transparent; color: var(--brand-lake); cursor: pointer; font: 13px var(--font-body); text-align: left; }
.suggestions__item:hover { border-color: var(--brand-lake); background: var(--surface-hover); }
.suggestions__item:focus-visible { outline: none; box-shadow: var(--focus-ring); }
</style>
