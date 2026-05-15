import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'mq9',
  titleTemplate: ':title — mq9',
  description: 'Deploy once. Every Agent gets a mailbox. Send to any Agent — online or offline.',
  base: '/',
  cleanUrls: true,
  appearance: 'force-light',

  head: [
    ['link', { rel: 'icon', type: 'image/svg+xml', href: '/favicon.svg' }],
    ['link', { rel: 'preconnect', href: 'https://fonts.googleapis.com' }],
    ['link', { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossorigin: '' }],
    ['link', { rel: 'stylesheet', href: 'https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@700&display=swap' }],
    ['meta', { name: 'author', content: 'mq9' }],
    ['meta', { name: 'keywords', content: 'mq9, AI agent messaging, agent communication, async messaging, NATS, agent mailbox, multi-agent system' }],
    ['meta', { name: 'robots', content: 'index, follow' }],
    ['meta', { property: 'og:type', content: 'website' }],
    ['meta', { property: 'og:site_name', content: 'mq9' }],
    ['meta', { property: 'og:title', content: 'mq9 — A message broker for AI Agents.' }],
    ['meta', { property: 'og:description', content: 'Deploy once. Every Agent gets a mailbox. Send to any Agent — online or offline.' }],
    ['meta', { property: 'og:url', content: 'https://mq9.robustmq.com' }],
    ['meta', { name: 'twitter:card', content: 'summary_large_image' }],
    ['link', { rel: 'canonical', href: 'https://mq9.robustmq.com' }],
    ['script', { charset: 'UTF-8', id: 'LA_COLLECT', src: '//sdk.51.la/js-sdk-pro.min.js' }],
    ['script', {}, `LA.init({id:"3PUlhxY3LHemHVJk",ck:"3PUlhxY3LHemHVJk",autoTrack:true,hashMode:true})`],
  ],

  locales: {
    root: {
      label: 'English',
      lang: 'en-US',
      themeConfig: {
        nav: [
          { text: 'Home', link: '/' },
          { text: 'Docs', link: '/docs/overview' },
          { text: 'GitHub', link: 'https://github.com/robustmq/robustmq' },
        ],
        sidebar: {
          '/sdk/': [
            {
              text: 'SDK',
              items: [
                { text: 'Python', link: '/sdk/python' },
                { text: 'JavaScript', link: '/sdk/javascript' },
                { text: 'Go', link: '/sdk/go' },
                { text: 'Rust', link: '/sdk/rust' },
                { text: 'Java', link: '/sdk/java' },
              ],
            },
          ],
          '/docs/': [
            {
              text: 'Getting Started',
              items: [
                { text: 'Overview', link: '/docs/overview' },
                { text: 'Quick Start', link: '/docs/quick-start' },
                { text: 'What is mq9', link: '/docs/what' },
                { text: 'For Engineers', link: '/docs/for-engineer' },
                { text: 'For Agents', link: '/docs/for-agent' },
              ],
            },
            {
              text: 'Deep Dives',
              items: [
                { text: 'Features', link: '/docs/features' },
                { text: 'Protocol', link: '/docs/protocol' },
                { text: 'Scenarios', link: '/docs/scenarios' },
              ],
            },
            {
              text: 'Integrations',
              items: [
                { text: 'SDK Reference', link: '/docs/sdk/' },
                { text: 'LangChain / LangGraph', link: '/docs/langchain' },
                { text: 'MCP Server', link: '/docs/mcp' },
              ],
            },
            {
              text: 'Reference',
              items: [
                { text: 'FAQ', link: '/docs/faq' },
                { text: 'Roadmap', link: '/docs/roadmap' },
              ],
            },
          ],
        },
      },
    },
    zh: {
      label: '中文',
      lang: 'zh-CN',
      link: '/zh/',
      themeConfig: {
        nav: [
          { text: '首页', link: '/zh/' },
          { text: '文档', link: '/zh/docs/' },
          { text: 'GitHub', link: 'https://github.com/robustmq/robustmq' },
        ],
        sidebar: {
          '/zh/sdk/': [
            {
              text: 'SDK',
              items: [
                { text: 'Python', link: '/zh/sdk/python' },
                { text: 'JavaScript', link: '/zh/sdk/javascript' },
                { text: 'Go', link: '/zh/sdk/go' },
                { text: 'Rust', link: '/zh/sdk/rust' },
                { text: 'Java', link: '/zh/sdk/java' },
              ],
            },
          ],
          '/zh/docs/': [
            {
              text: '快速入门',
              items: [
                { text: '概述', link: '/zh/docs/overview' },
                { text: '快速开始', link: '/zh/docs/quick-start' },
                { text: 'mq9 是什么', link: '/zh/docs/what' },
                { text: '给工程师', link: '/zh/docs/for-engineer' },
                { text: '给 Agent', link: '/zh/docs/for-agent' },
              ],
            },
            {
              text: '深入了解',
              items: [
                { text: '功能特性', link: '/zh/docs/features' },
                { text: '协议规范', link: '/zh/docs/protocol' },
                { text: '使用场景', link: '/zh/docs/scenarios' },
              ],
            },
            {
              text: '集成',
              items: [
                { text: 'SDK 参考', link: '/zh/docs/sdk/' },
                { text: 'LangChain / LangGraph', link: '/zh/docs/langchain' },
                { text: 'MCP Server', link: '/zh/docs/mcp' },
              ],
            },
            {
              text: '参考',
              items: [
                { text: '常见问题', link: '/zh/docs/faq' },
                { text: '路线图', link: '/zh/docs/roadmap' },
              ],
            },
          ],
        },
      },
    },
  },

  themeConfig: {
    siteTitle: false,
    logo: '/logo.jpg',
    aside: false,
    socialLinks: [
      { icon: 'github', link: 'https://github.com/robustmq/robustmq' },
    ],
  },

  sitemap: {
    hostname: 'https://mq9.robustmq.com',
  },
})
