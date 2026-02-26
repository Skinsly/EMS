<template>
  <div class="stock-page-head">
    <div class="stock-head-actions">
      <slot name="actions" />
    </div>

    <div :class="['stock-page-title', titleClass]">
      <slot name="title">
        {{ title }}
      </slot>
    </div>

    <slot name="pager">
      <TopPager :page="page" :total-pages="totalPages" @prev="$emit('prev')" @next="$emit('next')" />
    </slot>
  </div>
</template>

<script setup>
import TopPager from './TopPager.vue'

defineProps({
  title: {
    type: String,
    default: ''
  },
  titleClass: {
    type: [String, Array, Object],
    default: ''
  },
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
