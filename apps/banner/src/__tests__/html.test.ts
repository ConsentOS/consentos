import { describe, expect, it } from 'vitest';

import { escapeHtml, isAllowedLinkUrl, isValidColour, isValidFontFamily } from '../html';
import cssValues from './fixtures/css-values.json';

describe('escapeHtml', () => {
  it('escapes markup characters', () => {
    expect(escapeHtml(`<a href="x">Tom & Jerry's</a>`)).toBe(
      '&lt;a href=&quot;x&quot;&gt;Tom &amp; Jerry&#39;s&lt;/a&gt;',
    );
  });

  it('leaves plain text unchanged', () => {
    expect(escapeHtml('Accept all')).toBe('Accept all');
  });
});

describe('isAllowedLinkUrl', () => {
  it.each([
    'https://example.com/privacy',
    'http://example.com',
    'HTTPS://EXAMPLE.COM',
    '/privacy',
    'privacy.html',
    '#terms',
    '?q=1',
    '  https://example.com  ',
  ])('allows %s', (url) => {
    expect(isAllowedLinkUrl(url)).toBe(true);
  });

  it.each([
    '',
    '   ',
    'javascript:void(0)',
    'data:text/html,hi',
    'vbscript:x',
    'mailto:a@example.com',
    'java\tscript:x',
    'https://exa mple.com',
    '//example.com/privacy',
    '/\\example.com/privacy',
    '\\\\example.com',
  ])('rejects %j', (url) => {
    expect(isAllowedLinkUrl(url)).toBe(false);
  });
});

describe('isValidColour', () => {
  it.each(cssValues.colour.valid)('accepts %j', (value) => {
    expect(isValidColour(value)).toBe(true);
  });

  it.each([...cssValues.colour.invalid, '', 'a'.repeat(201), 42, null, undefined])('rejects %j', (value) => {
    expect(isValidColour(value)).toBe(false);
  });

  it('accepts up to 200 characters', () => {
    expect(isValidColour('a'.repeat(200))).toBe(true);
  });
});

describe('isValidFontFamily', () => {
  it.each(cssValues.fontFamily.valid)('accepts %j', (value) => {
    expect(isValidFontFamily(value)).toBe(true);
  });

  it.each([...cssValues.fontFamily.invalid, '', 'a'.repeat(201), 7, undefined])('rejects %j', (value) => {
    expect(isValidFontFamily(value)).toBe(false);
  });
});
