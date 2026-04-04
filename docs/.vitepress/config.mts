import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'mq9 — Agent-to-Agent messaging, solved.',
  titleTemplate: ':title — mq9',
  description: 'Running multiple Agents? They need to talk to each other. mq9 handles it — reliably, asynchronously, at any scale.',
  lang: 'en-US',
  base: '/',
  cleanUrls: true,
  appearance: 'force-light',

  head: [
    ['link', { rel: 'icon', type: 'image/svg+xml', href: '/favicon.svg' }],
    ['link', { rel: 'preconnect', href: 'https://fonts.googleapis.com' }],
    ['link', { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossorigin: '' }],
    ['link', { rel: 'stylesheet', href: 'https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@700&display=swap' }],

    // Basic SEO
    ['meta', { name: 'author', content: 'mq9' }],
    ['meta', { name: 'keywords', content: 'mq9, AI agent messaging, agent communication, async messaging, NATS, agent mailbox, multi-agent system, agent-to-agent, offline delivery' }],
    ['meta', { name: 'robots', content: 'index, follow' }],

    // Open Graph
    ['meta', { property: 'og:type', content: 'website' }],
    ['meta', { property: 'og:site_name', content: 'mq9' }],
    ['meta', { property: 'og:title', content: 'mq9 — Agent-to-Agent messaging, solved.' }],
    ['meta', { property: 'og:description', content: 'Running multiple Agents? They need to talk to each other. mq9 handles it — reliably, asynchronously, at any scale.' }],
    ['meta', { property: 'og:url', content: 'https://mq9.robustmq.com' }],
    ['meta', { property: 'og:image', content: 'https://mq9.robustmq.com/og-image.png' }],

    // Twitter / X
    ['meta', { name: 'twitter:card', content: 'summary_large_image' }],
    ['meta', { name: 'twitter:title', content: 'mq9 — Agent-to-Agent messaging, solved.' }],
    ['meta', { name: 'twitter:description', content: 'Running multiple Agents? They need to talk to each other. mq9 handles it — reliably, asynchronously, at any scale.' }],
    ['meta', { name: 'twitter:image', content: 'https://mq9.robustmq.com/og-image.png' }],

    // Canonical
    ['link', { rel: 'canonical', href: 'https://mq9.robustmq.com' }],
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
    hostname: 'https://mq9.robustmq.com',
  },
})
