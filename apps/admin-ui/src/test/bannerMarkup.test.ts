import { describe, expect, it } from 'vitest';

import {
  colourOr,
  escapeHtml,
  isAllowedLinkUrl,
  isValidColour,
  isValidFontFamily,
  pixelsOr,
  renderLinks,
} from '../utils/bannerMarkup';

describe('bannerMarkup', () => {
  it('escapes HTML special characters including single quotes', () => {
    expect(escapeHtml(`<b class="x">'&'</b>`)).toBe('&lt;b class=&quot;x&quot;&gt;&#39;&amp;&#39;&lt;/b&gt;');
  });

  it.each(['#fff', '#2C6AE4', 'rgb(0, 0, 0)', 'hsl(var(--p))', 'var(--brand)', 'oklch(70% 0.1 200)', 'color-mix(in srgb, red, blue)', 'linear-gradient(red, blue)'])(
    'accepts colour %s',
    (value) => {
      expect(isValidColour(value)).toBe(true);
    },
  );

  it.each(['red;}', 'red</style>', 'url(x)', 'red /* x */', '"red"', 'a\\62', '', 'x'.repeat(201), 're\nd'])(
    'rejects colour %j',
    (value) => {
      expect(isValidColour(value)).toBe(false);
    },
  );

  it('accepts font stacks with closed quotes and rejects unclosed ones', () => {
    expect(isValidFontFamily(`"Open Sans", 'Helvetica Neue', sans-serif`)).toBe(true);
    expect(isValidFontFamily(`"Open Sans, sans-serif`)).toBe(false);
    expect(isValidFontFamily(`Inter; color: red`)).toBe(false);
  });

  it('falls back for invalid colours and pixel values', () => {
    expect(colourOr(' #123456 ', '#000')).toBe('#123456');
    expect(colourOr('red;}', '#000')).toBe('#000');
    expect(colourOr(undefined, '#000')).toBe('#000');
    expect(pixelsOr(12, 6)).toBe(12);
    expect(pixelsOr('12', 6)).toBe(6);
    expect(pixelsOr(-1, 6)).toBe(6);
  });

  it('allows only http(s) and relative link targets', () => {
    expect(isAllowedLinkUrl('https://example.com/privacy')).toBe(true);
    expect(isAllowedLinkUrl('/privacy')).toBe(true);
    expect(isAllowedLinkUrl('javascript:alert(1)')).toBe(false);
    expect(isAllowedLinkUrl('mailto:a@example.com')).toBe(false);
    expect(isAllowedLinkUrl('//example.com')).toBe(false);
    expect(isAllowedLinkUrl('/\\example.com')).toBe(false);
  });

  it('escapes text, renders allowed links and drops empty or disallowed ones', () => {
    expect(renderLinks('<b>Hi</b> [Policy](https://example.com/p)')).toBe(
      '&lt;b&gt;Hi&lt;/b&gt; <a href="https://example.com/p" target="_blank" rel="noopener" class="consentos-banner__link">Policy</a>',
    );
    expect(renderLinks('Read [Terms]() now')).toBe('Readnow');
    expect(renderLinks('[Click](javascript:alert(1))')).toBe('Click)');
  });
});
