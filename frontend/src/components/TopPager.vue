<template>
  <div class="top-pager">
    <el-button class="pager-icon-btn" text :disabled="page <= 1" @click="$emit('prev')" aria-label="上一页">
      <el-icon><ArrowLeft /></el-icon>
    </el-button>
    <span class="pager-text">第 {{ page }} / {{ totalPages }} 页</span>
    <el-button class="pager-icon-btn" text :disabled="page >= totalPages" @click="$emit('next')" aria-label="下一页">
      <el-icon><ArrowRight /></el-icon>
    </el-button>
  </div>
</template>

<script setup>
import { ArrowLeft, ArrowRight } from '@element-plus/icons-vue'

defineProps({
  page: {
    type: Number,
    required: true
  },
  totalPages: {
    type: Number,
    required: true
  }
})

defineEmits(['prev', 'next'])
</script>
