<template>
  <div class="space-y-6 max-w-3xl">
    <!-- 用户信息 -->
    <el-card>
      <template #header>
        <span class="font-bold">个人信息</span>
      </template>
      
      <el-form :model="userForm" label-width="100px">
        <el-form-item label="用户名">
          <el-input v-model="userForm.username" disabled />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="userForm.email" disabled />
        </el-form-item>
        <el-form-item label="注册时间">
          <el-input v-model="userForm.createdAt" disabled />
        </el-form-item>
      </el-form>
    </el-card>
    
    <!-- 修改密码 -->
    <el-card>
      <template #header>
        <span class="font-bold">修改密码</span>
      </template>
      
      <el-form :model="passwordForm" label-width="100px">
        <el-form-item label="当前密码">
          <el-input v-model="passwordForm.oldPassword" type="password" show-password />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="passwordForm.newPassword" type="password" show-password />
        </el-form-item>
        <el-form-item label="确认新密码">
          <el-input v-model="passwordForm.confirmPassword" type="password" show-password />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="changePassword">修改密码</el-button>
        </el-form-item>
      </el-form>
    </el-card>
    
    <!-- 关于 -->
    <el-card>
      <template #header>
        <span class="font-bold">关于</span>
      </template>
      
      <div class="space-y-2 text-gray-600">
        <p><strong>Backtrader Web</strong> v1.0.0</p>
        <p>基于 Backtrader 的量化交易回测平台</p>
        <p>技术栈: Vue 3 + FastAPI + Backtrader</p>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import api from '@/api/index'

const authStore = useAuthStore()
const changingPassword = ref(false)

const userForm = reactive({
  username: '',
  email: '',
  createdAt: '',
})

const passwordForm = reactive({
  oldPassword: '',
  newPassword: '',
  confirmPassword: '',
})

const user = computed(() => authStore.user)

async function changePassword() {
  if (!passwordForm.oldPassword || !passwordForm.newPassword) {
    ElMessage.warning('请填写密码')
    return
  }
  if (passwordForm.newPassword !== passwordForm.confirmPassword) {
    ElMessage.error('两次输入的新密码不一致')
    return
  }
  if (passwordForm.newPassword.length < 8) {
    ElMessage.error('密码至少8位')
    return
  }
  
  changingPassword.value = true
  try {
    await api.put('/auth/change-password', {
      old_password: passwordForm.oldPassword,
      new_password: passwordForm.newPassword,
    })
    ElMessage.success('密码修改成功')
    passwordForm.oldPassword = ''
    passwordForm.newPassword = ''
    passwordForm.confirmPassword = ''
  } catch {
    // error handled by interceptor
  } finally {
    changingPassword.value = false
  }
}

onMounted(() => {
  if (user.value) {
    userForm.username = user.value.username
    userForm.email = user.value.email
    userForm.createdAt = user.value.created_at
  }
})
</script>
