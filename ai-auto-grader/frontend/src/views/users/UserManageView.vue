<template>
  <div>
    <div class="toolbar">
      <h2>用户与角色</h2>
      <el-button type="primary" @click="openCreate">新建用户</el-button>
    </div>

    <el-table :data="users" v-loading="loading" border>
      <el-table-column prop="username" label="账号" width="160" />
      <el-table-column prop="real_name" label="姓名" width="140" />
      <el-table-column label="角色" width="150">
        <template #default="{ row }">
          <el-tag size="small">{{ ROLE_LABELS[row.role] || row.role }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="email" label="邮箱" min-width="180">
        <template #default="{ row }">{{ row.email || '-' }}</template>
      </el-table-column>
      <el-table-column prop="phone" label="手机号" width="140">
        <template #default="{ row }">{{ row.phone || '-' }}</template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag size="small" :type="row.is_active ? 'success' : 'info'">
            {{ row.is_active ? '启用' : '停用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link type="danger" :disabled="row.id === auth.user?.id" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑用户' : '新建用户'" width="480px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="账号" prop="username">
          <el-input v-model="form.username" :disabled="editing" placeholder="至少 3 个字符" />
        </el-form-item>
        <el-form-item label="姓名" prop="real_name">
          <el-input v-model="form.real_name" />
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="form.role" style="width: 100%">
            <el-option v-for="r in roleOptions" :key="r.role" :label="r.label" :value="r.role" />
          </el-select>
        </el-form-item>
        <el-form-item :label="editing ? '重置密码' : '密码'" prop="password">
          <el-input v-model="form.password" type="password" show-password
                    :placeholder="editing ? '留空则不修改' : '至少 6 个字符'" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="form.email" />
        </el-form-item>
        <el-form-item label="手机号">
          <el-input v-model="form.phone" />
        </el-form-item>
        <el-form-item v-if="editing" label="启用账号">
          <el-switch v-model="form.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSubmit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { listUsers, listRoleOptions, createUser, updateUser, deleteUser, ROLE_LABELS, type RoleOption } from '@/api/users'
import type { User } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const users = ref<User[]>([])
const roleOptions = ref<RoleOption[]>([])
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const editing = ref(false)
const editingId = ref('')
const formRef = ref<FormInstance>()

const form = reactive({
  username: '',
  real_name: '',
  role: 'teacher',
  password: '',
  email: '',
  phone: '',
  is_active: true,
})

const rules: FormRules = {
  username: [{ required: true, min: 3, message: '账号至少 3 个字符', trigger: 'blur' }],
  real_name: [{ required: true, message: '请填写姓名', trigger: 'blur' }],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }],
  password: [
    {
      validator: (_rule, value, callback) => {
        if (!editing.value && (!value || value.length < 6)) callback(new Error('密码至少 6 个字符'))
        else if (value && value.length < 6) callback(new Error('密码至少 6 个字符'))
        else callback()
      },
      trigger: 'blur',
    },
  ],
}

async function load() {
  loading.value = true
  try {
    const [u, r] = await Promise.all([listUsers(), listRoleOptions()])
    users.value = u.data
    roleOptions.value = r.data
  } finally {
    loading.value = false
  }
}

function resetForm() {
  form.username = ''
  form.real_name = ''
  form.role = 'teacher'
  form.password = ''
  form.email = ''
  form.phone = ''
  form.is_active = true
  formRef.value?.clearValidate()
}

function openCreate() {
  editing.value = false
  editingId.value = ''
  resetForm()
  dialogVisible.value = true
}

function openEdit(row: User) {
  editing.value = true
  editingId.value = row.id
  form.username = row.username
  form.real_name = row.real_name
  form.role = row.role
  form.password = ''
  form.email = row.email || ''
  form.phone = row.phone || ''
  form.is_active = row.is_active
  formRef.value?.clearValidate()
  dialogVisible.value = true
}

async function handleSubmit() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    saving.value = true
    try {
      if (editing.value) {
        const payload: Record<string, unknown> = {
          real_name: form.real_name,
          role: form.role,
          email: form.email || null,
          phone: form.phone || null,
          is_active: form.is_active,
        }
        if (form.password) payload.password = form.password
        await updateUser(editingId.value, payload)
        ElMessage.success('用户已更新')
      } else {
        await createUser({
          username: form.username,
          real_name: form.real_name,
          role: form.role,
          password: form.password,
          email: form.email || undefined,
          phone: form.phone || undefined,
        })
        ElMessage.success('用户已创建')
      }
      dialogVisible.value = false
      load()
    } finally {
      saving.value = false
    }
  })
}

async function handleDelete(row: User) {
  await ElMessageBox.confirm(`确定删除用户「${row.real_name}」吗？`, '警告', { type: 'warning' })
  await deleteUser(row.id)
  ElMessage.success('已删除')
  load()
}

onMounted(load)
</script>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
</style>