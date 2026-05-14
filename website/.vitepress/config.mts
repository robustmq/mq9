import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'mq9 — A message broker for AI Agents.',
  titleTemplate: ':title — mq9',
  description: 'Deploy once. Every Agent gets a mailbox. Send to any Agent — online or offline. Messages are stored and delivered when ready. Point-to-point, broadcast, offline recovery. One binary, nothing else to install.',
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
    ['meta', { property: 'og:title', content: 'mq9 — A message broker for AI Agents.' }],
    ['meta', { property: 'og:description', content: 'Deploy once. Every Agent gets a mailbox. Send to any Agent — online or offline. Messages are stored and delivered when ready. Point-to-point, broadcast, offline recovery. One binary, nothing else to install.' }],
    ['meta', { property: 'og:url', content: 'https://mq9.robustmq.com' }],
    ['meta', { property: 'og:image', content: 'https://mq9.robustmq.com/og-image.png' }],

    // Twitter / X
    ['meta', { name: 'twitter:card', content: 'summary_large_image' }],
    ['meta', { name: 'twitter:title', content: 'mq9 — A message broker for AI Agents.' }],
    ['meta', { name: 'twitter:description', content: 'Deploy once. Every Agent gets a mailbox. Send to any Agent — online or offline. Messages are stored and delivered when ready. Point-to-point, broadcast, offline recovery. One binary, nothing else to install.' }],
    ['meta', { name: 'twitter:image', content: 'https://mq9.robustmq.com/og-image.png' }],

    // Canonical
    ['link', { rel: 'canonical', href: 'https://mq9.robustmq.com' }],

    // 51.la 访问统计
    ['script', { charset: 'UTF-8', id: 'LA_COLLECT', src: '//sdk.51.la/js-sdk-pro.min.js' }],
    ['script', {}, `LA.init({id:"3PUlhxY3LHemHVJk",ck:"3PUlhxY3LHemHVJk",autoTrack:true,hashMode:true})`],
  ],

  themeConfig: {
    siteTitle: 'mq9',

    nav: [
      { text: 'Home', link: '/' },
      { text: 'What', link: '/what' },
      { text: 'For Agent', link: '/for-agent' },
      { text: 'For Engineer', link: '/for-engineer' },
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
      {
        text: 'GitHub',
        link: 'https://github.com/robustmq/robustmq',
      },
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
    },

    aside: false,


    socialLinks: [
      { icon: 'github', link: 'https://github.com/robustmq/robustmq' },
    ],
  },

  sitemap: {
    hostname: 'https://mq9.robustmq.com',
  },
})
