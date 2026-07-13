import {
  computed,
  defineComponent,
  getCurrentInstance,
  h,
  inject,
  onBeforeUnmount,
  provide,
  reactive,
  ref,
  watch,
  type App,
  type Component,
  type InjectionKey,
  type PropType,
} from 'vue'
import { LoaderCircle } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardContent,
  CardHeader,
} from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Progress } from '@/components/ui/progress'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'

type LooseRecord = Record<string, unknown>

function valueProp(defaultValue: unknown = undefined) {
  return { type: null as unknown as PropType<unknown>, default: defaultValue }
}

const UiButton = defineComponent({
  name: 'UiButton',
  inheritAttrs: false,
  props: {
    type: { type: String, default: 'default' },
    size: { type: String, default: 'default' },
    loading: Boolean,
    disabled: Boolean,
    text: Boolean,
    link: Boolean,
    plain: Boolean,
    circle: Boolean,
    icon: Object as PropType<Component>,
    nativeType: { type: String, default: 'button' },
  },
  emits: ['click'],
  setup(props, { attrs, slots, emit }) {
    return () => h(Button, {
      ...attrs,
      type: props.nativeType,
      disabled: props.disabled || props.loading,
      variant: props.type === 'danger'
        ? 'destructive'
        : props.text || props.link || props.plain
          ? 'ghost'
          : props.type === 'primary' || props.type === 'success'
            ? 'default'
            : 'secondary',
      size: props.circle ? 'icon' : props.size === 'small' ? 'sm' : props.size === 'large' ? 'lg' : 'default',
      class: cn(props.circle && 'rounded-full', attrs.class as string),
      onClick: (event: MouseEvent) => emit('click', event),
    }, {
      default: () => [
        props.loading ? h(LoaderCircle, { class: 'size-4 animate-spin' }) : props.icon ? h(props.icon, { class: 'size-4' }) : null,
        slots.default?.(),
      ],
    })
  },
})

const UiIcon = defineComponent({
  name: 'UiIcon',
  setup(_, { slots, attrs }) {
    return () => h('span', { ...attrs, class: cn('inline-flex size-4 shrink-0 items-center justify-center [&>svg]:size-full', attrs.class as string) }, slots.default?.())
  },
})

const UiCard = defineComponent({
  name: 'UiCard',
  props: { shadow: String },
  setup(_, { slots, attrs }) {
    return () => h(Card, { ...attrs, class: cn('gap-0 overflow-hidden py-0', attrs.class as string) }, {
      default: () => [
        slots.header ? h(CardHeader, { class: 'border-b py-4' }, slots.header()) : null,
        h(CardContent, { class: 'p-4 md:p-5' }, slots.default?.()),
      ],
    })
  },
})

const UiDialog = defineComponent({
  name: 'UiDialog',
  props: {
    modelValue: Boolean,
    title: String,
    width: [String, Number],
    closeOnClickModal: { type: Boolean, default: true },
  },
  emits: ['update:modelValue', 'close', 'closed', 'open'],
  setup(props, { slots, emit, attrs }) {
    const onOpenChange = (open: boolean) => {
      emit('update:modelValue', open)
      emit(open ? 'open' : 'close')
      if (!open) emit('closed')
    }
    return () => h(Dialog, { open: props.modelValue, 'onUpdate:open': onOpenChange }, {
      default: () => h(DialogContent, {
        class: cn('max-h-[90vh] overflow-y-auto sm:max-w-xl', attrs.class as string),
        style: props.width ? { width: typeof props.width === 'number' ? `${props.width}px` : props.width, maxWidth: 'calc(100vw - 2rem)' } : undefined,
        onInteractOutside: props.closeOnClickModal ? undefined : (event: Event) => event.preventDefault(),
      }, {
        default: () => [
          props.title || slots.header ? h(DialogHeader, null, {
            default: () => props.title ? h(DialogTitle, null, () => props.title) : slots.header?.(),
          }) : null,
          h(DialogDescription, { class: 'sr-only' }, () => props.title || '对话框'),
          h('div', { class: 'min-w-0 py-1' }, slots.default?.()),
          slots.footer ? h(DialogFooter, null, slots.footer()) : null,
        ],
      }),
    })
  },
})

const UiInput = defineComponent({
  name: 'UiInput',
  inheritAttrs: false,
  props: {
    modelValue: valueProp(''),
    type: { type: String, default: 'text' },
    rows: { type: Number, default: 3 },
    disabled: Boolean,
    placeholder: String,
    readonly: Boolean,
    clearable: Boolean,
    autocomplete: String,
  },
  emits: ['update:modelValue', 'input', 'change', 'blur', 'focus', 'keyup'],
  setup(props, { attrs, emit, slots, expose }) {
    const inputRef = ref<HTMLInputElement | HTMLTextAreaElement>()
    expose({ focus: () => inputRef.value?.focus(), blur: () => inputRef.value?.blur() })
    return () => {
      const tag = props.type === 'textarea' ? 'textarea' : 'input'
      const control = h(tag, {
        ...attrs,
        ref: inputRef,
        value: props.modelValue as string | number,
        type: tag === 'input' ? props.type : undefined,
        rows: tag === 'textarea' ? props.rows : undefined,
        disabled: props.disabled,
        readonly: props.readonly,
        placeholder: props.placeholder,
        autocomplete: props.autocomplete,
        class: cn(
          'flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs outline-none transition-colors placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/40 disabled:cursor-not-allowed disabled:opacity-50',
          tag === 'textarea' ? 'min-h-20 resize-y' : 'h-9',
          attrs.class as string,
        ),
        onInput: (event: Event) => {
          const value = (event.target as HTMLInputElement).value
          emit('update:modelValue', value)
          emit('input', value)
        },
        onChange: (event: Event) => emit('change', (event.target as HTMLInputElement).value),
        onBlur: (event: FocusEvent) => emit('blur', event),
        onFocus: (event: FocusEvent) => emit('focus', event),
        onKeyup: (event: KeyboardEvent) => emit('keyup', event),
      })
      if (!slots.prefix && !slots.suffix && !slots.prepend && !slots.append) return control
      return h('div', { class: 'flex w-full items-stretch [&>input]:rounded-none [&>input]:first:rounded-l-md [&>input]:last:rounded-r-md' }, [
        slots.prepend ? h('span', { class: 'flex items-center rounded-l-md border border-r-0 bg-muted px-3 text-sm text-muted-foreground' }, slots.prepend()) : null,
        slots.prefix ? h('span', { class: 'flex items-center border-y border-l px-2 text-muted-foreground' }, slots.prefix()) : null,
        control,
        slots.suffix ? h('span', { class: 'flex items-center border-y border-r px-2 text-muted-foreground' }, slots.suffix()) : null,
        slots.append ? h('span', { class: 'flex items-center rounded-r-md border border-l-0 bg-muted px-3 text-sm text-muted-foreground' }, slots.append()) : null,
      ])
    }
  },
})

const UiInputNumber = defineComponent({
  name: 'UiInputNumber',
  props: {
    modelValue: Number,
    min: Number,
    max: Number,
    step: { type: Number, default: 1 },
    disabled: Boolean,
  },
  emits: ['update:modelValue', 'change'],
  setup(props, { emit, attrs }) {
    return () => h('input', {
      ...attrs,
      type: 'number',
      value: props.modelValue,
      min: props.min,
      max: props.max,
      step: props.step,
      disabled: props.disabled,
      class: cn('h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/40', attrs.class as string),
      onInput: (event: Event) => emit('update:modelValue', Number((event.target as HTMLInputElement).value)),
      onChange: (event: Event) => emit('change', Number((event.target as HTMLInputElement).value)),
    })
  },
})

const UiOption = defineComponent({
  name: 'UiOption',
  props: { label: [String, Number], value: valueProp(), disabled: Boolean },
  setup(props, { slots }) {
    return () => h('option', { value: props.value as string | number, disabled: props.disabled }, slots.default?.() || String(props.label ?? props.value ?? ''))
  },
})

const UiOptionGroup = defineComponent({
  name: 'UiOptionGroup',
  props: { label: String },
  setup(props, { slots }) { return () => h('optgroup', { label: props.label }, slots.default?.()) },
})

const UiSelect = defineComponent({
  name: 'UiSelect',
  inheritAttrs: false,
  props: { modelValue: valueProp(''), disabled: Boolean, placeholder: String, multiple: Boolean },
  emits: ['update:modelValue', 'change'],
  setup(props, { slots, emit, attrs }) {
    return () => h('select', {
      ...attrs,
      value: props.modelValue as string | number,
      disabled: props.disabled,
      multiple: props.multiple,
      class: cn('h-9 w-full rounded-md border border-input bg-background px-3 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/40 disabled:opacity-50', attrs.class as string),
      onChange: (event: Event) => {
        const target = event.target as HTMLSelectElement
        const value = props.multiple ? [...target.selectedOptions].map(option => option.value) : target.value
        emit('update:modelValue', value)
        emit('change', value)
      },
    }, [
      props.placeholder ? h('option', { value: '', disabled: true }, props.placeholder) : null,
      slots.default?.(),
    ])
  },
})

interface FormContext { model: LooseRecord; rules: LooseRecord }
const formKey: InjectionKey<FormContext> = Symbol('ui-form')

const UiForm = defineComponent({
  name: 'UiForm',
  props: {
    model: { type: Object as PropType<LooseRecord>, default: () => ({}) },
    rules: { type: Object as PropType<LooseRecord>, default: () => ({}) },
    labelWidth: [String, Number],
    inline: Boolean,
  },
  setup(props, { slots, attrs, expose }) {
    provide(formKey, reactive({ model: props.model, rules: props.rules }))
    const validate = async (callback?: (valid: boolean) => void) => {
      let valid = true
      for (const [field, rawRules] of Object.entries(props.rules || {})) {
        const value = props.model?.[field]
        for (const rule of (Array.isArray(rawRules) ? rawRules : [rawRules]) as Array<Record<string, unknown>>) {
          if (rule.required && (value === '' || value === undefined || value === null || (Array.isArray(value) && !value.length))) valid = false
          if (typeof value === 'string' && typeof rule.min === 'number' && value.length < rule.min) valid = false
          if (typeof value === 'string' && typeof rule.max === 'number' && value.length > rule.max) valid = false
          if (typeof rule.validator === 'function') {
            await new Promise<void>((resolve) => {
              ;(rule.validator as Function)(rule, value, (error?: Error) => { if (error) valid = false; resolve() })
            })
          }
        }
      }
      callback?.(valid)
      return valid
    }
    expose({ validate, validateField: validate, clearValidate: () => undefined, resetFields: () => undefined })
    return () => h('form', { ...attrs, class: cn(props.inline && 'flex flex-wrap items-start gap-3', attrs.class as string), onSubmit: (event: Event) => event.preventDefault() }, slots.default?.())
  },
})

const UiFormItem = defineComponent({
  name: 'UiFormItem',
  props: { label: String, prop: String, required: Boolean, error: String, labelWidth: [String, Number] },
  setup(props, { slots, attrs }) {
    return () => h('div', { ...attrs, class: cn('grid gap-2', attrs.class as string) }, [
      props.label || slots.label ? h('label', { class: 'text-sm font-medium leading-none' }, [props.required ? h('span', { class: 'mr-1 text-destructive' }, '*') : null, slots.label?.() || props.label]) : null,
      h('div', { class: 'min-w-0' }, slots.default?.()),
      props.error ? h('p', { class: 'text-sm text-destructive' }, props.error) : null,
    ])
  },
})

const UiSwitch = defineComponent({
  name: 'UiSwitch',
  props: { modelValue: Boolean, disabled: Boolean, activeText: String, inactiveText: String },
  emits: ['update:modelValue', 'change'],
  setup(props, { emit, attrs }) {
    return () => h('label', { class: 'inline-flex items-center gap-2 text-sm' }, [
      props.inactiveText ? h('span', { class: 'text-muted-foreground' }, props.inactiveText) : null,
      h(Switch, { ...attrs, modelValue: props.modelValue, disabled: props.disabled, 'onUpdate:modelValue': (value: boolean) => { emit('update:modelValue', value); emit('change', value) } }),
      props.activeText ? h('span', null, props.activeText) : null,
    ])
  },
})

const radioKey: InjectionKey<{ value: { value: unknown }; update: (value: unknown) => void }> = Symbol('ui-radio')
const UiRadioGroup = defineComponent({
  name: 'UiRadioGroup',
  props: { modelValue: valueProp(), disabled: Boolean },
  emits: ['update:modelValue', 'change'],
  setup(props, { slots, emit, attrs }) {
    const state = computed(() => props.modelValue)
    provide(radioKey, { value: state as unknown as { value: unknown }, update: (value) => { emit('update:modelValue', value); emit('change', value) } })
    return () => h('div', { ...attrs, class: cn('flex flex-wrap items-center gap-2', attrs.class as string) }, slots.default?.())
  },
})

function makeRadio(name: string, button = false) {
  return defineComponent({
    name,
    props: { label: valueProp(), value: valueProp(), disabled: Boolean },
    setup(props, { slots, attrs }) {
      const group = inject(radioKey)
      const optionValue = computed(() => props.value ?? props.label)
      return () => h('label', { ...attrs, class: cn(button ? 'cursor-pointer rounded-md border px-3 py-1.5 text-sm has-[:checked]:border-primary has-[:checked]:bg-primary has-[:checked]:text-primary-foreground' : 'inline-flex cursor-pointer items-center gap-2 text-sm', attrs.class as string) }, [
        h('input', { type: 'radio', class: button ? 'sr-only' : 'size-4 accent-primary', checked: group?.value.value === optionValue.value, disabled: props.disabled, onChange: () => group?.update(optionValue.value) }),
        slots.default?.() || String(props.label ?? props.value ?? ''),
      ])
    },
  })
}

const UiRadio = makeRadio('UiRadio')
const UiRadioButton = makeRadio('UiRadioButton', true)

const UiCheckbox = defineComponent({
  name: 'UiCheckbox',
  props: { modelValue: valueProp(false), label: valueProp(), disabled: Boolean },
  emits: ['update:modelValue', 'change'],
  setup(props, { slots, emit, attrs }) {
    return () => h('label', { ...attrs, class: cn('inline-flex cursor-pointer items-center gap-2 text-sm', attrs.class as string) }, [
      h('input', { type: 'checkbox', class: 'size-4 accent-primary', checked: Boolean(props.modelValue), disabled: props.disabled, onChange: (event: Event) => { const value = (event.target as HTMLInputElement).checked; emit('update:modelValue', value); emit('change', value) } }),
      slots.default?.() || (props.label != null ? String(props.label) : null),
    ])
  },
})

interface RegisteredColumn { id: number; props: LooseRecord; slots: Record<string, Function> }
const tableKey: InjectionKey<{ register: (column: RegisteredColumn) => void; remove: (id: number) => void }> = Symbol('ui-table')

const UiTableColumn = defineComponent({
  name: 'UiTableColumn',
  props: { prop: String, label: String, width: [String, Number], minWidth: [String, Number], align: String, fixed: [String, Boolean], type: String },
  setup(props, { slots }) {
    const table = inject(tableKey)
    const id = getCurrentInstance()?.uid || Math.random()
    table?.register({ id, props: props as unknown as LooseRecord, slots })
    watch(props, () => table?.register({ id, props: props as unknown as LooseRecord, slots }), { deep: true })
    onBeforeUnmount(() => table?.remove(id))
    return () => null
  },
})

const UiTable = defineComponent({
  name: 'UiTable',
  props: { data: { type: Array as PropType<LooseRecord[]>, default: () => [] }, emptyText: { type: String, default: '暂无数据' }, rowKey: [String, Function], height: [String, Number], maxHeight: [String, Number] },
  emits: ['row-click', 'row-dblclick', 'selection-change'],
  setup(props, { slots, emit, attrs }) {
    const columns = reactive<RegisteredColumn[]>([])
    provide(tableKey, {
      register(column) { const index = columns.findIndex(item => item.id === column.id); if (index >= 0) columns[index] = column; else columns.push(column) },
      remove(id) { const index = columns.findIndex(item => item.id === id); if (index >= 0) columns.splice(index, 1) },
    })
    const cellValue = (row: LooseRecord, column: RegisteredColumn, index: number) => {
      if (column.slots.default) return column.slots.default({ row, $index: index, column: column.props })
      return column.props.prop ? row[String(column.props.prop)] as never : ''
    }
    return () => h('div', { ...attrs, class: cn('relative w-full overflow-auto rounded-md border', attrs.class as string), style: { maxHeight: props.maxHeight || props.height } }, [
      h('table', { class: 'w-full caption-bottom text-sm' }, [
        h('thead', { class: 'border-b bg-muted/40' }, [h('tr', null, columns.map(column => h('th', { class: 'h-10 px-3 text-left align-middle font-medium text-muted-foreground', style: { width: column.props.width ? `${column.props.width}px` : undefined, minWidth: column.props.minWidth ? `${column.props.minWidth}px` : undefined, textAlign: column.props.align as string } }, column.slots.header?.({ column: column.props }) || String(column.props.label || ''))))]),
        h('tbody', { class: 'divide-y' }, props.data.length ? props.data.map((row, index) => h('tr', { class: 'transition-colors hover:bg-muted/35', onClick: () => emit('row-click', row), onDblclick: () => emit('row-dblclick', row) }, columns.map(column => h('td', { class: 'p-3 align-middle', style: { textAlign: column.props.align as string } }, cellValue(row, column, index))))) : [h('tr', null, [h('td', { colspan: Math.max(columns.length, 1), class: 'h-28 text-center text-muted-foreground' }, props.emptyText)])]),
      ]),
      h('div', { class: 'hidden' }, slots.default?.()),
    ])
  },
})

interface RegisteredItem { id: number; props: LooseRecord; slots: Record<string, Function> }
function registry(key: InjectionKey<{ register: (item: RegisteredItem) => void; remove: (id: number) => void }>) {
  const items = reactive<RegisteredItem[]>([])
  provide(key, { register(item) { const index = items.findIndex(value => value.id === item.id); if (index >= 0) items[index] = item; else items.push(item) }, remove(id) { const index = items.findIndex(value => value.id === id); if (index >= 0) items.splice(index, 1) } })
  return items
}

const descriptionsKey: InjectionKey<{ register: (item: RegisteredItem) => void; remove: (id: number) => void }> = Symbol('ui-descriptions')
const UiDescriptionsItem = defineComponent({
  name: 'UiDescriptionsItem', props: { label: String, span: Number },
  setup(props, { slots }) { const owner = inject(descriptionsKey); const id = getCurrentInstance()?.uid || Math.random(); owner?.register({ id, props: props as unknown as LooseRecord, slots }); onBeforeUnmount(() => owner?.remove(id)); return () => null },
})
const UiDescriptions = defineComponent({
  name: 'UiDescriptions', props: { title: String, column: { type: Number, default: 3 }, border: Boolean, direction: String, size: String },
  setup(props, { slots, attrs }) { const items = registry(descriptionsKey); return () => h('div', { ...attrs, class: cn('space-y-3', attrs.class as string) }, [props.title ? h('h3', { class: 'font-medium' }, props.title) : null, h('dl', { class: 'grid overflow-hidden rounded-md border', style: { gridTemplateColumns: `repeat(${Math.max(1, props.column)}, minmax(0, 1fr))` } }, items.flatMap(item => [h('dt', { class: 'bg-muted/40 px-3 py-2 text-sm text-muted-foreground' }, String(item.props.label || '')), h('dd', { class: 'px-3 py-2 text-sm' }, item.slots.default?.())])), h('div', { class: 'hidden' }, slots.default?.())]) },
})

const tabsKey: InjectionKey<{ register: (item: RegisteredItem) => void; remove: (id: number) => void }> = Symbol('ui-tabs')
const UiTabPane = defineComponent({
  name: 'UiTabPane', props: { label: String, name: valueProp() },
  setup(props, { slots }) { const owner = inject(tabsKey); const id = getCurrentInstance()?.uid || Math.random(); owner?.register({ id, props: props as unknown as LooseRecord, slots }); onBeforeUnmount(() => owner?.remove(id)); return () => null },
})
const UiTabs = defineComponent({
  name: 'UiTabs', props: { modelValue: valueProp(), type: String }, emits: ['update:modelValue', 'tab-change'],
  setup(props, { slots, emit, attrs }) { const items = registry(tabsKey); const select = (value: unknown) => { emit('update:modelValue', value); emit('tab-change', value) }; return () => h('div', { ...attrs, class: cn('w-full', attrs.class as string) }, [h('div', { class: 'inline-flex h-9 items-center rounded-lg bg-muted p-1 text-muted-foreground' }, items.map(item => h('button', { type: 'button', class: cn('rounded-md px-3 py-1 text-sm font-medium', props.modelValue === item.props.name && 'bg-background text-foreground shadow-sm'), onClick: () => select(item.props.name) }, String(item.props.label || item.props.name || '')))), h('div', { class: 'mt-4' }, items.find(item => item.props.name === props.modelValue)?.slots.default?.()), h('div', { class: 'hidden' }, slots.default?.())]) },
})

const stepsKey: InjectionKey<{ register: (item: RegisteredItem) => void; remove: (id: number) => void }> = Symbol('ui-steps')
const UiStep = defineComponent({ name: 'UiStep', props: { title: String, description: String, icon: Object }, setup(props, { slots }) { const owner = inject(stepsKey); const id = getCurrentInstance()?.uid || Math.random(); owner?.register({ id, props: props as unknown as LooseRecord, slots }); onBeforeUnmount(() => owner?.remove(id)); return () => null } })
const UiSteps = defineComponent({ name: 'UiSteps', props: { active: { type: Number, default: 0 }, finishStatus: String, alignCenter: Boolean, direction: String }, setup(props, { slots, attrs }) { const items = registry(stepsKey); return () => h('div', { ...attrs, class: cn('flex gap-3', props.direction === 'vertical' ? 'flex-col' : 'overflow-x-auto', attrs.class as string) }, [items.map((item, index) => h('div', { class: cn('flex min-w-32 flex-1 items-center gap-2 rounded-md border p-3', index < props.active && 'border-primary/50', index === props.active && 'bg-primary/10') }, [h('span', { class: cn('grid size-7 place-items-center rounded-full bg-muted text-xs font-semibold', index <= props.active && 'bg-primary text-primary-foreground') }, String(index + 1)), h('div', null, [h('div', { class: 'text-sm font-medium' }, String(item.props.title || '')), item.props.description ? h('div', { class: 'text-xs text-muted-foreground' }, String(item.props.description)) : null])])), h('div', { class: 'hidden' }, slots.default?.())]) } })

const UiTag = defineComponent({ name: 'UiTag', props: { type: String, effect: String, size: String, closable: Boolean }, emits: ['close'], setup(props, { slots, emit, attrs }) { return () => h(Badge, { ...attrs, variant: props.type === 'danger' ? 'destructive' : props.type === 'success' ? 'default' : 'secondary', class: cn(props.type === 'warning' && 'bg-amber-500/15 text-amber-400', props.type === 'info' && 'bg-blue-500/15 text-blue-400', attrs.class as string) }, { default: () => [slots.default?.(), props.closable ? h('button', { class: 'ml-1', onClick: () => emit('close') }, '×') : null] }) } })
const UiAlert = defineComponent({ name: 'UiAlert', props: { title: String, description: String, type: String, closable: Boolean, showIcon: Boolean }, setup(props, { slots, attrs }) { return () => h('div', { ...attrs, role: 'alert', class: cn('rounded-lg border p-3 text-sm', props.type === 'error' && 'border-red-500/40 bg-red-500/10 text-red-200', props.type === 'warning' && 'border-amber-500/40 bg-amber-500/10 text-amber-100', props.type === 'success' && 'border-emerald-500/40 bg-emerald-500/10 text-emerald-100', props.type === 'info' && 'border-blue-500/40 bg-blue-500/10 text-blue-100', attrs.class as string) }, [props.title ? h('div', { class: 'font-medium' }, props.title) : null, h('div', { class: props.title ? 'mt-1 text-current/80' : '' }, slots.default?.() || props.description)]) } })
const UiText = defineComponent({ name: 'UiText', props: { type: String, size: String, truncated: Boolean, tag: { type: String, default: 'span' } }, setup(props, { slots, attrs }) { return () => h(props.tag, { ...attrs, class: cn(props.type === 'danger' && 'text-destructive', props.type === 'success' && 'text-emerald-400', props.type === 'warning' && 'text-amber-400', props.type === 'info' && 'text-blue-400', props.truncated && 'truncate', attrs.class as string) }, slots.default?.()) } })
const UiLink = defineComponent({ name: 'UiLink', props: { href: String, target: String, type: String, underline: { type: Boolean, default: true }, disabled: Boolean }, setup(props, { slots, attrs }) { return () => h('a', { ...attrs, href: props.disabled ? undefined : props.href, target: props.target, class: cn('text-primary underline-offset-4 hover:underline', props.disabled && 'pointer-events-none opacity-50', attrs.class as string) }, slots.default?.()) } })
const UiEmpty = defineComponent({ name: 'UiEmpty', props: { description: { type: String, default: '暂无数据' }, imageSize: Number }, setup(props, { slots, attrs }) { return () => h('div', { ...attrs, class: cn('grid min-h-32 place-items-center p-6 text-center text-sm text-muted-foreground', attrs.class as string) }, [slots.image?.(), h('p', null, props.description), slots.default?.()]) } })
const UiDivider = defineComponent({ name: 'UiDivider', props: { direction: String, contentPosition: String }, setup(_, { slots, attrs }) { return () => h('div', { ...attrs, class: cn('my-4 flex items-center gap-3 text-xs text-muted-foreground before:h-px before:flex-1 before:bg-border after:h-px after:flex-1 after:bg-border', attrs.class as string) }, slots.default?.()) } })
const UiProgress = defineComponent({ name: 'UiProgress', props: { percentage: { type: Number, default: 0 }, status: String, strokeWidth: Number, textInside: Boolean, showText: { type: Boolean, default: true }, color: String }, setup(props, { attrs }) { return () => h('div', { ...attrs, class: cn('flex items-center gap-3', attrs.class as string) }, [h(Progress, { modelValue: props.percentage, class: 'flex-1' }), props.showText ? h('span', { class: 'w-12 text-right text-xs text-muted-foreground' }, `${Math.round(props.percentage)}%`) : null]) } })
const UiTooltip = defineComponent({ name: 'UiTooltip', props: { content: String, placement: String, disabled: Boolean }, setup(props, { slots, attrs }) { return () => h('span', { ...attrs, title: props.disabled ? undefined : props.content, class: cn('inline-flex', attrs.class as string) }, slots.default?.()) } })
const UiScrollbar = defineComponent({ name: 'UiScrollbar', props: { height: [String, Number], maxHeight: [String, Number], always: Boolean }, setup(props, { slots, attrs }) { return () => h('div', { ...attrs, class: cn('overflow-auto', attrs.class as string), style: { height: props.height, maxHeight: props.maxHeight } }, slots.default?.()) } })
const UiRow = defineComponent({ name: 'UiRow', props: { gutter: { type: Number, default: 0 }, justify: String, align: String }, setup(props, { slots, attrs }) { return () => h('div', { ...attrs, class: cn('grid grid-cols-12', attrs.class as string), style: { gap: `${props.gutter}px` } }, slots.default?.()) } })
const UiCol = defineComponent({ name: 'UiCol', props: { span: { type: Number, default: 24 }, xs: [Number, Object], sm: [Number, Object], md: [Number, Object], lg: [Number, Object], xl: [Number, Object] }, setup(props, { slots, attrs }) { const width = Math.max(1, Math.round((props.span / 24) * 12)); return () => h('div', { ...attrs, class: cn('min-w-0', attrs.class as string), style: { gridColumn: `span ${width} / span ${width}` } }, slots.default?.()) } })
const UiCollapse = defineComponent({ name: 'UiCollapse', setup(_, { slots, attrs }) { return () => h('div', { ...attrs, class: cn('divide-y rounded-md border', attrs.class as string) }, slots.default?.()) } })
const UiCollapseItem = defineComponent({ name: 'UiCollapseItem', props: { title: String, name: valueProp() }, setup(props, { slots, attrs }) { return () => h('details', { ...attrs, class: attrs.class }, [h('summary', { class: 'cursor-pointer px-4 py-3 text-sm font-medium' }, slots.title?.() || props.title), h('div', { class: 'border-t p-4' }, slots.default?.())]) } })

const UiDatePicker = defineComponent({
  name: 'UiDatePicker',
  props: { modelValue: valueProp(), type: String, startPlaceholder: String, endPlaceholder: String, placeholder: String, disabled: Boolean },
  emits: ['update:modelValue', 'change'],
  setup(props, { emit, attrs }) {
    const updateRange = (index: number, value: string) => { const current = Array.isArray(props.modelValue) ? [...props.modelValue] : ['', '']; current[index] = value; emit('update:modelValue', current); emit('change', current) }
    return () => props.type?.includes('range') ? h('div', { class: 'grid grid-cols-2 gap-2' }, [0, 1].map(index => h('input', { type: props.type.includes('datetime') ? 'datetime-local' : 'date', value: Array.isArray(props.modelValue) ? props.modelValue[index] : '', placeholder: index ? props.endPlaceholder : props.startPlaceholder, class: 'h-9 rounded-md border border-input bg-background px-3 text-sm', onInput: (event: Event) => updateRange(index, (event.target as HTMLInputElement).value) }))) : h('input', { ...attrs, type: props.type?.includes('datetime') ? 'datetime-local' : 'date', value: props.modelValue as string, disabled: props.disabled, class: cn('h-9 rounded-md border border-input bg-background px-3 text-sm', attrs.class as string), onInput: (event: Event) => { const value = (event.target as HTMLInputElement).value; emit('update:modelValue', value); emit('change', value) } })
  },
})

const UiUpload = defineComponent({
  name: 'UiUpload',
  props: { action: String, autoUpload: Boolean, showFileList: Boolean, accept: String, multiple: Boolean, drag: Boolean, limit: Number, disabled: Boolean, onChange: Function, onRemove: Function, beforeUpload: Function, httpRequest: Function },
  emits: ['change', 'remove', 'exceed'],
  setup(props, { slots, emit, attrs, expose }) {
    const input = ref<HTMLInputElement>()
    const files = ref<File[]>([])
    const change = (event: Event) => { const selected = [...((event.target as HTMLInputElement).files || [])]; if (props.limit && files.value.length + selected.length > props.limit) { emit('exceed', selected); return } files.value = props.multiple ? [...files.value, ...selected] : selected.slice(0, 1); for (const raw of selected) { const file = { name: raw.name, size: raw.size, raw }; props.onChange?.(file, files.value); emit('change', file, files.value) } }
    expose({ clearFiles: () => { files.value = []; if (input.value) input.value.value = '' }, submit: () => files.value.forEach(raw => props.httpRequest?.({ file: raw })) })
    return () => h('div', { ...attrs, class: cn('space-y-2', attrs.class as string) }, [h('input', { ref: input, type: 'file', class: 'sr-only', accept: props.accept, multiple: props.multiple, disabled: props.disabled, onChange: change }), h('div', { class: cn(props.drag && 'grid min-h-32 cursor-pointer place-items-center rounded-lg border border-dashed p-6 text-center hover:border-primary/60'), onClick: () => input.value?.click() }, slots.trigger?.() || slots.default?.() || h(Button, { type: 'button', variant: 'secondary' }, () => '选择文件')), slots.tip ? h('div', { class: 'text-xs text-muted-foreground' }, slots.tip()) : null])
  },
})

const dropdownKey: InjectionKey<(command: unknown) => void> = Symbol('ui-dropdown')
const UiDropdown = defineComponent({ name: 'UiDropdown', props: { trigger: String }, emits: ['command'], setup(_, { slots, emit, attrs }) { const open = ref(false); provide(dropdownKey, (command) => { emit('command', command); open.value = false }); return () => h('div', { ...attrs, class: cn('relative inline-flex', attrs.class as string) }, [h('div', { onClick: () => { open.value = !open.value } }, slots.default?.()), open.value ? h('div', { class: 'absolute right-0 top-full z-50 mt-2 min-w-40 rounded-md border bg-popover p-1 text-popover-foreground shadow-md' }, slots.dropdown?.()) : null]) } })
const UiDropdownMenu = defineComponent({ name: 'UiDropdownMenu', setup(_, { slots }) { return () => h('div', null, slots.default?.()) } })
const UiDropdownItem = defineComponent({ name: 'UiDropdownItem', props: { command: valueProp(), divided: Boolean, disabled: Boolean }, setup(props, { slots, attrs }) { const command = inject(dropdownKey); return () => h('button', { ...attrs, type: 'button', disabled: props.disabled, class: cn('flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm hover:bg-accent', props.divided && 'mt-1 border-t pt-2', attrs.class as string), onClick: () => command?.(props.command) }, slots.default?.()) } })

const UiPagination = defineComponent({ name: 'UiPagination', props: { currentPage: { type: Number, default: 1 }, pageSize: { type: Number, default: 10 }, total: { type: Number, default: 0 }, pageSizes: Array as PropType<number[]>, layout: String }, emits: ['update:currentPage', 'update:pageSize', 'current-change', 'size-change'], setup(props, { emit, attrs }) { const pages = computed(() => Math.max(1, Math.ceil(props.total / props.pageSize))); const setPage = (page: number) => { const value = Math.min(pages.value, Math.max(1, page)); emit('update:currentPage', value); emit('current-change', value) }; return () => h('div', { ...attrs, class: cn('flex flex-wrap items-center justify-end gap-2 text-sm', attrs.class as string) }, [props.pageSizes ? h('select', { class: 'h-8 rounded-md border bg-background px-2', value: props.pageSize, onChange: (event: Event) => { const value = Number((event.target as HTMLSelectElement).value); emit('update:pageSize', value); emit('size-change', value) } }, props.pageSizes.map(size => h('option', { value: size }, `${size} 条/页`))) : null, h('span', { class: 'text-muted-foreground' }, `共 ${props.total} 条`), h(Button, { size: 'sm', variant: 'outline', disabled: props.currentPage <= 1, onClick: () => setPage(props.currentPage - 1) }, () => '上一页'), h('span', null, `${props.currentPage} / ${pages.value}`), h(Button, { size: 'sm', variant: 'outline', disabled: props.currentPage >= pages.value, onClick: () => setPage(props.currentPage + 1) }, () => '下一页')]) } })

const UiTree = defineComponent({ name: 'UiTree', props: { data: { type: Array as PropType<LooseRecord[]>, default: () => [] }, props: { type: Object as PropType<{ label?: string; children?: string }>, default: () => ({ label: 'label', children: 'children' }) }, nodeKey: String, defaultExpandAll: Boolean, highlightCurrent: Boolean, expandOnClickNode: Boolean }, emits: ['node-click'], setup(props, { slots, emit, attrs }) { const renderNode = (node: LooseRecord, level = 0): ReturnType<typeof h> => { const childrenKey = props.props.children || 'children'; const labelKey = props.props.label || 'label'; const children = (node[childrenKey] as LooseRecord[]) || []; return h('li', null, [h('button', { type: 'button', class: 'flex w-full items-center rounded px-2 py-1.5 text-left text-sm hover:bg-accent', style: { paddingLeft: `${level * 14 + 8}px` }, onClick: () => emit('node-click', node) }, slots.default?.({ node: { label: node[labelKey], data: node }, data: node }) || String(node[labelKey] || '')), children.length ? h('ul', null, children.map(child => renderNode(child, level + 1))) : null]) }; return () => h('ul', { ...attrs, class: cn('py-1', attrs.class as string) }, props.data.map(node => renderNode(node))) } })

const simpleContainers: Record<string, Component> = {
  UiContainer: defineComponent({ setup(_, { slots, attrs }) { return () => h('div', attrs, slots.default?.()) } }),
  UiAside: defineComponent({ setup(_, { slots, attrs }) { return () => h('aside', attrs, slots.default?.()) } }),
  UiHeader: defineComponent({ setup(_, { slots, attrs }) { return () => h('header', attrs, slots.default?.()) } }),
  UiMain: defineComponent({ setup(_, { slots, attrs }) { return () => h('main', attrs, slots.default?.()) } }),
  UiFooter: defineComponent({ setup(_, { slots, attrs }) { return () => h('footer', attrs, slots.default?.()) } }),
  UiMenu: defineComponent({ setup(_, { slots, attrs }) { return () => h('nav', attrs, slots.default?.()) } }),
  UiMenuItem: defineComponent({ props: { index: String }, setup(_, { slots, attrs }) { return () => h('div', attrs, slots.default?.()) } }),
}

const components: Record<string, Component> = {
  UiButton, UiIcon, UiCard, UiDialog, UiInput, UiInputNumber, UiSelect, UiOption, UiOptionGroup,
  UiForm, UiFormItem, UiSwitch, UiRadioGroup, UiRadio, UiRadioButton, UiCheckbox,
  UiTable, UiTableColumn, UiDescriptions, UiDescriptionsItem, UiTabs, UiTabPane,
  UiSteps, UiStep, UiTag, UiAlert, UiText, UiLink, UiEmpty, UiDivider, UiProgress,
  UiTooltip, UiScrollbar, UiRow, UiCol, UiCollapse, UiCollapseItem, UiDatePicker,
  UiUpload, UiDropdown, UiDropdownMenu, UiDropdownItem, UiPagination, UiTree,
  ...simpleContainers,
}

export function installAppCompat(app: App) {
  Object.entries(components).forEach(([name, component]) => app.component(name, component))
}
