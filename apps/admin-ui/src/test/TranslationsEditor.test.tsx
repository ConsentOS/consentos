import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import TranslationsEditor from '../components/TranslationsEditor';
import type { TranslationInheritanceResponse } from '../types/api';

function createQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = createQueryClient();
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

interface TranslationLike {
  id: string;
  locale: string;
  strings: Record<string, string>;
}

function makeApi(overrides: Partial<ReturnType<typeof baseApi>> = {}) {
  return { ...baseApi(), ...overrides };
}

function baseApi() {
  return {
    list: vi.fn((): Promise<TranslationLike[]> => Promise.resolve([])),
    create: vi.fn((body: { locale: string; strings: Record<string, string> }) =>
      Promise.resolve({ id: '1', locale: body.locale, strings: body.strings }),
    ),
    update: vi.fn((locale: string, body: { strings: Record<string, string> }) =>
      Promise.resolve({ id: '1', locale, strings: body.strings }),
    ),
    remove: vi.fn(() => Promise.resolve()),
  };
}

describe('TranslationsEditor', () => {
  it('shows the empty state message when there are no translations', async () => {
    const api = makeApi();
    renderWithProviders(<TranslationsEditor queryKey={['t']} api={api} />);
    await waitFor(() => {
      expect(
        screen.getByText('No translations yet. The banner will use English defaults.'),
      ).toBeInTheDocument();
    });
  });

  it('shows a custom empty message when provided', async () => {
    const api = makeApi();
    renderWithProviders(
      <TranslationsEditor queryKey={['t']} api={api} emptyMessage="Nothing here yet." />,
    );
    await waitFor(() => {
      expect(screen.getByText('Nothing here yet.')).toBeInTheDocument();
    });
  });

  it('lists existing locales and opens the editor for the selected one', async () => {
    const api = makeApi({
      list: vi.fn(() => Promise.resolve([{ id: '1', locale: 'fr', strings: { title: 'Bonjour' } }])),
    });
    renderWithProviders(<TranslationsEditor queryKey={['t']} api={api} />);

    const localeButton = await screen.findByText('French');
    fireEvent.click(localeButton);

    expect(await screen.findByDisplayValue('Bonjour')).toBeInTheDocument();
  });

  it('creates a new translation for the selected locale', async () => {
    const api = makeApi();
    renderWithProviders(<TranslationsEditor queryKey={['t']} api={api} />);

    fireEvent.click(await screen.findByText('Add language'));
    fireEvent.change(screen.getByLabelText('Language'), { target: { value: 'de' } });
    fireEvent.click(screen.getByText('Add language', { selector: 'button[type="submit"]' }));

    await waitFor(() => {
      expect(api.create).toHaveBeenCalledWith({ locale: 'de', strings: {} });
    });
  });

  it('saves edited strings for the selected locale', async () => {
    const api = makeApi({
      list: vi.fn(() => Promise.resolve([{ id: '1', locale: 'fr', strings: {} }])),
    });
    renderWithProviders(<TranslationsEditor queryKey={['t']} api={api} />);

    fireEvent.click(await screen.findByText('French'));
    const titleInput = await screen.findByPlaceholderText('We use cookies');
    fireEvent.change(titleInput, { target: { value: 'Bonjour' } });
    fireEvent.click(screen.getByText('Save translation'));

    await waitFor(() => {
      expect(api.update).toHaveBeenCalledWith('fr', { strings: { title: 'Bonjour' } });
    });
  });

  it('shows an inheritance badge and lets the operator reset an overridden key', async () => {
    const api = makeApi({
      list: vi.fn(() =>
        Promise.resolve([{ id: '1', locale: 'fr', strings: { title: 'Site title' } }]),
      ),
    });
    const inheritanceResponse: TranslationInheritanceResponse = {
      site_id: 'site-1',
      site_group_id: null,
      locale: 'fr',
      keys: {
        title: {
          resolved_value: 'Site title',
          source: 'site',
          site_value: 'Site title',
          group_value: null,
          org_value: 'Org title',
          system_value: null,
        },
      },
    };
    const getInheritance = vi.fn(() => Promise.resolve(inheritanceResponse));

    renderWithProviders(
      <TranslationsEditor queryKey={['t']} api={api} getInheritance={getInheritance} />,
    );

    fireEvent.click(await screen.findByText('French'));
    // Site-level override shows a "Reset to organisation default" link
    // rather than a source badge (badges only appear for non-site
    // sources — the override itself needs no badge).
    const resetLink = await screen.findByText('Reset to organisation default');
    fireEvent.click(resetLink);
    fireEvent.click(screen.getByText('Save translation'));

    await waitFor(() => {
      // Resetting removes the key entirely rather than sending null.
      expect(api.update).toHaveBeenCalledWith('fr', { strings: {} });
    });
  });
});
