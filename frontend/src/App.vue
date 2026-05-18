<template>
  <router-view />
</template>

<script setup lang="ts">
import { usePwaInstallPrompt } from '@/composables/usePwaInstall'
import { useTheme } from '@/composables/useTheme'

usePwaInstallPrompt()
useTheme()
</script>
