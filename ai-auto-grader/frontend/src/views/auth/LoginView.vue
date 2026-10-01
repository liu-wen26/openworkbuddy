<template>
  <div class="login-page">
    <el-card class="login-card">
      <h2 class="title">AI自动阅卷系统</h2>
      <el-form :model="form" label-width="80px" @keyup.enter="handleLogin">
        <el-form-item label="用户名">
          <el-input v-model="form.username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" placeholder="请输入密码" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleLogin" :loading="loading" style="width: 100%">
            登录
          </el-button>
        </el-form-item>
      </el-form>
      <div class="tips">
        <p>默认账号：</p>
        <p>admin / admin123（超级管理员）</p>
        <p>jiaowu / jiaowu123（教务管理员）</p>
        <p>jiaoyan / jiaoyan123（教研组长）</p>
        <p>teacher / teacher123（阅卷教师）</p>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const form = reactive({ username: '', password: '' })
const loading = ref(false)
const auth = useAuthStore()
const router = useRouter()

async function handleLogin() {
  if (!form.username || !form.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    await auth.login(form)
    ElMessage.success('登录成功')
    router.push('/')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: #f0f2f5;
}
.login-card {
  width: 420px;
}
.title {
  text-align: center;
  margin-bottom: 24px;
}
.tips {
  margin-top: 16px;
  color: #909399;
  font-size: 12px;
}
</style>
