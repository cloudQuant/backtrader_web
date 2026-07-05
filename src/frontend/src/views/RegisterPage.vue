<template>
  <AuthFrame
    title-id="register-title"
    :eyebrow="t('auth.registerEyebrow')"
    :title="t('auth.registerTitle')"
    :subtitle="t('auth.registerSubtitle')"
  >
    <el-form
      ref="formRef"
      class="auth-form"
      :model="form"
      :rules="rules"
      :aria-label="t('auth.register')"
      @submit.prevent="handleRegister"
    >
      <el-form-item prop="username">
        <el-input
          v-model="form.username"
          data-testid="register-username"
          :placeholder="t('auth.username')"
          :aria-label="t('auth.username')"
          prefix-icon="User"
          size="large"
          autocomplete="username"
        />
      </el-form-item>

      <el-form-item prop="email">
        <el-input
          v-model="form.email"
          data-testid="register-email"
          :placeholder="t('auth.email')"
          :aria-label="t('auth.email')"
          prefix-icon="Message"
          size="large"
          autocomplete="email"
        />
      </el-form-item>

      <el-form-item prop="password">
        <el-input
          v-model="form.password"
          data-testid="register-password"
          type="password"
          :placeholder="t('auth.password')"
          :aria-label="t('auth.password')"
          prefix-icon="Lock"
          size="large"
          show-password
          autocomplete="new-password"
        />
      </el-form-item>

      <el-form-item prop="confirmPassword">
        <el-input
          v-model="form.confirmPassword"
          data-testid="register-confirm-password"
          type="password"
          :placeholder="t('auth.confirmPassword')"
          :aria-label="t('auth.confirmPassword')"
          prefix-icon="Lock"
          size="large"
          show-password
          autocomplete="new-password"
        />
      </el-form-item>

      <el-form-item>
        <el-button
          data-testid="register-submit"
          type="primary"
          size="large"
          class="auth-submit"
          :loading="loading"
          native-type="submit"
          :aria-label="t('auth.register')"
        >
          {{ t('auth.register') }}
        </el-button>
      </el-form-item>
    </el-form>

    <template #footer>
      {{ t('auth.hasAccount') }}
      <router-link
        to="/login"
        class="auth-link"
        :aria-label="t('auth.loginNow')"
      >
        {{ t('auth.loginNow') }}
      </router-link>
    </template>
  </AuthFrame>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import AuthFrame from '@/components/auth/AuthFrame.vue'

const { t } = useI18n()
const router = useRouter()
const authStore = useAuthStore()

const formRef = ref<FormInstance>()
const loading = ref(false)

const form = reactive({
  username: '',
  email: '',
  password: '',
  confirmPassword: '',
})

const validateConfirmPassword = (
  _rule: unknown,
  value: string,
  callback: (error?: string | Error) => void,
) => {
  if (value !== form.password) {
    callback(new Error(t('auth.passwordMismatch')))
  } else {
    callback()
  }
}

const rules: FormRules = {
  username: [
    { required: true, message: t('auth.usernameRequired'), trigger: 'blur' },
    { min: 3, max: 50, message: t('auth.usernameLength'), trigger: 'blur' },
  ],
  email: [
    { required: true, message: t('auth.emailRequired'), trigger: 'blur' },
    { type: 'email', message: t('auth.emailInvalid'), trigger: 'blur' },
  ],
  password: [
    { required: true, message: t('auth.passwordRequired'), trigger: 'blur' },
    { min: 8, message: t('auth.passwordMinLength'), trigger: 'blur' },
  ],
  confirmPassword: [
    { required: true, message: t('auth.confirmPasswordRequired'), trigger: 'blur' },
    { validator: validateConfirmPassword, trigger: 'blur' },
  ],
}

async function handleRegister() {
  if (!formRef.value) return

  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  try {
    await authStore.register({
      username: form.username,
      email: form.email,
      password: form.password,
    })
    ElMessage.success(t('auth.registerSuccessMsg'))
    router.push('/login')
  } catch {
    // 错误已在拦截器中处理
  } finally {
    loading.value = false
  }
}
</script>
