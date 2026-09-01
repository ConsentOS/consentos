import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import type { FormEvent } from 'react';

import { COMMON_LOCALES, localeName, TRANSLATION_KEYS } from '../constants/translations';
import type { ConfigSource, TranslationInheritanceResponse } from '../types/api';
import { ResetButton, SourceBadge } from './ConfigSourceBadge';
import { Alert } from './ui/alert';
import { Button } from './ui/button';
import { Card, CardContent } from './ui/card';
import { EmptyState } from './ui/empty-state';
import { FormField } from './ui/form-field';
import { Input } from './ui/input';
import { LoadingState } from './ui/loading-state';
import { Modal } from './ui/modal';
import { Select } from './ui/select';
import { Textarea } from './ui/textarea';

interface TranslationLike {
  id: string;
  locale: string;
  strings: Record<string, string>;
}

interface TranslationsEditorApi {
  list: () => Promise<TranslationLike[]>;
  create: (body: { locale: string; strings: Record<string, string> }) => Promise<TranslationLike>;
  update: (locale: string, body: { strings: Record<string, string> }) => Promise<TranslationLike>;
  remove: (locale: string) => Promise<void>;
}

interface Props {
  /** React Query key for the translations list — also namespaces the inheritance query. */
  queryKey: readonly unknown[];
  api: TranslationsEditorApi;
  /** When provided, the site-level editor shows per-key source badges and reset buttons. */
  getInheritance?: (locale: string) => Promise<TranslationInheritanceResponse>;
  emptyMessage?: string;
}

/** Determine which parent level would provide the value if this override is removed. */
function getParentSource(
  key: string,
  inheritance: TranslationInheritanceResponse | undefined,
): ConfigSource | null {
  if (!inheritance) return null;
  const info = inheritance.keys[key];
  if (!info) return null;
  if (info.group_value != null) return 'group';
  if (info.org_value != null) return 'org';
  return 'system';
}

export default function TranslationsEditor({ queryKey, api, getInheritance, emptyMessage }: Props) {
  const queryClient = useQueryClient();
  const [selectedLocale, setSelectedLocale] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const { data: translations, isLoading } = useQuery({
    queryKey,
    queryFn: api.list,
  });

  const deleteMutation = useMutation({
    mutationFn: (locale: string) => api.remove(locale),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey });
      setSelectedLocale(null);
    },
  });

  if (isLoading) {
    return <LoadingState />;
  }

  const existing = translations ?? [];
  const selected = existing.find((t) => t.locale === selectedLocale);

  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="p-6">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h3 className="font-heading text-sm font-semibold text-foreground">Translations</h3>
              <p className="mt-0.5 text-xs text-text-secondary">
                Manage banner text for different languages. English is the default fallback.
              </p>
            </div>
            <Button onClick={() => setShowCreate(true)}>Add language</Button>
          </div>

          {existing.length === 0 ? (
            <EmptyState
              message={
                emptyMessage ?? 'No translations yet. The banner will use English defaults.'
              }
            />
          ) : (
            <div className="flex flex-wrap gap-2">
              {existing.map((t) => (
                <button
                  key={t.locale}
                  onClick={() => setSelectedLocale(t.locale)}
                  className={`rounded-lg border px-4 py-2 text-sm font-medium transition ${
                    selectedLocale === t.locale
                      ? 'border-copper bg-copper/10 text-copper'
                      : 'border-border text-text-secondary hover:bg-mist'
                  }`}
                >
                  {localeName(t.locale)}
                  <span className="ml-1.5 text-xs text-text-tertiary">{t.locale}</span>
                </button>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {selected && (
        <TranslationEditor
          key={selected.locale}
          queryKey={queryKey}
          api={api}
          translation={selected}
          getInheritance={getInheritance}
          onDelete={() => {
            if (confirm(`Delete ${localeName(selected.locale)} translation?`)) {
              deleteMutation.mutate(selected.locale);
            }
          }}
        />
      )}

      <CreateTranslationModal
        open={showCreate}
        queryKey={queryKey}
        api={api}
        existingLocales={existing.map((t) => t.locale)}
        onClose={() => setShowCreate(false)}
        onCreated={(locale) => {
          setShowCreate(false);
          setSelectedLocale(locale);
        }}
      />
    </div>
  );
}

/* ── Translation editor ──────────────────────────────────────────────── */

function TranslationEditor({
  queryKey,
  api,
  translation,
  getInheritance,
  onDelete,
}: {
  queryKey: readonly unknown[];
  api: TranslationsEditorApi;
  translation: TranslationLike;
  getInheritance?: (locale: string) => Promise<TranslationInheritanceResponse>;
  onDelete: () => void;
}) {
  const queryClient = useQueryClient();
  const [strings, setStrings] = useState<Record<string, string>>(translation.strings);
  const [resetKeys, setResetKeys] = useState<Set<string>>(new Set());
  const [saved, setSaved] = useState(false);

  const { data: inheritance } = useQuery({
    queryKey: [...queryKey, 'inheritance', translation.locale],
    queryFn: () => getInheritance!(translation.locale),
    enabled: !!getInheritance,
  });

  const mutation = useMutation({
    mutationFn: (body: { strings: Record<string, string> }) =>
      api.update(translation.locale, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey });
      if (getInheritance) {
        queryClient.invalidateQueries({ queryKey: [...queryKey, 'inheritance', translation.locale] });
      }
      setResetKeys(new Set());
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    },
  });

  const markReset = (key: string) => {
    setResetKeys((prev) => new Set([...prev, key]));
    setStrings((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    // Resetting a key means removing it from the stored strings dict —
    // not sending null — so the cascade can supply it again.
    const payload = { ...strings };
    for (const key of resetKeys) {
      delete payload[key];
    }
    mutation.mutate({ strings: payload });
  };

  const getSource = (key: string): ConfigSource => inheritance?.keys[key]?.source ?? 'site';

  const filledCount = TRANSLATION_KEYS.filter((k) => strings[k.key]?.trim()).length;

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {inheritance && (
        <div className="rounded-xl border border-dashed border-border bg-surface p-4">
          <p className="text-xs text-text-secondary">
            <strong>Translation cascade:</strong> Organisation defaults
            {inheritance.site_group_id && <>{' → '}Group defaults</>}
            {' → '}<span className="font-semibold">Site translation</span>. Each key is
            resolved independently — fields with a coloured badge are inherited from a higher
            level. Click &ldquo;Reset&rdquo; to remove a site-level override for that key.
          </p>
        </div>
      )}

      <Card>
        <CardContent className="p-6">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h3 className="font-heading text-sm font-semibold text-foreground">
                {localeName(translation.locale)}{' '}
                <span className="font-normal text-text-tertiary">({translation.locale})</span>
              </h3>
              <p className="mt-0.5 text-xs text-text-secondary">
                {filledCount}/{TRANSLATION_KEYS.length} strings translated. Empty strings fall back
                to {inheritance ? 'the parent level, then English' : 'English'}.
              </p>
            </div>
            <button
              type="button"
              onClick={onDelete}
              className="text-xs text-status-error-fg hover:underline"
            >
              Delete language
            </button>
          </div>

          <div className="space-y-4">
            {TRANSLATION_KEYS.map(({ key, label, placeholder, multiline }) => {
              const inherited = inheritance?.keys[key];
              const effectivePlaceholder = inherited?.resolved_value ?? placeholder;
              return (
                <div key={key}>
                  <label className="mb-1 flex items-center text-xs font-medium text-text-secondary">
                    {label}
                    <span className="ml-1 font-mono text-text-tertiary">{key}</span>
                    {inheritance && (
                      <>
                        <SourceBadge source={getSource(key)} field={label} />
                        <ResetButton
                          source={getSource(key)}
                          parentSource={getParentSource(key, inheritance)}
                          onReset={() => markReset(key)}
                        />
                      </>
                    )}
                  </label>
                  {multiline ? (
                    <Textarea
                      value={strings[key] ?? ''}
                      onChange={(e) => setStrings({ ...strings, [key]: e.target.value })}
                      placeholder={effectivePlaceholder}
                      rows={3}
                    />
                  ) : (
                    <Input
                      type="text"
                      value={strings[key] ?? ''}
                      onChange={(e) => setStrings({ ...strings, [key]: e.target.value })}
                      placeholder={effectivePlaceholder}
                    />
                  )}
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      <div className="flex items-center gap-3">
        <Button type="submit" disabled={mutation.isPending}>
          {mutation.isPending ? 'Saving...' : 'Save translation'}
        </Button>
        {resetKeys.size > 0 && (
          <span className="text-xs text-text-secondary">
            {resetKeys.size} key{resetKeys.size > 1 ? 's' : ''} will be reset to inherited
          </span>
        )}
        {saved && <span className="text-sm text-status-success-fg">Saved successfully</span>}
        {mutation.isError && (
          <span className="text-sm text-status-error-fg">Failed to save. Please try again.</span>
        )}
      </div>
    </form>
  );
}

/* ── Create translation modal ────────────────────────────────────────── */

function CreateTranslationModal({
  open,
  queryKey,
  api,
  existingLocales,
  onClose,
  onCreated,
}: {
  open: boolean;
  queryKey: readonly unknown[];
  api: TranslationsEditorApi;
  existingLocales: string[];
  onClose: () => void;
  onCreated: (locale: string) => void;
}) {
  const queryClient = useQueryClient();
  const [locale, setLocale] = useState('');
  const [error, setError] = useState('');

  const availableLocales = COMMON_LOCALES.filter((l) => !existingLocales.includes(l.code));

  const mutation = useMutation({
    mutationFn: () => api.create({ locale, strings: {} }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey });
      onCreated(locale);
    },
    onError: () => {
      setError('Failed to create translation. The locale may already exist.');
    },
  });

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!locale) return;
    setError('');
    mutation.mutate();
  };

  return (
    <Modal open={open} onClose={onClose} title="Add language">
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && <Alert variant="error">{error}</Alert>}
        <FormField label="Language" htmlFor="locale">
          <Select id="locale" required value={locale} onChange={(e) => setLocale(e.target.value)}>
            <option value="">Select a language...</option>
            {availableLocales.map((l) => (
              <option key={l.code} value={l.code}>
                {l.name} ({l.code})
              </option>
            ))}
          </Select>
        </FormField>
        <div className="flex justify-end gap-3 pt-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={mutation.isPending || !locale}>
            {mutation.isPending ? 'Creating...' : 'Add language'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
