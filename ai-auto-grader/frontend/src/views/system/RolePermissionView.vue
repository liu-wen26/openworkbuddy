<template>
  <div>
    <div class="toolbar">
      <h2>角色权限管理</h2>
      <el-button type="primary" :disabled="isSuper || saving" :loading="saving" @click="save">保存</el-button>
    </div>

    <el-alert
      title="超管拥有全部权限且不可修改；其他角色可在此勾选或取消权限（与内置默认的差异会被记录）。"
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 16px"
    />

    <el-card shadow="never" v-loading="loading">
      <el-radio-group v-model="activeRole" class="role-tabs" @change="onRoleChange">
        <el-radio-button v-for="r in roles" :key="r.role" :value="r.role">
          {{ roleLabel(r.role) }}
          <el-tag v-if="r.is_super" size="small" type="warning" style="margin-left: 6px">全权限</el-tag>
        </el-radio-button>
      </el-radio-group>

      <el-divider />

      <div v-if="isSuper" class="super-hint">
        <el-tag type="warning">超级管理员拥有系统全部权限，无需配置。</el-tag>
      </div>

      <div v-else class="perm-groups">
        <div v-for="group in catalog" :key="group.group" class="perm-group">
          <div class="group-head">
            <span class="group-title">{{ group.group }}</span>
            <el-button link type="primary" @click="toggleGroup(group, true)">全选</el-button>
            <el-button link type="primary" @click="toggleGroup(group, false)">清空</el-button>
          </div>
          <el-checkbox-group v-model="selected" class="group-items">
            <el-checkbox v-for="item in group.items" :key="item[0]" :value="item[0]">
              {{ item[1] }}
              <span class="perm-key">{{ item[0] }}</span>
            </el-checkbox>
          </el-checkbox-group>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getRoles, updateRolePermissions, type RoleInfo, type PermissionGroup } from '@/api/system'
import { ROLE_LABELS } from '@/api/users'

const roles = ref<RoleInfo[]>([])
const catalog = ref<PermissionGroup[]>([])
const activeRole = ref<string>('')
const selected = ref<string[]>([])
const loading = ref(false)
const saving = ref(false)

const isSuper = computed(() => roles.value.find((r) => r.role === activeRole.value)?.is_super ?? false)

function roleLabel(role: string) {
  return ROLE_LABELS[role] || role
}

async function load() {
  loading.value = true
  try {
    const res = await getRoles()
    roles.value = res.data.roles
    catalog.value = res.data.catalog
    if (!activeRole.value && roles.value.length) {
      activeRole.value = roles.value[0].role
    }
    onRoleChange()
  } finally {
    loading.value = false
  }
}

function onRoleChange() {
  const current = roles.value.find((r) => r.role === activeRole.value)
  selected.value = current ? [...current.permissions] : []
}

function toggleGroup(group: PermissionGroup, check: boolean) {
  const keys = group.items.map((i) => i[0])
  const set = new Set(selected.value)
  keys.forEach((k) => (check ? set.add(k) : set.delete(k)))
  selected.value = [...set]
}

async function save() {
  if (!activeRole.value) return
  saving.value = true
  try {
    const res = await updateRolePermissions(activeRole.value, selected.value)
    const current = roles.value.find((r) => r.role === activeRole.value)
    if (current) current.permissions = res.data.permissions
    ElMessage.success(`「${roleLabel(activeRole.value)}」权限已更新`)
  } finally {
    saving.value = false
  }
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
.role-tabs {
  flex-wrap: wrap;
}
.perm-groups {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 16px;
}
.perm-group {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 12px 16px;
}
.group-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.group-title {
  flex: 1;
  font-weight: 600;
  color: #303133;
}
.group-items {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.perm-key {
  margin-left: 6px;
  color: #c0c4cc;
  font-size: 12px;
}
.super-hint {
  padding: 24px 0;
}
</style>