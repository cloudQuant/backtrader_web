<template>
  <div class="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-500 to-purple-600">
    <el-card class="login-card shadow-2xl">
      <template #header>
        <div class="text-center">
          <h1 class="text-2xl font-bold text-gray-800">
            Backtrader Web
          </h1>
          <p class="text-gray-500 mt-2">
            {{ t('common.subtitle') }}
          </p>
        </div>
      </template>
      
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        @submit.prevent="handleLogin"
      >
        <el-form-item prop="username">
          <el-input
            ref="usernameInputRef"
            v-model="form.username"
            :placeholder="t('auth.username')"
            prefix-icon="User"
            size="large"
          />
        </el-form-item>
        
        <el-form-item prop="password">
          <el-input
            v-model="form.password"
            type="password"
            :placeholder="t('auth.password')"
            prefix-icon="Lock"
            size="large"
            show-password
          />
        </el-form-item>
        
        <el-form-item>
          <el-button
            type="primary"
            size="large"
            class="w-full"
            :loading="loading"
            native-type="submit"
          >
            {{ t('auth.login') }}
          </el-button>
        </el-form-item>
      </el-form>
      
      <div class="text-center text-gray-500">
        {{ t('auth.noAccount') }}
        <router-link
          to="/register"
          class="text-blue-500 hover:underline"
        >
          {{ t('auth.registerNow') }}
        </router-link>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const formRef = ref<FormInstance>()
const loading = ref(false)
const usernameInputRef = ref<InstanceType<typeof import('element-plus')['ElInput']> | null>(null)

const form = reactive({
  username: '',
  password: '',
})

const rules: FormRules = {
  username: [
    { required: true, message: t('auth.usernameRequired'), trigger: 'blur' },
  ],
  password: [
    { required: true, message: t('auth.passwordRequired'), trigger: 'blur' },
  ],
}

async function handleLogin() {
  if (!formRef.value) return

  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  try {
    await authStore.login(form)
    ElMessage.success(t('auth.loginSuccess'))
    
    // BUG-11: 验证重定向路径安全性，防止 XSS
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : ''
    const safeRedirect = redirect && redirect.startsWith('/') && !redirect.startsWith('//') ? redirect : '/'
    router.push(safeRedirect)
  } catch (error) {
    // 错误已在拦截器中处理
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  // Auto-focus username input on page load
  usernameInputRef.value?.focus()
})
</script>

<style scoped lang="scss">
@use '@/styles/responsive' as *;

.login-card {
  width: 384px;
  
  @include respond-to('sm') {
    width: 100%;
    max-width: 90%;
    margin: 12px;
  }
}
</style>
