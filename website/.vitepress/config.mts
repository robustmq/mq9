import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'mq9',
  titleTemplate: ':title — mq9',
  description: 'Agent registration, discovery, and reliable async messaging in one broker — designed to scale to millions of agents.',
  base: '/',
  cleanUrls: true,
  appearance: 'force-light',

  head: [
    ['link', { rel: 'icon', type: 'image/svg+xml', href: '/favicon.svg' }],
    ['link', { rel: 'preconnect', href: 'https://fonts.googleapis.com' }],
    ['link', { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossorigin: '' }],
    ['link', { rel: 'stylesheet', href: 'https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@700&display=swap' }],
    ['meta', { name: 'author', content: 'mq9' }],
    ['meta', { name: 'keywords', content: 'mq9, agent registry, agent discovery, AI agent messaging, async messaging, NATS, agent mailbox, multi-agent system, A2A, AgentCard, reliable messaging' }],
    ['meta', { name: 'robots', content: 'index, follow' }],
    ['meta', { property: 'og:type', content: 'website' }],
    ['meta', { property: 'og:site_name', content: 'mq9' }],
    ['meta', { property: 'og:title', content: 'mq9 — Agent Registry + Reliable Async Messaging' }],
    ['meta', { property: 'og:description', content: 'Agent registration, discovery, and reliable async messaging in one broker — designed to scale to millions of agents.' }],
    ['meta', { property: 'og:url', content: 'https://mq9.robustmq.com' }],
    ['meta', { name: 'twitter:card', content: 'summary_large_image' }],
    ['meta', { name: 'twitter:title', content: 'mq9 — Agent Registry + Reliable Async Messaging' }],
    ['meta', { name: 'twitter:description', content: 'Agent registration, discovery, and reliable async messaging in one broker — designed to scale to millions of agents.' }],
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
          { text: 'Docs', link: '/docs/what' },
          { text: 'Blogs', link: 'https://robustmq.com/en/Blogs/' },
          { text: 'GitHub', link: 'https://github.com/robustmq/mq9' },
          { text: 'RobustMQ', link: 'https://github.com/robustmq/robustmq' },
        ],
        sidebar: {
          '/docs/': [
            {
              text: 'Getting Started',
              items: [
                { text: 'What is mq9', link: '/docs/what' },
                { text: 'For Engineers', link: '/docs/for-engineer' },
                { text: 'For Agents', link: '/docs/for-agent' },
                { text: 'Quick Start', link: '/docs/quick-start' },
              ],
            },
            {
              text: 'Deep Dives',
              items: [
                { text: 'Architecture', link: '/docs/architecture' },
                { text: 'Features', link: '/docs/features' },
                { text: 'Protocol', link: '/docs/protocol' },
                { text: 'Scenarios', link: '/docs/scenarios' },
                { text: 'Mailbox Naming', link: '/docs/mailbox-naming' },
              ],
            },
            {
              text: 'SDK',
              items: [
                { text: 'Python', link: '/docs/sdk/python' },
                { text: 'JavaScript', link: '/docs/sdk/javascript' },
                { text: 'Go', link: '/docs/sdk/go' },
                { text: 'Rust', link: '/docs/sdk/rust' },
                { text: 'Java', link: '/docs/sdk/java' },
                { text: 'C#', link: '/docs/sdk/csharp' },
              ],
            },
            {
              text: 'Integrations',
              items: [
                { text: 'LangChain / LangGraph', link: '/docs/langchain' },
                { text: 'MCP Server', link: '/docs/mcp' },
                {
                  text: 'A2A Protocol',
                  items: [
                    { text: 'Overview', link: '/docs/a2a' },
                    { text: 'Python', link: '/docs/a2a/python' },
                  ],
                },
              ],
            },
            {
              text: 'Reference',
              items: [
                { text: 'FAQ', link: '/docs/faq' },
                { text: 'Roadmap', link: '/docs/roadmap' },
                { text: 'Registry Roadmap', link: '/docs/registry-roadmap' },
                { text: 'Messaging Roadmap', link: '/docs/messaging-roadmap' },
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
          { text: '文档', link: '/zh/docs/what' },
          { text: 'Blogs', link: 'https://robustmq.com/zh/Blogs/' },
          { text: 'GitHub', link: 'https://github.com/robustmq/mq9' },
          { text: 'RobustMQ', link: 'https://github.com/robustmq/robustmq' },
        ],
        sidebar: {
          '/zh/docs/': [
            {
              text: '快速入门',
              items: [
                { text: 'mq9 是什么', link: '/zh/docs/what' },
                { text: '给工程师', link: '/zh/docs/for-engineer' },
                { text: '给 Agent', link: '/zh/docs/for-agent' },
                { text: '快速开始', link: '/zh/docs/quick-start' },
              ],
            },
            {
              text: '深入了解',
              items: [
                { text: '系统架构', link: '/zh/docs/architecture' },
                { text: '功能特性', link: '/zh/docs/features' },
                { text: '协议规范', link: '/zh/docs/protocol' },
                { text: '使用场景', link: '/zh/docs/scenarios' },
                { text: '邮箱命名规范', link: '/zh/docs/mailbox-naming' },
              ],
            },
            {
              text: 'SDK',
              items: [
                { text: 'Python', link: '/zh/docs/sdk/python' },
                { text: 'JavaScript', link: '/zh/docs/sdk/javascript' },
                { text: 'Go', link: '/zh/docs/sdk/go' },
                { text: 'Rust', link: '/zh/docs/sdk/rust' },
                { text: 'Java', link: '/zh/docs/sdk/java' },
                { text: 'C#', link: '/zh/docs/sdk/csharp' },
              ],
            },
            {
              text: '集成',
              items: [
                { text: 'LangChain / LangGraph', link: '/zh/docs/langchain' },
                { text: 'MCP Server', link: '/zh/docs/mcp' },
                {
                  text: 'A2A 协议',
                  items: [
                    { text: '概述', link: '/zh/docs/a2a' },
                    { text: 'Python', link: '/zh/docs/a2a/python' },
                  ],
                },
              ],
            },
            {
              text: '参考',
              items: [
                { text: '常见问题', link: '/zh/docs/faq' },
                { text: '路线图', link: '/zh/docs/roadmap' },
                { text: '注册中心规划', link: '/zh/docs/registry-roadmap' },
                { text: '通信规划', link: '/zh/docs/messaging-roadmap' },
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
    socialLinks: [
      { icon: 'github', link: 'https://github.com/robustmq/mq9' },
    ],
  },

  sitemap: {
    hostname: 'https://mq9.robustmq.com',
  },
})
