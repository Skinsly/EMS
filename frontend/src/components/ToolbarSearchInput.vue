<template>
  <el-input
    :model-value="modelValue"
    class="toolbar-search-input"
    :placeholder="placeholder"
    @update:model-value="$emit('update:modelValue', $event)"
    @input="$emit('input', $event)"
    @keydown.enter.prevent="$emit('enter')"
  />
</template>

<script setup>
defineProps({
  modelValue: {
    type: String,
    default: ''
  },
  placeholder: {
    type: String,
    default: ''
  }
})

defineEmits(['update:modelValue', 'input', 'enter'])
</script>
