/**
 * Creating a sidebar enables you to:
 - create an ordered group of docs
 - render a sidebar for each doc of that group
 - provide next/previous navigation

 The sidebars can be generated from the filesystem, or explicitly defined here.

 Create as many sidebars as you want.
 */

// @ts-check

/** @type {import('@docusaurus/plugin-content-docs').SidebarsConfig} */
const sidebars = {
  // By default, Docusaurus generates a sidebar from the docs folder structure
  tutorialSidebar: [
    'intro',
    {
      type: 'category',
      label: 'Getting Started',
      items: [
        'getting-started/installation',
        'getting-started/quickstart',
        'getting-started/first-benchmark',
      ],
    },
    {
      type: 'category',
      label: 'Features',
      items: [
        'features/overview',
        'features/vllm-features',
        'features/quantization',
        'features/backend-comparison',
        'features/energy-monitoring',
      ],
    },
    {
      type: 'category',
      label: 'Profiles',
      items: [
        'profiles/overview',
        'profiles/standard-profiles',
        'profiles/quantization-profiles',
        'profiles/advanced-features',
        'profiles/creating-profiles',
      ],
    },
    {
      type: 'category',
      label: 'Guides',
      items: [
        'guides/configuration',
        'guides/troubleshooting',
        'guides/performance-tuning',
        'guides/cloud-deployment',
      ],
    },
    {
      type: 'category',
      label: 'Reference',
      items: [
        'reference/cli',
        'reference/profiles',
        'reference/metrics',
        'reference/api',
      ],
    },
    {
      type: 'category',
      label: 'Contributing',
      items: [
        'contributing/overview',
        'contributing/development',
        'contributing/profiles',
        'contributing/documentation',
      ],
    },
  ],

  // But you can create a sidebar manually
  /*
  tutorialSidebar: [
    'intro',
    'hello',
    {
      type: 'category',
      label: 'Tutorial',
      items: ['tutorial-basics/create-a-document'],
    },
  ],
   */
};

export default sidebars;
