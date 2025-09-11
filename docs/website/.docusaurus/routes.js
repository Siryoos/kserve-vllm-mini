import React from 'react';
import ComponentCreator from '@docusaurus/ComponentCreator';

export default [
  {
    path: '/kserve-vllm-mini/search',
    component: ComponentCreator('/kserve-vllm-mini/search', 'e45'),
    exact: true
  },
  {
    path: '/kserve-vllm-mini/docs',
    component: ComponentCreator('/kserve-vllm-mini/docs', '2d1'),
    routes: [
      {
        path: '/kserve-vllm-mini/docs',
        component: ComponentCreator('/kserve-vllm-mini/docs', 'aec'),
        routes: [
          {
            path: '/kserve-vllm-mini/docs',
            component: ComponentCreator('/kserve-vllm-mini/docs', '787'),
            routes: [
              {
                path: '/kserve-vllm-mini/docs/intro',
                component: ComponentCreator('/kserve-vllm-mini/docs/intro', '012'),
                exact: true,
                sidebar: "tutorialSidebar"
              }
            ]
          }
        ]
      }
    ]
  },
  {
    path: '/kserve-vllm-mini/',
    component: ComponentCreator('/kserve-vllm-mini/', 'cad'),
    exact: true
  },
  {
    path: '*',
    component: ComponentCreator('*'),
  },
];
