import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import BannerPreview from '../components/BannerPreview';
import type { BannerConfig } from '../types/api';

const DEFAULT_CONFIG: BannerConfig = {
  primaryColour: '#2563eb',
  backgroundColour: '#ffffff',
  textColour: '#1a1a2e',
  fontFamily: 'system-ui',
  borderRadius: 6,
  showRejectAll: true,
  showManagePreferences: true,
  showCloseButton: false,
  showLogo: false,
  showCookieCount: false,
};

describe('BannerPreview', () => {
  it('renders the preview container', () => {
    render(
      <BannerPreview
        bannerConfig={DEFAULT_CONFIG}
        displayMode="bottom_banner"
        viewport="desktop"
        privacyPolicyUrl={null}
      />,
    );

    expect(screen.getByTestId('banner-preview')).toBeInTheDocument();
  });

  it('renders an iframe with srcdoc', () => {
    render(
      <BannerPreview
        bannerConfig={DEFAULT_CONFIG}
        displayMode="bottom_banner"
        viewport="desktop"
        privacyPolicyUrl={null}
      />,
    );

    const iframe = screen.getByTitle('Banner preview') as HTMLIFrameElement;
    expect(iframe).toBeInTheDocument();
    expect(iframe.getAttribute('srcdoc')).toBeTruthy();
    expect(iframe.getAttribute('sandbox')).toBe('allow-scripts');
  });

  it('includes banner text in srcdoc', () => {
    render(
      <BannerPreview
        bannerConfig={DEFAULT_CONFIG}
        displayMode="bottom_banner"
        viewport="desktop"
        privacyPolicyUrl={null}
      />,
    );

    const iframe = screen.getByTitle('Banner preview') as HTMLIFrameElement;
    const srcdoc = iframe.getAttribute('srcdoc')!;
    expect(srcdoc).toContain('We use cookies');
    expect(srcdoc).toContain('Accept all');
    expect(srcdoc).toContain('Reject all');
    expect(srcdoc).toContain('Manage preferences');
  });

  it('applies theme colours to srcdoc', () => {
    render(
      <BannerPreview
        bannerConfig={{ ...DEFAULT_CONFIG, primaryColour: '#ff0000', backgroundColour: '#111111' }}
        displayMode="bottom_banner"
        viewport="desktop"
        privacyPolicyUrl={null}
      />,
    );

    const srcdoc = (screen.getByTitle('Banner preview') as HTMLIFrameElement).getAttribute('srcdoc')!;
    expect(srcdoc).toContain('#ff0000');
    expect(srcdoc).toContain('#111111');
  });

  it('hides reject all button when showRejectAll is false', () => {
    render(
      <BannerPreview
        bannerConfig={{ ...DEFAULT_CONFIG, showRejectAll: false }}
        displayMode="bottom_banner"
        viewport="desktop"
        privacyPolicyUrl={null}
      />,
    );

    const srcdoc = (screen.getByTitle('Banner preview') as HTMLIFrameElement).getAttribute('srcdoc')!;
    expect(srcdoc).not.toContain('Reject all');
  });

  it('hides manage preferences when showManagePreferences is false', () => {
    render(
      <BannerPreview
        bannerConfig={{ ...DEFAULT_CONFIG, showManagePreferences: false }}
        displayMode="bottom_banner"
        viewport="desktop"
        privacyPolicyUrl={null}
      />,
    );

    const srcdoc = (screen.getByTitle('Banner preview') as HTMLIFrameElement).getAttribute('srcdoc')!;
    expect(srcdoc).not.toContain('Manage preferences');
  });

  it('shows close button when enabled', () => {
    render(
      <BannerPreview
        bannerConfig={{ ...DEFAULT_CONFIG, showCloseButton: true }}
        displayMode="bottom_banner"
        viewport="desktop"
        privacyPolicyUrl={null}
      />,
    );

    const srcdoc = (screen.getByTitle('Banner preview') as HTMLIFrameElement).getAttribute('srcdoc')!;
    expect(srcdoc).toContain('cmp-close');
  });

  it('does not show close button element when disabled', () => {
    render(
      <BannerPreview
        bannerConfig={{ ...DEFAULT_CONFIG, showCloseButton: false }}
        displayMode="bottom_banner"
        viewport="desktop"
        privacyPolicyUrl={null}
      />,
    );

    const srcdoc = (screen.getByTitle('Banner preview') as HTMLIFrameElement).getAttribute('srcdoc')!;
    // The CSS class may still exist in styles, but the button element should not be rendered
    expect(srcdoc).not.toContain('<button class="cmp-close"');
  });

  it('shows cookie count when enabled', () => {
    render(
      <BannerPreview
        bannerConfig={{ ...DEFAULT_CONFIG, showCookieCount: true }}
        displayMode="bottom_banner"
        viewport="desktop"
        privacyPolicyUrl={null}
      />,
    );

    const srcdoc = (screen.getByTitle('Banner preview') as HTMLIFrameElement).getAttribute('srcdoc')!;
    expect(srcdoc).toContain('12 cookies used on this site');
  });

  it('shows logo when configured', () => {
    render(
      <BannerPreview
        bannerConfig={{ ...DEFAULT_CONFIG, showLogo: true, logoUrl: 'https://example.com/logo.svg' }}
        displayMode="bottom_banner"
        viewport="desktop"
        privacyPolicyUrl={null}
      />,
    );

    const srcdoc = (screen.getByTitle('Banner preview') as HTMLIFrameElement).getAttribute('srcdoc')!;
    expect(srcdoc).toContain('cmp-logo');
    expect(srcdoc).toContain('https://example.com/logo.svg');
  });

  it('includes privacy policy link when URL provided', () => {
    render(
      <BannerPreview
        bannerConfig={DEFAULT_CONFIG}
        displayMode="bottom_banner"
        viewport="desktop"
        privacyPolicyUrl="https://example.com/privacy"
      />,
    );

    const srcdoc = (screen.getByTitle('Banner preview') as HTMLIFrameElement).getAttribute('srcdoc')!;
    expect(srcdoc).toContain('Privacy Policy');
  });

  it('uses mobile width when viewport is mobile', () => {
    render(
      <BannerPreview
        bannerConfig={DEFAULT_CONFIG}
        displayMode="bottom_banner"
        viewport="mobile"
        privacyPolicyUrl={null}
      />,
    );

    const iframe = screen.getByTitle('Banner preview');
    expect(iframe).toHaveStyle({ width: '375px' });
  });

  it('uses full width for desktop viewport', () => {
    render(
      <BannerPreview
        bannerConfig={DEFAULT_CONFIG}
        displayMode="bottom_banner"
        viewport="desktop"
        privacyPolicyUrl={null}
      />,
    );

    const iframe = screen.getByTitle('Banner preview');
    expect(iframe).toHaveStyle({ width: '100%' });
  });

  it('applies overlay positioning styles', () => {
    render(
      <BannerPreview
        bannerConfig={DEFAULT_CONFIG}
        displayMode="overlay"
        viewport="desktop"
        privacyPolicyUrl={null}
      />,
    );

    const srcdoc = (screen.getByTitle('Banner preview') as HTMLIFrameElement).getAttribute('srcdoc')!;
    expect(srcdoc).toContain('transform: translate(-50%, -50%)');
    expect(srcdoc).toContain('cmp-overlay-bg');
  });

  it('applies corner popup positioning styles', () => {
    render(
      <BannerPreview
        bannerConfig={DEFAULT_CONFIG}
        displayMode="corner_popup"
        viewport="desktop"
        privacyPolicyUrl={null}
      />,
    );

    const srcdoc = (screen.getByTitle('Banner preview') as HTMLIFrameElement).getAttribute('srcdoc')!;
    expect(srcdoc).toContain('bottom: 20px');
    expect(srcdoc).toContain('right: 20px');
    expect(srcdoc).toContain('width: 380px');
  });

  it('applies a custom banner width to the overlay modal', () => {
    render(
      <BannerPreview
        bannerConfig={{ ...DEFAULT_CONFIG, bannerWidth: 480 }}
        displayMode="overlay"
        viewport="desktop"
        privacyPolicyUrl={null}
      />,
    );

    const srcdoc = (screen.getByTitle('Banner preview') as HTMLIFrameElement).getAttribute('srcdoc')!;
    expect(srcdoc).toContain('max-width: 480px');
  });

  it('applies top banner positioning', () => {
    render(
      <BannerPreview
        bannerConfig={DEFAULT_CONFIG}
        displayMode="top_banner"
        viewport="desktop"
        privacyPolicyUrl={null}
      />,
    );

    const srcdoc = (screen.getByTitle('Banner preview') as HTMLIFrameElement).getAttribute('srcdoc')!;
    expect(srcdoc).toContain('top: 0');
  });

  it('applies border radius to buttons', () => {
    render(
      <BannerPreview
        bannerConfig={{ ...DEFAULT_CONFIG, borderRadius: 12 }}
        displayMode="bottom_banner"
        viewport="desktop"
        privacyPolicyUrl={null}
      />,
    );

    const srcdoc = (screen.getByTitle('Banner preview') as HTMLIFrameElement).getAttribute('srcdoc')!;
    expect(srcdoc).toContain('border-radius: 12px');
  });

  it('applies a per-button outline style', () => {
    render(
      <BannerPreview
        bannerConfig={{ ...DEFAULT_CONFIG, acceptButton: { style: 'outline' } }}
        displayMode="bottom_banner"
        viewport="desktop"
        privacyPolicyUrl={null}
      />,
    );

    const srcdoc = (screen.getByTitle('Banner preview') as HTMLIFrameElement).getAttribute('srcdoc')!;
    expect(srcdoc).toContain('background: transparent');
  });

  it('applies custom font family', () => {
    render(
      <BannerPreview
        bannerConfig={{ ...DEFAULT_CONFIG, fontFamily: "'Inter', sans-serif" }}
        displayMode="bottom_banner"
        viewport="desktop"
        privacyPolicyUrl={null}
      />,
    );

    const srcdoc = (screen.getByTitle('Banner preview') as HTMLIFrameElement).getAttribute('srcdoc')!;
    expect(srcdoc).toContain("'Inter', sans-serif");
  });

  it('includes category preferences section', () => {
    render(
      <BannerPreview
        bannerConfig={DEFAULT_CONFIG}
        displayMode="bottom_banner"
        viewport="desktop"
        privacyPolicyUrl={null}
      />,
    );

    const srcdoc = (screen.getByTitle('Banner preview') as HTMLIFrameElement).getAttribute('srcdoc')!;
    expect(srcdoc).toContain('Necessary');
    expect(srcdoc).toContain('Functional');
    expect(srcdoc).toContain('Analytics');
    expect(srcdoc).toContain('Marketing');
    expect(srcdoc).toContain('Personalisation');
    expect(srcdoc).toContain('Save preferences');
  });

  it('escapes HTML in logo URL', () => {
    render(
      <BannerPreview
        bannerConfig={{
          ...DEFAULT_CONFIG,
          showLogo: true,
          logoUrl: 'https://example.com/logo.svg?a=1&b=2',
        }}
        displayMode="bottom_banner"
        viewport="desktop"
        privacyPolicyUrl={null}
      />,
    );

    const srcdoc = (screen.getByTitle('Banner preview') as HTMLIFrameElement).getAttribute('srcdoc')!;
    expect(srcdoc).toContain('&amp;');
    expect(srcdoc).not.toContain('?a=1&b=2"');
  });
});
