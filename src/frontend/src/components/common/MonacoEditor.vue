<template>
  <div ref="editorRef" class="monaco-editor-container" :style="{ height: height + 'px' }"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import * as monaco from 'monaco-editor'

interface Props {
  modelValue: string
  language?: string
  height?: number
  readOnly?: boolean
  theme?: string
}

const props = withDefaults(defineProps<Props>(), {
  language: 'python',
  height: 400,
  readOnly: false,
  theme: 'vs',
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
}>()

const editorRef = ref<HTMLDivElement>()
let editor: monaco.editor.IStandaloneCodeEditor | null = null

onMounted(() => {
  if (!editorRef.value) return

  editor = monaco.editor.create(editorRef.value, {
    value: props.modelValue,
    language: props.language,
    theme: props.theme,
    readOnly: props.readOnly,
    minimap: { enabled: false },
    fontSize: 14,
    lineNumbers: 'on',
    scrollBeyondLastLine: false,
    automaticLayout: true,
    tabSize: 4,
    wordWrap: 'on',
  })

  editor.onDidChangeModelContent(() => {
    const value = editor?.getValue() || ''
    emit('update:modelValue', value)
  })
})

watch(() => props.modelValue, (newVal) => {
  if (editor && editor.getValue() !== newVal) {
    editor.setValue(newVal)
  }
})

watch(() => props.theme, (newTheme) => {
  monaco.editor.setTheme(newTheme)
})

onUnmounted(() => {
  editor?.dispose()
})
</script>

<style scoped>
.monaco-editor-container {
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  overflow: hidden;
}
</style>
