# Documentation Site Setup

This directory contains the Docusaurus documentation site for kserve-vllm-mini.

## Quick Start

```bash
# Install dependencies
cd docs/website
npm install

# Start development server
npm start

# Build for production
npm run build

# Serve production build
npm run serve
```

## Deployment

### Netlify (Recommended)

1. Connect your GitHub repository to Netlify
2. Set build command: `cd docs/website && npm run build`
3. Set publish directory: `docs/website/build`
4. Deploy!

### GitHub Pages

```bash
# Deploy to GitHub Pages
npm run deploy
```

### Manual Deployment

```bash
# Build the site
npm run build

# Upload the `build` directory to your hosting provider
```

## Site Structure

```
docs/website/
├── docs/                   # Documentation pages
├── blog/                   # Blog posts
├── src/
│   ├── components/         # React components
│   ├── css/               # Custom CSS
│   └── pages/             # Custom pages
├── static/                # Static assets
├── docusaurus.config.js   # Site configuration
└── sidebars.js            # Documentation sidebar
```

## Adding Content

### Documentation Pages
Create `.md` files in `docs/` directory. Use frontmatter for metadata:

```markdown
---
sidebar_position: 1
title: My Page
description: Page description
---

# My Page Content
```

### Blog Posts
Create `.md` files in `blog/` directory with date prefix:

```
blog/
├── 2025-09-12-welcome.md
├── 2025-10-01-new-features.md
└── authors.yml
```

### Custom Pages
Add React components to `src/pages/` for custom pages.

## Configuration

Key configuration options in `docusaurus.config.js`:

- **Site metadata**: title, tagline, URL
- **Theme configuration**: navbar, footer, search
- **Plugin configuration**: docs, blog, sitemap
- **Deployment settings**: GitHub Pages, custom domains

## Customization

### Styling
- Modify `src/css/custom.css` for global styles
- Use CSS modules for component-specific styles
- Customize Infima variables for theme colors

### Components
- Create reusable components in `src/components/`
- Use MDX for interactive documentation
- Add Mermaid diagrams with `@docusaurus/theme-mermaid`

### Search
Configure Algolia DocSearch for site search:

1. Apply for DocSearch at https://docsearch.algolia.com/apply/
2. Update `docusaurus.config.js` with your search credentials
3. Algolia will crawl your site and provide search functionality

## Content Guidelines

### Writing Style
- Use clear, concise language
- Include code examples for technical concepts
- Add screenshots for visual processes
- Cross-reference related documentation

### Organization
- Group related topics in categories
- Use consistent naming conventions
- Maintain logical information hierarchy
- Update sidebar configuration as needed

## Maintenance

### Regular Tasks
- Update dependencies monthly
- Review and update documentation for accuracy
- Check and fix broken links
- Monitor site performance and loading times

### Content Reviews
- Quarterly documentation audits
- Update examples with latest software versions
- Gather feedback from community and improve content
- Archive outdated information

This documentation site serves as the professional face of the kserve-vllm-mini project and should reflect the same quality and attention to detail as the codebase itself.
