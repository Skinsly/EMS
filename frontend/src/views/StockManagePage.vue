<template>
  <component :is="activeMode === 'in' ? StockInPage : StockOutPage" />
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import StockInPage from './StockInPage.vue'
import StockOutPage from './StockOutPage.vue'

const route = useRoute()
const router = useRouter()

const activeMode = computed(() => (route.query.mode === 'out' ? 'out' : 'in'))

if (!route.query.mode) {
  router.replace({ path: '/stock-manage', query: { mode: 'in' } })
}
</script>
