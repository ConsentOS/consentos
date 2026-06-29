import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AxiosError } from 'axios';
import { useState } from 'react';
import type { FormEvent } from 'react';

import { createCookie, listCategories } from '../api/cookies';
import { trackFeatureUsage } from '../services/analytics';
import type { CookieCategory } from '../types/api';
import { Alert } from './ui/alert.tsx';
import { Button } from './ui/button.tsx';
import { FormField } from './ui/form-field.tsx';
import { Input } from './ui/input.tsx';
import { Modal } from './ui/modal.tsx';
import { Select } from './ui/select.tsx';
import { Textarea } from './ui/textarea.tsx';

interface Props {
  siteId: string;
  onClose: () => void;
}

const STORAGE_TYPES: { value: string; label: string }[] = [
  { value: 'cookie', label: 'Cookie' },
  { value: 'local_storage', label: 'Local storage' },
  { value: 'session_storage', label: 'Session storage' },
  { value: 'indexed_db', label: 'IndexedDB' },
];

export default function AddCookieModal({ siteId, onClose }: Props) {
  const queryClient = useQueryClient();
  const [name, setName] = useState('');
  const [domain, setDomain] = useState('');
  const [storageType, setStorageType] = useState('cookie');
  const [categoryId, setCategoryId] = useState('');
  const [vendor, setVendor] = useState('');
  const [description, setDescription] = useState('');
  const [error, setError] = useState('');

  const { data: categories } = useQuery({
    queryKey: ['cookie-categories'],
    queryFn: listCategories,
  });

  const mutation = useMutation({
    mutationFn: () =>
      createCookie(siteId, {
        name: name.trim(),
        domain: domain.trim(),
        storage_type: storageType,
        category_id: categoryId || null,
        vendor: vendor.trim() || null,
        description: description.trim() || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cookies', siteId] });
      queryClient.invalidateQueries({ queryKey: ['cookies', siteId, 'summary'] });
      trackFeatureUsage('cookie', 'manual_add', { site_id: siteId });
      onClose();
    },
    onError: (err: unknown) => {
      const detail =
        err instanceof AxiosError ? (err.response?.data as { detail?: string })?.detail : undefined;
      setError(detail ?? 'Failed to add cookie. It may already exist for this site.');
    },
  });

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    setError('');
    mutation.mutate();
  };

  return (
    <Modal open={true} onClose={onClose} title="Add cookie">
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && <Alert variant="error">{error}</Alert>}

        <FormField label="Name">
          <Input
            id="cookie-name"
            type="text"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="_ga"
          />
        </FormField>

        <FormField label="Domain">
          <Input
            id="cookie-domain"
            type="text"
            required
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            placeholder=".example.com"
          />
        </FormField>

        <FormField label="Storage type">
          <Select
            id="cookie-storage-type"
            value={storageType}
            onChange={(e) => setStorageType(e.target.value)}
          >
            {STORAGE_TYPES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </Select>
        </FormField>

        <FormField label="Category (optional)">
          <Select
            id="cookie-category"
            value={categoryId}
            onChange={(e) => setCategoryId(e.target.value)}
          >
            <option value="">Uncategorised</option>
            {(categories ?? []).map((cat: CookieCategory) => (
              <option key={cat.id} value={cat.id}>
                {cat.name}
              </option>
            ))}
          </Select>
        </FormField>

        <FormField label="Vendor (optional)">
          <Input
            id="cookie-vendor"
            type="text"
            value={vendor}
            onChange={(e) => setVendor(e.target.value)}
            placeholder="Google"
          />
        </FormField>

        <FormField label="Description (optional)">
          <Textarea
            id="cookie-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What this cookie is used for"
          />
        </FormField>

        <div className="flex justify-end gap-3 pt-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? 'Adding...' : 'Add cookie'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
