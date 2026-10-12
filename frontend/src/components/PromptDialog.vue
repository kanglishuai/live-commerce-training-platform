<template>
  <div v-if="show" class="modal-mask" @click.self="$emit('cancel')">
    <div class="modal card">
      <h3 style="margin:0 0 10px">{{ title }}</h3>
      <textarea
        v-if="withInput"
        ref="area"
        v-model="text"
        class="textarea"
        rows="3"
        @keydown.ctrl.enter.prevent="confirm"
        @keydown.meta.enter.prevent="confirm"
      ></textarea>
      <div class="row" style="margin-top:10px;justify-content:flex-end">
        <button class="btn ghost sm" @click="$emit('cancel')">取消</button>
        <button class="btn sm" :disabled="withInput && !text.trim()" @click="confirm">确定</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'

// 应用内对话框：内置浏览器 / 沙箱 iframe / 嵌入式 WebView 对 window.prompt 直接抛错、
// window.confirm 会阻塞脚本执行，演示与评估环境不可控，故统一走应用内实现。
const props = withDefaults(
  defineProps<{
    show: boolean
    title: string
    defaultValue?: string
    /** false = 纯确认（无输入框），true = 输入对话框 */
    withInput?: boolean
  }>(),
  { withInput: true }
)
const emit = defineEmits<{
  (e: 'confirm', text: string): void
  (e: 'cancel'): void
}>()

const text = ref('')
const area = ref<HTMLTextAreaElement | null>(null)

watch(
  () => props.show,
  async (visible) => {
    if (!visible) return
    text.value = props.defaultValue || ''
    await nextTick()
    area.value?.focus()
  }
)

function confirm() {
  if (props.withInput) {
    const value = text.value.trim()
    if (!value) return
    emit('confirm', value)
  } else {
    emit('confirm', '')
  }
}
</script>

<style scoped>
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, .55);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.modal {
  width: min(520px, 92vw);
  margin: 0;
}
.native-tip {
  color: var(--text-dim);
  font-size: 12px;
}
</style>
