import type { Directive } from 'vue'

function update(element: HTMLElement, loading: boolean) {
  element.classList.toggle('app-loading', loading)
  element.setAttribute('aria-busy', String(loading))
}

export const loadingDirective: Directive<HTMLElement, boolean> = {
  mounted: (element, binding) => update(element, Boolean(binding.value)),
  updated: (element, binding) => update(element, Boolean(binding.value)),
}
