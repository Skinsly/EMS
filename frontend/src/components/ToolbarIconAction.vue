<template>
  <el-tooltip :content="tooltip" placement="bottom">
    <el-button :type="type || undefined" :disabled="disabled" :aria-label="ariaLabel" @click="$emit('click')">
      <el-icon><slot /></el-icon>
    </el-button>
  </el-tooltip>
</template>

<script setup>
defineProps({
  tooltip: {
    type: String,
    required: true
  },
  ariaLabel: {
    type: String,
    required: true
  },
  type: {
    type: String,
    default: ''
  },
  disabled: {
    type: Boolean,
    default: false
  }
})

defineEmits(['click'])
</script>
