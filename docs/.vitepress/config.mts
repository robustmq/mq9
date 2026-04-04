import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'mq9',
  description: 'The Communication Layer for AI Agents',
  lang: 'en-US',
  cleanUrls: true,
  appearance: 'force-light',

  head: [
    ['link', { rel: 'icon', type: 'image/svg+xml', href: '/favicon.svg' }],
    ['link', { rel: 'preconnect', href: 'https://fonts.googleapis.com' }],
    ['link', { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossorigin: '' }],
    ['link', { rel: 'stylesheet', href: 'https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@700&display=swap' }],
    ['meta', { name: 'author', content: 'mq9' }],
    ['meta', { name: 'keywords', content: 'mq9, AI agent, message queue, NATS, async communication, mailbox' }],
    ['meta', { property: 'og:type', content: 'website' }],
    ['meta', { property: 'og:site_name', content: 'mq9' }],
    ['meta', { property: 'og:image', content: 'https://mq9.ai/og-image.png' }],
    ['meta', { name: 'twitter:card', content: 'summary_large_image' }],
  ],

  themeConfig: {
    siteTitle: 'mq9',

    nav: [
      { text: 'Home', link: '/' },
      { text: 'What', link: '/what' },
      { text: 'For Agent', link: '/for-agent' },
      { text: 'For Engineer', link: '/for-engineer' },
      {
        text: 'GitHub',
        link: 'https://github.com/robustmq/robustmq',
      },
    ],

    sidebar: false,
    aside: false,

    footer: {
      message: 'Built on <a href="https://github.com/robustmq/robustmq" target="_blank">RobustMQ</a>',
      copyright: '© 2025 mq9',
    },

    socialLinks: [
      { icon: 'github', link: 'https://github.com/robustmq/robustmq' },
    ],
  },

  sitemap: {
    hostname: 'https://mq9.ai',
  },
})
