import typescript from '@rollup/plugin-typescript';
import terser from '@rollup/plugin-terser';

export default [
  // consent-loader.js — lightweight synchronous bootstrap (~2KB gzipped)
  {
    input: 'src/loader.ts',
    output: {
      file: 'dist/consent-loader.js',
      format: 'iife',
      name: 'CmpLoader',
      sourcemap: false,
    },
    plugins: [
      typescript({ tsconfig: './tsconfig.json', declaration: false }),
      terser(),
    ],
  },
  // consent-bundle.js — full banner + consent engine
  {
    input: 'src/banner.ts',
    output: {
      file: 'dist/consent-bundle.js',
      format: 'iife',
      name: 'CmpBanner',
      // No sourcemap in the published bundle. The file is minified
      // and served cross-origin from customer sites; shipping the
      // map would publish our source tree to anyone inspecting the
      // page. Build locally if you need to debug.
      sourcemap: false,
    },
    plugins: [
      typescript({ tsconfig: './tsconfig.json', declaration: false }),
      terser(),
    ],
  },
];
