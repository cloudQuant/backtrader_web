/**
 * Shared Element Plus component stubs for view tests.
 * These stubs absorb common props and keep the rendered DOM stable.
 */
import { defineComponent, h } from 'vue'

const cardStub = defineComponent({
  name: 'ElCardStub',
  setup(_props, { slots }) {
    return () =>
      h('div', { class: 'el-card' }, [
        slots.header?.(),
        slots.default?.(),
      ])
  },
})

const formStub = defineComponent({
  name: 'ElFormStub',
  inheritAttrs: false,
  props: ['model', 'rules', 'labelWidth'],
  setup(_props, { slots, expose }) {
    expose({
      validate: async (callback?: (valid: boolean) => void) => {
        callback?.(true)
        return true
      },
    })

    return () => h('form', { class: 'el-form' }, slots.default?.())
  },
})

const formItemStub = defineComponent({
  name: 'ElFormItemStub',
  inheritAttrs: false,
  props: ['label', 'prop'],
  setup(_props, { slots }) {
    return () => h('div', { class: 'el-form-item' }, slots.default?.())
  },
})

const inputStub = defineComponent({
  name: 'ElInputStub',
  inheritAttrs: false,
  props: ['modelValue', 'type', 'placeholder', 'prefixIcon', 'size', 'showPassword', 'disabled'],
  emits: ['update:modelValue', 'input', 'change'],
  setup(props, { emit }) {
    return () =>
      h('input', {
        class: 'el-input',
        type: props.type || 'text',
        value: props.modelValue ?? '',
        placeholder: props.placeholder,
        disabled: props.disabled,
        onInput: (event: Event) => {
          const target = event.target as HTMLInputElement
          emit('update:modelValue', target.value)
          emit('input', target.value)
        },
        onChange: (event: Event) => {
          const target = event.target as HTMLInputElement
          emit('change', target.value)
        },
      })
  },
})

const inputNumberStub = defineComponent({
  name: 'ElInputNumberStub',
  inheritAttrs: false,
  props: ['modelValue', 'min', 'max', 'step', 'size', 'disabled'],
  emits: ['update:modelValue', 'change'],
  setup(props, { emit }) {
    return () =>
      h('div', { class: 'el-input-number' }, [
        h('input', {
          type: 'number',
          value: props.modelValue ?? '',
          disabled: props.disabled,
          onInput: (event: Event) => {
            const target = event.target as HTMLInputElement
            emit('update:modelValue', Number(target.value))
          },
          onChange: (event: Event) => {
            const target = event.target as HTMLInputElement
            emit('change', Number(target.value))
          },
        }),
      ])
  },
})

const buttonStub = defineComponent({
  name: 'ElButtonStub',
  inheritAttrs: false,
  props: ['type', 'size', 'loading', 'nativeType', 'circle'],
  emits: ['click'],
  setup(props, { slots, emit }) {
    return () =>
      h(
        'button',
        {
          class: 'el-button',
          disabled: props.loading,
          type: props.nativeType || 'button',
          onClick: () => emit('click'),
        },
        slots.default?.(),
      )
  },
})

const avatarStub = defineComponent({
  name: 'ElAvatarStub',
  inheritAttrs: false,
  props: ['size'],
  setup(_props, { slots }) {
    return () => h('div', { class: 'el-avatar' }, slots.default?.())
  },
})

const checkboxStub = defineComponent({
  name: 'ElCheckboxStub',
  inheritAttrs: false,
  props: ['modelValue', 'label', 'disabled'],
  emits: ['update:modelValue', 'change'],
  setup(props, { slots, emit }) {
    return () =>
      h('label', { class: 'el-checkbox' }, [
        h('input', {
          type: 'checkbox',
          checked: Boolean(props.modelValue),
          disabled: props.disabled,
          onChange: (event: Event) => {
            const target = event.target as HTMLInputElement
            emit('update:modelValue', target.checked)
            emit('change', target.checked)
          },
        }),
        slots.default?.(),
      ])
  },
})

const layoutStub = (tag: string, className: string) =>
  defineComponent({
    name: className,
    inheritAttrs: false,
    props: ['width'],
    setup(_props, { slots }) {
      return () => h(tag, { class: className }, slots.default?.())
    },
  })

export const elStubs: Record<string, any> = {
  'el-card': cardStub,
  'el-form': formStub,
  'el-form-item': formItemStub,
  'el-input': inputStub,
  'el-input-number': inputNumberStub,
  'el-select': { template: '<select class="el-select"><slot /></select>' },
  'el-option': { template: '<option />' },
  'el-button': buttonStub,
  'el-icon': { template: '<span class="el-icon"><slot /></span>' },
  'el-table': { template: '<div class="el-table"><slot /></div>' },
  'el-table-column': { template: '<div />' },
  'el-tag': { template: '<span class="el-tag"><slot /></span>' },
  'el-date-picker': inputStub,
  'el-divider': { template: '<hr class="el-divider" />' },
  'el-row': { template: '<div class="el-row"><slot /></div>' },
  'el-col': { template: '<div class="el-col"><slot /></div>' },
  'el-tabs': { template: '<div class="el-tabs"><slot /></div>' },
  'el-tab-pane': { template: '<div class="el-tab-pane"><slot /></div>' },
  'el-dialog': { template: '<div class="el-dialog"><slot /><slot name="footer" /></div>' },
  'el-progress': { template: '<div class="el-progress" />' },
  'el-descriptions': { template: '<div class="el-descriptions"><slot /></div>' },
  'el-descriptions-item': { template: '<div class="el-descriptions-item"><slot /></div>' },
  'el-empty': { template: '<div class="el-empty">Empty</div>' },
  'el-tooltip': { template: '<div class="el-tooltip"><slot /></div>' },
  'el-radio-group': { template: '<div class="el-radio-group"><slot /></div>' },
  'el-radio-button': { template: '<div class="el-radio-button"><slot /></div>' },
  'el-switch': { template: '<div class="el-switch" />' },
  'el-badge': { template: '<div class="el-badge"><slot /></div>' },
  'el-dropdown': { template: '<div class="el-dropdown"><slot /><slot name="dropdown" /></div>' },
  'el-dropdown-menu': { template: '<div class="el-dropdown-menu"><slot /></div>' },
  'el-dropdown-item': { template: '<div class="el-dropdown-item"><slot /></div>' },
  'el-alert': { template: '<div class="el-alert"><slot /></div>' },
  'el-pagination': { template: '<div class="el-pagination" />' },
  'el-collapse': { template: '<div class="el-collapse"><slot /></div>' },
  'el-collapse-item': { template: '<div class="el-collapse-item"><slot /></div>' },
  'el-popconfirm': { template: '<div class="el-popconfirm"><slot name="reference" /></div>' },
  'el-slider': { template: '<div class="el-slider" />' },
  'el-statistic': { template: '<div class="el-statistic" />' },
  'el-skeleton': { template: '<div class="el-skeleton"><slot /></div>' },
  'el-loading': { template: '<div class="el-loading"><slot /></div>' },
  'el-result': { template: '<div class="el-result"><slot /></div>' },
  'el-steps': { template: '<div class="el-steps"><slot /></div>' },
  'el-step': { template: '<div class="el-step" />' },
  'el-scrollbar': { template: '<div class="el-scrollbar"><slot /></div>' },
  'el-menu': { template: '<div class="el-menu"><slot /></div>' },
  'el-menu-item': { template: '<div class="el-menu-item"><slot /></div>' },
  'el-sub-menu': { template: '<div class="el-sub-menu"><slot /></div>' },
  'router-link': { template: '<a><slot /></a>' },
  'router-view': { template: '<div class="router-view" />' },
  'el-checkbox': checkboxStub,
  'el-checkbox-group': { template: '<div class="el-checkbox-group"><slot /></div>' },
  'el-avatar': avatarStub,
  'el-container': layoutStub('div', 'el-container'),
  'el-aside': layoutStub('aside', 'el-aside'),
  'el-header': layoutStub('header', 'el-header'),
  'el-main': layoutStub('main', 'el-main'),
  'el-button-group': { template: '<div class="el-button-group"><slot /></div>' },
}
