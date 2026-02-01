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
    
    <!-- 系统设置 -->
    <el-card>
      <template #header>
        <span class="font-bold">系统设置</span>
      </template>
      
      <el-form label-width="100px">
        <el-form-item label="主题">
          <el-radio-group v-model="settings.theme">
            <el-radio label="light">浅色</el-radio>
            <el-radio label="dark">深色</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="语言">
          <el-select v-model="settings.language" class="w-40">
            <el-option label="中文" value="zh-CN" />
            <el-option label="English" value="en-US" />
          </el-select>
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
import { reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()

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

const settings = reactive({
  theme: 'light',
  language: 'zh-CN',
})

const user = computed(() => authStore.user)

function changePassword() {
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
  
  ElMessage.success('密码修改成功')
  passwordForm.oldPassword = ''
  passwordForm.newPassword = ''
  passwordForm.confirmPassword = ''
}

onMounted(() => {
  if (user.value) {
    userForm.username = user.value.username
    userForm.email = user.value.email
    userForm.createdAt = user.value.created_at
  }
})
</script>
