<template>
  <el-tooltip :content="tooltip" :placement="placement" :show-after="250">
    <el-button
      class="theme-toggle-button"
      :class="{ 'is-fixed': fixed, 'has-text': hasLabel }"
      :icon="isDark ? Sunny : Moon"
      :circle="!hasLabel"
      :title="tooltip"
      :aria-label="tooltip"
      @click="toggleTheme"
    >
      <span v-if="hasLabel">{{ label || buttonText }}</span>
    </el-button>
  </el-tooltip>
</template>

<script setup lang="ts">
import { Moon, Sunny } from '@element-plus/icons-vue'
import { computed } from 'vue'

import { useTheme } from '@/composables/useTheme'

const props = withDefaults(defineProps<{ fixed?: boolean; placement?: 'top' | 'bottom' | 'left' | 'right'; text?: boolean; label?: string }>(), {
  placement: 'bottom',
})

const { isDark, toggleTheme } = useTheme()
const tooltip = computed(() => (isDark.value ? '切换到浅色主题' : '切换到暗色主题'))
const buttonText = computed(() => (isDark.value ? '浅色主题' : '暗色主题'))
const hasLabel = computed(() => props.text || Boolean(props.label))
</script>
