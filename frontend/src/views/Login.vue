<template>
  <div class="login-page">
    <ThemeToggle fixed label="主题" />

    <div class="login-shell">
      <section class="login-character-panel" :class="{ 'is-covering': isCovering, 'is-peeking': isPeeking }">
        <div class="login-brand">
          <div class="brand-mark">N</div>
          <div>
            <strong>Nebula</strong>
            <span>Sub Hub</span>
          </div>
        </div>

        <div class="character-stage" aria-hidden="true">
          <div class="characters-scene">
            <div ref="purpleRef" class="character-figure character-purple" :style="purpleStyle">
              <div class="character-face">
                <span class="character-eye"><span class="character-pupil"></span></span>
                <span class="character-eye"><span class="character-pupil"></span></span>
              </div>
            </div>

            <div ref="blackRef" class="character-figure character-black" :style="blackStyle">
              <div class="character-face">
                <span class="character-eye"><span class="character-pupil"></span></span>
                <span class="character-eye"><span class="character-pupil"></span></span>
              </div>
            </div>

            <div ref="orangeRef" class="character-figure character-orange" :style="orangeStyle">
              <div class="character-face character-face-dot">
                <span class="dot-eye"></span>
                <span class="dot-eye"></span>
              </div>
            </div>

            <div ref="yellowRef" class="character-figure character-yellow" :style="yellowStyle">
              <div class="character-face character-face-dot">
                <span class="dot-eye"></span>
                <span class="dot-eye"></span>
              </div>
              <span class="character-mouth"></span>
            </div>
          </div>
        </div>

        <div class="character-caption">
          <span class="caption-dot"></span>
          <span>{{ characterCaption }}</span>
        </div>
      </section>

      <section class="login-card">
        <div class="login-title">
          <span class="eyebrow">Nebula Sub Hub</span>
          <h1>欢迎回来</h1>
        </div>

        <el-form label-position="top" @submit.prevent="submit">
          <el-form-item label="用户名">
            <el-input
              v-model="form.username"
              :prefix-icon="User"
              autocomplete="username"
              placeholder="请输入用户名"
              @focus="setActiveField('username')"
              @blur="clearActiveField('username')"
            />
          </el-form-item>
          <el-form-item label="密码">
            <el-input
              v-model="form.password"
              :prefix-icon="Lock"
              :type="showPassword ? 'text' : 'password'"
              autocomplete="current-password"
              placeholder="请输入密码"
              @focus="setActiveField('password')"
              @blur="clearActiveField('password')"
            >
              <template #suffix>
                <button
                  class="password-visibility"
                  type="button"
                  :aria-label="showPassword ? '隐藏密码' : '显示密码'"
                  :title="showPassword ? '隐藏密码' : '显示密码'"
                  @mousedown.prevent
                  @click="showPassword = !showPassword"
                >
                  <el-icon>
                    <component :is="showPassword ? Hide : View" />
                  </el-icon>
                </button>
              </template>
            </el-input>
          </el-form-item>
          <el-button type="primary" native-type="submit" :loading="loading" class="login-submit">
            进入控制台
          </el-button>
        </el-form>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Hide, Lock, User, View } from '@element-plus/icons-vue'
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import ThemeToggle from '@/components/ThemeToggle.vue'
import { useAuthStore } from '@/stores/auth'

type CharacterKey = 'purple' | 'black' | 'orange' | 'yellow'
type CharacterStyle = Record<string, string | number>

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const loading = ref(false)
const form = reactive({ username: '', password: '' })
const activeField = ref<'username' | 'password' | null>(null)
const showPassword = ref(false)
const mouse = reactive({ x: 0, y: 0 })
const purpleRef = ref<HTMLElement | null>(null)
const blackRef = ref<HTMLElement | null>(null)
const orangeRef = ref<HTMLElement | null>(null)
const yellowRef = ref<HTMLElement | null>(null)

const hasPassword = computed(() => form.password.length > 0)
const isCovering = computed(() => activeField.value === 'password' && !showPassword.value)
const isPeeking = computed(() => activeField.value === 'password' && showPassword.value)
const characterCaption = computed(() => {
  if (isCovering.value) return '密码已隐藏'
  if (isPeeking.value) return '密码可见'
  if (activeField.value === 'username') return '正在识别账号'
  return '安全登录'
})
const purpleStyle = computed(() => characterStyle('purple'))
const blackStyle = computed(() => characterStyle('black'))
const orangeStyle = computed(() => characterStyle('orange'))
const yellowStyle = computed(() => characterStyle('yellow'))

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value))
}

function pointerPose(element: HTMLElement | null) {
  if (!element) return { faceX: 0, faceY: 0, skew: 0 }
  const rect = element.getBoundingClientRect()
  const centerX = rect.left + rect.width / 2
  const centerY = rect.top + rect.height / 3
  const deltaX = mouse.x - centerX
  const deltaY = mouse.y - centerY

  return {
    faceX: clamp(deltaX / 20, -15, 15),
    faceY: clamp(deltaY / 30, -10, 10),
    skew: clamp(-deltaX / 120, -6, 6),
  }
}

function baseCharacterStyle(params: {
  element: HTMLElement | null
  left: number
  width: number
  height: number
  radius: string
  color: string
  zIndex: number
  faceLeft: number
  faceTop: number
  gap: number
  eyeSize: number
  pupilSize?: number
  blinkDelay: string
  transformMultiplier?: number
}) {
  const pose = pointerPose(params.element)
  const skew = pose.skew * (params.transformMultiplier || 1)

  return {
    left: `${params.left}px`,
    width: `${params.width}px`,
    height: `${params.height}px`,
    backgroundColor: params.color,
    borderRadius: params.radius,
    zIndex: params.zIndex,
    transform: `skewX(${skew}deg)`,
    '--face-left': `${params.faceLeft + pose.faceX}px`,
    '--face-top': `${params.faceTop + pose.faceY}px`,
    '--face-gap': `${params.gap}px`,
    '--eye-size': `${params.eyeSize}px`,
    '--pupil-size': `${params.pupilSize || Math.max(5, Math.round(params.eyeSize * 0.42))}px`,
    '--look-x': '0px',
    '--look-y': '0px',
    '--mouth-left': `${params.faceLeft - 12 + pose.faceX}px`,
    '--mouth-top': `${params.faceTop + 48 + pose.faceY}px`,
    '--blink-delay': params.blinkDelay,
  } as CharacterStyle
}

function characterStyle(character: CharacterKey) {
  const styles: Record<CharacterKey, CharacterStyle> = {
    purple: baseCharacterStyle({
      element: purpleRef.value,
      left: 70,
      width: 180,
      height: 400,
      radius: '10px 10px 0 0',
      color: '#6C3FF5',
      zIndex: 1,
      faceLeft: 45,
      faceTop: 40,
      gap: 32,
      eyeSize: 18,
      pupilSize: 7,
      blinkDelay: '0s',
    }),
    black: baseCharacterStyle({
      element: blackRef.value,
      left: 240,
      width: 120,
      height: 310,
      radius: '8px 8px 0 0',
      color: '#2D2D2D',
      zIndex: 2,
      faceLeft: 26,
      faceTop: 32,
      gap: 24,
      eyeSize: 16,
      pupilSize: 6,
      blinkDelay: '1.4s',
      transformMultiplier: 1.5,
    }),
    orange: baseCharacterStyle({
      element: orangeRef.value,
      left: 0,
      width: 240,
      height: 200,
      radius: '120px 120px 0 0',
      color: '#FF9B6B',
      zIndex: 3,
      faceLeft: 82,
      faceTop: 90,
      gap: 32,
      eyeSize: 12,
      blinkDelay: '0.7s',
    }),
    yellow: baseCharacterStyle({
      element: yellowRef.value,
      left: 310,
      width: 140,
      height: 230,
      radius: '70px 70px 0 0',
      color: '#E8D754',
      zIndex: 4,
      faceLeft: 52,
      faceTop: 40,
      gap: 24,
      eyeSize: 12,
      blinkDelay: '2.1s',
    }),
  }

  const style = styles[character]

  if (activeField.value === 'username') {
    if (character === 'purple') {
      style.height = '440px'
      style.transform = 'skewX(-12deg) translateX(40px)'
      style['--face-left'] = '55px'
      style['--face-top'] = '65px'
      style['--look-x'] = '3px'
      style['--look-y'] = '4px'
    }
    if (character === 'black') {
      style.transform = 'skewX(10deg) translateX(20px)'
      style['--face-left'] = '32px'
      style['--face-top'] = '12px'
      style['--look-y'] = '-4px'
    }
  }

  if (hasPassword.value && !showPassword.value) {
    if (character === 'purple') {
      style.height = '440px'
      style.transform = 'skewX(-12deg) translateX(40px)'
      style['--face-left'] = '55px'
      style['--face-top'] = '65px'
      style['--look-x'] = '3px'
      style['--look-y'] = '4px'
    }
    if (character === 'black') {
      style.transform = 'skewX(-3deg)'
      style['--look-y'] = '-4px'
    }
  }

  if (hasPassword.value && showPassword.value) {
    style.transform = 'skewX(0deg)'
    style['--look-x'] = '-5px'
    style['--look-y'] = '-4px'

    if (character === 'purple') {
      style.height = '400px'
      style['--face-left'] = '20px'
      style['--face-top'] = '35px'
    }
    if (character === 'black') {
      style['--face-left'] = '10px'
      style['--face-top'] = '28px'
    }
    if (character === 'orange') {
      style['--face-left'] = '50px'
      style['--face-top'] = '85px'
    }
    if (character === 'yellow') {
      style['--face-left'] = '20px'
      style['--face-top'] = '35px'
      style['--mouth-left'] = '10px'
      style['--mouth-top'] = '88px'
    }
  }

  return style
}

function setActiveField(field: 'username' | 'password') {
  activeField.value = field
}

function clearActiveField(field: 'username' | 'password') {
  if (activeField.value === field) activeField.value = null
}

function handleMouseMove(event: MouseEvent) {
  mouse.x = event.clientX
  mouse.y = event.clientY
}

async function submit() {
  loading.value = true
  try {
    await auth.login(form.username, form.password)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/dashboard'
    router.push(redirect.startsWith('/') ? redirect : '/dashboard')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  mouse.x = window.innerWidth / 2
  mouse.y = window.innerHeight / 2
  window.addEventListener('mousemove', handleMouseMove)
})

onBeforeUnmount(() => {
  window.removeEventListener('mousemove', handleMouseMove)
})
</script>

<style scoped>
.login-page {
  position: relative;
  display: grid;
  min-height: 100vh;
  place-items: center;
  padding: 28px;
  overflow: auto;
  background: var(--bg);
}

.login-shell {
  display: grid;
  grid-template-columns: minmax(320px, 500px) minmax(320px, 430px);
  gap: 34px;
  align-items: stretch;
  width: min(1010px, 100%);
}

.login-page :deep(.theme-toggle-button.is-fixed.has-text) {
  width: auto;
  min-width: 64px;
  height: 34px;
  padding: 0 11px;
  gap: 4px;
  color: var(--text);
  font-size: 13px;
  font-weight: 650;
  white-space: nowrap;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 999px;
  box-shadow: var(--dashboard-shadow);
}

.login-page :deep(.theme-toggle-button.is-fixed.has-text .el-icon) {
  margin-right: 0;
}

.login-page :deep(.theme-toggle-button.is-fixed.has-text.el-button [class*='el-icon'] + span) {
  margin-left: 0;
}

.login-character-panel,
.login-card {
  min-height: 560px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
}

.login-character-panel {
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 30px;
  overflow: hidden;
  color: #f8fafc;
  background:
    linear-gradient(rgba(255, 255, 255, 0.045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.045) 1px, transparent 1px),
    linear-gradient(135deg, #34313c 0%, #24222b 44%, #17171d 100%);
  background-size: 20px 20px, 20px 20px, auto;
}

.login-character-panel::before {
  position: absolute;
  right: -90px;
  bottom: 70px;
  width: 270px;
  height: 270px;
  content: '';
  background: rgba(255, 255, 255, 0.08);
  border-radius: 999px;
  filter: blur(44px);
}

.login-character-panel::after {
  position: absolute;
  top: 130px;
  left: -70px;
  width: 210px;
  height: 210px;
  content: '';
  background: rgba(232, 215, 84, 0.18);
  border-radius: 999px;
  filter: blur(54px);
}

.login-brand,
.character-caption,
.character-stage {
  position: relative;
  z-index: 1;
}

.login-brand {
  display: inline-flex;
  align-items: center;
  gap: 12px;
}

.login-brand .brand-mark {
  width: 42px;
  height: 42px;
  color: #101014;
  background: #f8fafc;
}

.login-brand strong,
.login-brand span {
  display: block;
}

.login-brand span {
  margin-top: 2px;
  color: rgba(248, 250, 252, 0.64);
  font-size: 12px;
}

.character-stage {
  display: flex;
  min-height: 410px;
  align-items: flex-end;
  justify-content: center;
  overflow: hidden;
}

.characters-scene {
  position: relative;
  width: 550px;
  height: 400px;
  flex: 0 0 auto;
  transform: scale(0.84);
  transform-origin: bottom center;
}

.character-figure {
  position: absolute;
  bottom: 0;
  box-shadow: 0 28px 52px rgba(0, 0, 0, 0.18);
  transform-origin: bottom center;
  transition:
    height 0.7s ease-in-out,
    transform 0.7s ease-in-out;
}

.character-face {
  position: absolute;
  top: var(--face-top);
  left: var(--face-left);
  display: flex;
  gap: var(--face-gap);
  align-items: center;
  transition:
    top 0.7s ease-in-out,
    left 0.7s ease-in-out;
}

.character-eye {
  display: inline-flex;
  width: var(--eye-size);
  height: var(--eye-size);
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: #ffffff;
  border-radius: 999px;
  animation: login-blink 5.2s infinite;
  animation-delay: var(--blink-delay);
}

.character-pupil {
  width: var(--pupil-size);
  height: var(--pupil-size);
  background: #2d2d2d;
  border-radius: 999px;
  transform: translate(var(--look-x), var(--look-y));
  transition: transform 0.12s ease-out;
}

.dot-eye {
  width: var(--eye-size);
  height: var(--eye-size);
  background: #2d2d2d;
  border-radius: 999px;
  transform: translate(var(--look-x), var(--look-y));
  transition: transform 0.12s ease-out;
}

.character-mouth {
  position: absolute;
  top: var(--mouth-top);
  left: var(--mouth-left);
  width: 80px;
  height: 4px;
  background: #2d2d2d;
  border-radius: 999px;
  transition:
    top 0.2s ease-out,
    left 0.2s ease-out,
    transform 0.2s ease-out;
}

.login-character-panel.is-peeking .character-eye,
.login-character-panel.is-peeking .dot-eye {
  animation-duration: 2.8s;
}

.login-character-panel.is-covering .character-purple,
.login-character-panel.is-covering .character-black {
  box-shadow: 0 34px 70px rgba(0, 0, 0, 0.25);
}

.login-character-panel.is-covering .character-mouth {
  transform: translateY(2px) scaleX(0.85);
}

.character-caption {
  display: inline-flex;
  width: fit-content;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  padding: 0 12px;
  color: rgba(248, 250, 252, 0.76);
  font-size: 13px;
  font-weight: 650;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 999px;
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.16);
}

.caption-dot {
  width: 8px;
  height: 8px;
  background: #4ade80;
  border-radius: 999px;
  box-shadow: 0 0 0 3px rgba(74, 222, 128, 0.2);
}

.login-card {
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 34px;
  background: color-mix(in srgb, var(--panel) 96%, transparent);
}

.login-title {
  margin-bottom: 24px;
}

.login-title h1 {
  margin-top: 6px;
  font-size: 28px;
}

.login-card :deep(.el-form-item) {
  margin-bottom: 18px;
}

.login-card :deep(.el-input__wrapper) {
  min-height: 42px;
}

.password-visibility {
  display: inline-flex;
  width: 28px;
  height: 28px;
  align-items: center;
  justify-content: center;
  padding: 0;
  color: var(--muted);
  background: transparent;
  border: 0;
  border-radius: 999px;
  cursor: pointer;
}

.password-visibility:hover,
.password-visibility:focus {
  color: var(--accent);
  background: var(--button-hover);
  outline: none;
}

.login-submit {
  width: 100%;
  min-height: 42px;
  margin-top: 4px;
}

@keyframes login-blink {
  0%,
  4%,
  100% {
    transform: scaleY(1);
  }

  2% {
    transform: scaleY(0.12);
  }
}

@media (max-width: 980px) {
  .login-shell {
    grid-template-columns: minmax(300px, 1fr);
    gap: 18px;
  }

  .login-character-panel,
  .login-card {
    min-height: auto;
  }

  .login-character-panel {
    padding: 24px;
  }

  .character-stage {
    min-height: 280px;
  }

  .characters-scene {
    transform: scale(0.62);
  }
}

@media (max-width: 560px) {
  .login-page {
    padding: 16px;
  }

  .login-character-panel {
    display: none;
  }

  .login-card {
    padding: 24px;
  }

  .login-title h1 {
    font-size: 24px;
  }
}
</style>
