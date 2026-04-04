<template>
  <div v-if="frontmatter.layout === 'home'">
    <Home />
  </div>
  <DefaultTheme.Layout v-else>
    <template #doc-after>
      <GiscusComment />
    </template>
  </DefaultTheme.Layout>
</template>

<script setup>
import DefaultTheme from 'vitepress/theme'
import { useData } from 'vitepress'
import Home from './Home.vue'
import GiscusComment from './GiscusComment.vue'

const { frontmatter } = useData()
</script>
