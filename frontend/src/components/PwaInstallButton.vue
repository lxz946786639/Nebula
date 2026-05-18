<template>
  <el-tooltip v-if="canInstall" content="安装应用" :placement="placement" :show-after="250">
    <el-button
      class="pwa-install-button"
      :icon="Download"
      circle
      title="安装应用"
      aria-label="安装应用"
      @click="install"
    />
  </el-tooltip>
</template>

<script setup lang="ts">
import { Download } from '@element-plus/icons-vue'

import { usePwaInstallPrompt } from '@/composables/usePwaInstall'

withDefaults(defineProps<{ placement?: 'top' | 'bottom' | 'left' | 'right' }>(), {
  placement: 'bottom',
})

const { canInstall, promptInstall } = usePwaInstallPrompt()

function install() {
  promptInstall().catch((error) => {
    console.warn('PWA install prompt failed', error)
  })
}
</script>
