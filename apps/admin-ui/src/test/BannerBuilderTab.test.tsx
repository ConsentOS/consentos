import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import BannerBuilderTab from '../components/BannerBuilderTab';
import type { BannerConfig } from '../types/api';

vi.mock('../api/translations', () => ({
  listTranslations: vi.fn(async () => [
    { id: '1', site_id: 'site-1', locale: 'de', strings: { title: 'Wir verwenden Cookies' }, created_at: '', updated_at: '' },
  ]),
}));

const mockOnSave = vi.fn<(body: { banner_config: BannerConfig }) => Promise<unknown>>(
  () => Promise.resolve({}),
);

function createQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = createQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  );
}

const BASE_CONFIG: { banner_config: BannerConfig | null } = {
  banner_config: null,
};

const DEFAULT_PROPS = {
  configQueryKey: ['sites', 'site-1', 'config'],
  config: BASE_CONFIG,
  onSave: mockOnSave,
};

/**
 * The sidebar is a single-open accordion with only "Display mode" expanded by
 * default. Click a section header to reveal its controls before asserting.
 */
function expandSection(name: string) {
  fireEvent.click(screen.getByText(name));
}

describe('BannerBuilderTab', () => {
  it('renders the builder with default state', () => {
    renderWithProviders(
      <BannerBuilderTab {...DEFAULT_PROPS} />,
    );

    expect(screen.getByTestId('banner-builder')).toBeInTheDocument();
    expect(screen.getByText('Display mode')).toBeInTheDocument();
    expect(screen.getByText('Theme')).toBeInTheDocument();
    expect(screen.getByText('Layout')).toBeInTheDocument();
    expect(screen.getByText('Live preview')).toBeInTheDocument();
  });

  it('renders all display mode buttons', () => {
    renderWithProviders(
      <BannerBuilderTab {...DEFAULT_PROPS} />,
    );

    expect(screen.getByText('Bottom banner')).toBeInTheDocument();
    expect(screen.getByText('Top banner')).toBeInTheDocument();
    expect(screen.getByText('Overlay (modal)')).toBeInTheDocument();
    expect(screen.getByText('Corner popup')).toBeInTheDocument();
  });

  it('renders the preview iframe', () => {
    renderWithProviders(
      <BannerBuilderTab {...DEFAULT_PROPS} />,
    );

    const preview = screen.getByTestId('banner-preview');
    const iframe = within(preview).getByTitle('Banner preview');
    expect(iframe).toBeInTheDocument();
    expect(iframe.tagName).toBe('IFRAME');
  });

  it('renders viewport toggle buttons', () => {
    renderWithProviders(
      <BannerBuilderTab {...DEFAULT_PROPS} />,
    );

    expect(screen.getByText('Desktop')).toBeInTheDocument();
    expect(screen.getByText('Mobile')).toBeInTheDocument();
  });

  it('toggles mobile viewport width', () => {
    renderWithProviders(
      <BannerBuilderTab {...DEFAULT_PROPS} />,
    );

    const mobileBtn = screen.getByText('Mobile');
    fireEvent.click(mobileBtn);

    const iframe = screen.getByTitle('Banner preview');
    expect(iframe).toHaveStyle({ width: '375px' });
  });

  it('renders button visibility toggles in the Buttons section', () => {
    renderWithProviders(
      <BannerBuilderTab {...DEFAULT_PROPS} />,
    );
    expandSection('Buttons');

    // Reject/Manage toggles now live in each button card's header
    expect(screen.getByLabelText('Show Reject button')).toBeInTheDocument();
    expect(screen.getByLabelText('Show Manage preferences')).toBeInTheDocument();
    expect(screen.getByText('Show close button')).toBeInTheDocument();
  });

  it('toggles the floating preferences button and its position into the saved config', async () => {
    mockOnSave.mockClear();
    renderWithProviders(<BannerBuilderTab {...DEFAULT_PROPS} />);
    expandSection('Buttons');

    const toggle = screen
      .getByText('Show floating preferences button')
      .closest('label')!
      .querySelector('input') as HTMLInputElement;
    expect(toggle.checked).toBe(true);
    expect(screen.getByText('Preferences button position')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Left'));
    fireEvent.click(screen.getByText('Save banner'));

    await waitFor(() => {
      expect(mockOnSave).toHaveBeenCalledWith(
        expect.objectContaining({
          banner_config: expect.objectContaining({
            showPreferencesButton: true,
            preferencesButtonPosition: 'left',
          }),
        }),
      );
    });
  });

  it('hides the position selector and omits position when the button is disabled', async () => {
    mockOnSave.mockClear();
    renderWithProviders(<BannerBuilderTab {...DEFAULT_PROPS} />);
    expandSection('Buttons');

    const toggle = screen
      .getByText('Show floating preferences button')
      .closest('label')!
      .querySelector('input') as HTMLInputElement;
    fireEvent.click(toggle);

    expect(screen.queryByText('Preferences button position')).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('Save banner'));

    await waitFor(() => {
      const body = mockOnSave.mock.calls[0][0];
      expect(body.banner_config.showPreferencesButton).toBe(false);
      expect(body.banner_config.preferencesButtonPosition).toBeUndefined();
    });
  });

  it('renders non-button display toggles in the Layout section', () => {
    renderWithProviders(
      <BannerBuilderTab {...DEFAULT_PROPS} />,
    );
    expandSection('Layout');

    expect(screen.getByText('Show cookie count')).toBeInTheDocument();
    expect(screen.getByText('Show logo')).toBeInTheDocument();
  });

  it('shows logo URL field when logo toggle is enabled', () => {
    renderWithProviders(
      <BannerBuilderTab {...DEFAULT_PROPS} />,
    );
    expandSection('Layout');

    // Logo is off by default — URL field should not be visible
    expect(screen.queryByPlaceholderText('https://example.com/logo.svg')).not.toBeInTheDocument();

    // Enable logo
    const logoCheckbox = screen.getByText('Show logo').closest('label')!.querySelector('input')!;
    fireEvent.click(logoCheckbox);

    expect(screen.getByPlaceholderText('https://example.com/logo.svg')).toBeInTheDocument();
  });

  it('renders font selector', () => {
    renderWithProviders(
      <BannerBuilderTab {...DEFAULT_PROPS} />,
    );
    expandSection('Theme');

    expect(screen.getByText('Font')).toBeInTheDocument();
    expect(screen.getByText('System default')).toBeInTheDocument();
  });

  it('renders save button', () => {
    renderWithProviders(
      <BannerBuilderTab {...DEFAULT_PROPS} />,
    );

    expect(screen.getByText('Save banner')).toBeInTheDocument();
  });

  it('loads existing banner config values', () => {
    const configWithBanner = {
      banner_config: {
        displayMode: 'overlay' as const,
        primaryColour: '#ff0000',
        backgroundColour: '#000000',
        textColour: '#ffffff',
        fontFamily: 'Georgia, serif',
        borderRadius: 12,
        showRejectAll: false,
        showManagePreferences: true,
        showCloseButton: true,
        showLogo: true,
        logoUrl: 'https://example.com/logo.png',
        showCookieCount: true,
      },
    };

    renderWithProviders(
      <BannerBuilderTab {...DEFAULT_PROPS} config={configWithBanner} />,
    );

    // The close button toggle now lives in the Buttons section
    expandSection('Buttons');
    const closeLabel = screen.getByText('Show close button').closest('label')!;
    const closeCheckbox = closeLabel.querySelector('input') as HTMLInputElement;
    expect(closeCheckbox.checked).toBe(true);

    // Logo URL field lives in Layout and should be visible since showLogo is true
    expandSection('Layout');
    expect(screen.getByPlaceholderText('https://example.com/logo.svg')).toBeInTheDocument();
  });

  it('calls save mutation when save button is clicked', async () => {
    mockOnSave.mockClear();

    renderWithProviders(
      <BannerBuilderTab {...DEFAULT_PROPS} />,
    );

    const saveBtn = screen.getByText('Save banner');
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(mockOnSave).toHaveBeenCalledWith(expect.objectContaining({
        banner_config: expect.objectContaining({
          primaryColour: '#2563eb',
          backgroundColour: '#ffffff',
          textColour: '#1a1a2e',
          displayMode: 'bottom_banner',
        }),
      }));
    });
  });

  it('shows a language switcher with configured locales when a siteId is given', async () => {
    renderWithProviders(
      <BannerBuilderTab {...DEFAULT_PROPS} siteId="site-1" />,
    );

    const select = await screen.findByLabelText('Preview language');
    expect(select).toBeInTheDocument();
    expect(within(select).getByRole('option', { name: 'Default (English)' })).toBeInTheDocument();
    expect(within(select).getByRole('option', { name: 'German (de)' })).toBeInTheDocument();
  });

  it('does not show the language switcher without a siteId', () => {
    renderWithProviders(
      <BannerBuilderTab {...DEFAULT_PROPS} />,
    );

    expect(screen.queryByLabelText('Preview language')).not.toBeInTheDocument();
  });

  it('changes display mode when mode button is clicked', () => {
    renderWithProviders(
      <BannerBuilderTab {...DEFAULT_PROPS} />,
    );

    const overlayBtn = screen.getByText('Overlay (modal)');
    fireEvent.click(overlayBtn);

    // Overlay button should now be active (bg-primary)
    expect(overlayBtn.className).toContain('bg-primary');
  });
});
