<script setup>
import { onMounted, watch } from 'vue'
import { useRoute } from 'vitepress'

const route = useRoute()

function loadGiscus() {
  const container = document.getElementById('giscus-container')
  if (!container) return

  container.innerHTML = ''

  const script = document.createElement('script')
  script.src = 'https://giscus.app/client.js'
  script.setAttribute('data-repo', 'robustmq/robustmq')
  script.setAttribute('data-repo-id', 'R_kgDOKC3GIQ')
  script.setAttribute('data-category', 'Announcements')
  script.setAttribute('data-category-id', 'DIC_kwDOKC3GIc4C51sI')
  script.setAttribute('data-mapping', 'pathname')
  script.setAttribute('data-strict', '0')
  script.setAttribute('data-reactions-enabled', '1')
  script.setAttribute('data-emit-metadata', '0')
  script.setAttribute('data-input-position', 'bottom')
  script.setAttribute('data-theme', 'light')
  script.setAttribute('data-lang', 'en')
  script.setAttribute('crossorigin', 'anonymous')
  script.async = true
  container.appendChild(script)
}

onMounted(() => loadGiscus())

watch(() => route.path, () => {
  setTimeout(loadGiscus, 300)
})
</script>

<template>
  <div style="margin-top: 48px; padding-top: 24px; border-top: 1px solid var(--vp-c-divider);">
    <div id="giscus-container" />
  </div>
</template>
