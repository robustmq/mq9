<template>
  <div v-if="frontmatter.layout === 'home'">
    <Home />
  </div>
  <DefaultTheme.Layout v-else />
</template>

<script setup>
import DefaultTheme from 'vitepress/theme'
import { useData } from 'vitepress'
import Home from './Home.vue'

const { frontmatter } = useData()
</script>
