// @ts-check
// `@type` JSDoc annotations allow editor autocompletion and type checking
// (when paired with `@ts-check`).
// There are various equivalent ways to declare your Docusaurus config.
// See: https://docusaurus.io/docs/api/docusaurus-config

import {themes as prismThemes} from 'prism-react-renderer';

/** @type {import('@docusaurus/types').Config} */
const config = {
  title: 'kserve-vllm-mini',
  tagline: 'Professional KServe + vLLM benchmarking toolkit',
  favicon: 'img/favicon.ico',

  // Set the production url of your site here
  url: 'https://siryoos.github.io',
  // Set the /<baseUrl>/ pathname under which your site is served
  // For GitHub pages deployment, it is often '/<projectName>/'
  baseUrl: '/kserve-vllm-mini/',

  // GitHub pages deployment config.
  // If you aren't using GitHub pages, you don't need these.
  organizationName: 'siryoos', // Usually your GitHub org/user name.
  projectName: 'kserve-vllm-mini', // Usually your repo name.

  onBrokenLinks: 'warn',
  onBrokenMarkdownLinks: 'warn',

  // Even if you don't use internationalization, you can use this field to set
  // useful metadata like html lang. For example, if your site is Chinese, you
  // may want to set it to `zh-Hans`.
  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  markdown: {
    mermaid: true,
  },
  themes: ['@docusaurus/theme-mermaid'],

  presets: [
    [
      'classic',
      /** @type {import('@docusaurus/preset-classic').Options} */
      ({
        docs: {
          sidebarPath: './sidebars.js',
          // Please change this to your repo.
          // Remove this to remove the "edit this page" links.
          editUrl:
            'https://github.com/siryoos/kserve-vllm-mini/tree/main/docs/website/',
        },
        blog: {
          showReadingTime: true,
          feedOptions: {
            type: ['rss', 'atom'],
            xslt: true,
          },
          // Please change this to your repo.
          // Remove this to remove the "edit this page" links.
          editUrl:
            'https://github.com/siryoos/kserve-vllm-mini/tree/main/docs/website/',
          // Useful options to enforce blogging best practices
          onInlineTags: 'warn',
          onInlineAuthors: 'warn',
          onUntruncatedBlogPosts: 'warn',
        },
        theme: {
          customCss: './src/css/custom.css',
        },
      }),
    ],
  ],

  themeConfig:
    /** @type {import('@docusaurus/preset-classic').ThemeConfig} */
    ({
      // Replace with your project's social card
      image: 'img/kserve-vllm-mini-social-card.jpg',
      navbar: {
        title: 'kserve-vllm-mini',
        logo: {
          alt: 'kserve-vllm-mini Logo',
          src: 'img/logo.svg',
        },
        items: [
          {
            type: 'docSidebar',
            sidebarId: 'tutorialSidebar',
            position: 'left',
            label: 'Docs',
          },
          {to: '/blog', label: 'Blog', position: 'left'},
          {
            href: 'https://github.com/siryoos/kserve-vllm-mini',
            label: 'GitHub',
            position: 'right',
          },
          {
            href: 'https://github.com/siryoos/kserve-vllm-mini/discussions',
            label: 'Discussions',
            position: 'right',
          },
        ],
      },
      footer: {
        style: 'dark',
        links: [
          {
            title: 'Docs',
            items: [
              {
                label: 'Quick Start',
                to: '/docs/quickstart',
              },
              {
                label: 'Features',
                to: '/docs/features',
              },
              {
                label: 'Profiles',
                to: '/docs/profiles',
              },
            ],
          },
          {
            title: 'Community',
            items: [
              {
                label: 'Discussions',
                href: 'https://github.com/siryoos/kserve-vllm-mini/discussions',
              },
              {
                label: 'Contributing',
                href: 'https://github.com/siryoos/kserve-vllm-mini/blob/main/CONTRIBUTING.md',
              },
              {
                label: 'Roadmap',
                href: 'https://github.com/siryoos/kserve-vllm-mini/projects/1',
              },
            ],
          },
          {
            title: 'More',
            items: [
              {
                label: 'Blog',
                to: '/blog',
              },
              {
                label: 'GitHub',
                href: 'https://github.com/siryoos/kserve-vllm-mini',
              },
              {
                label: 'KServe',
                href: 'https://kserve.github.io/website/',
              },
              {
                label: 'vLLM',
                href: 'https://github.com/vllm-project/vllm',
              },
            ],
          },
        ],
        copyright: `Copyright © ${new Date().getFullYear()} kserve-vllm-mini contributors. Built with Docusaurus.`,
      },
      prism: {
        theme: prismThemes.github,
        darkTheme: prismThemes.dracula,
        additionalLanguages: ['bash', 'yaml', 'json'],
      },
      algolia: {
        // The application ID provided by Algolia
        appId: process.env.ALGOLIA_APP_ID || '',
        // Public API key: it is safe to commit it
        apiKey: process.env.ALGOLIA_API_KEY || '',
        indexName: 'kserve-vllm-mini',
        // Optional: see doc section below
        contextualSearch: true,
        // Optional: path for search page that enabled by default (`false` to disable it)
        searchPagePath: 'search',
      },
      // Add announcement bar for important updates
      announcementBar: {
        id: 'support_ukraine',
        content:
          '⭐ If you like kserve-vllm-mini, give it a star on <a target="_blank" rel="noopener noreferrer" href="https://github.com/siryoos/kserve-vllm-mini">GitHub</a>!',
        backgroundColor: '#fafbfc',
        textColor: '#091E42',
        isCloseable: false,
      },
    }),
};

export default config;
