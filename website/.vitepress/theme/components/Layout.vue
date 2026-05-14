<template>
  <DefaultTheme.Layout>
    <template #doc-after v-if="frontmatter.layout !== 'home'">
      <GiscusComment />
    </template>
  </DefaultTheme.Layout>
</template>

<script setup>
import DefaultTheme from 'vitepress/theme'
import { useData } from 'vitepress'
import GiscusComment from './GiscusComment.vue'

const { frontmatter } = useData()
</script>
