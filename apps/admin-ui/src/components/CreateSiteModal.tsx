import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import type { FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';

import { listSiteGroups } from '../api/site-groups';
import { createSite } from '../api/sites';
import { trackFeatureUsage } from '../services/analytics';
import { Modal } from './ui/modal.tsx';
import { FormField } from './ui/form-field.tsx';
import { Input } from './ui/input.tsx';
import { Select } from './ui/select.tsx';
import { Button } from './ui/button.tsx';
import { Alert } from './ui/alert.tsx';

interface Props {
  onClose: () => void;
  defaultGroupId?: string;
}

export default function CreateSiteModal({ onClose, defaultGroupId }: Props) {
  return (
    <Modal open={true} onClose={onClose} title="Add site">
      <CreateSiteForm onDone={onClose} onCancel={onClose} defaultGroupId={defaultGroupId} />
    </Modal>
  );
}

interface FormProps {
  /** Called after the site is created, before opening it. */
  onDone?: () => void;
  /** Shows a Cancel button that calls this. */
  onCancel?: () => void;
  defaultGroupId?: string;
}

/** Adds a site, then opens it on its setup checklist. */
export function CreateSiteForm({ onDone, onCancel, defaultGroupId }: FormProps) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [domain, setDomain] = useState('');
  const [name, setName] = useState('');
  const [groupId, setGroupId] = useState(defaultGroupId ?? '');
  const [error, setError] = useState('');

  const { data: groups } = useQuery({
    queryKey: ['site-groups'],
    queryFn: listSiteGroups,
  });

  const mutation = useMutation({
    mutationFn: createSite,
    onSuccess: (site) => {
      queryClient.invalidateQueries({ queryKey: ['sites'] });
      queryClient.invalidateQueries({ queryKey: ['site-groups'] });
      trackFeatureUsage('site', 'create');
      onDone?.();
      // Straight to the new site, where its setup checklist starts.
      navigate(`/sites/${site.id}`);
    },
    onError: () => {
      setError('Failed to create site. Check the domain is unique.');
    },
  });

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    setError('');
    mutation.mutate({
      domain,
      display_name: name || domain,
      site_group_id: groupId || undefined,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {error && <Alert variant="error">{error}</Alert>}

      <FormField label="Domain">
        <Input
          id="domain"
          type="text"
          required
          value={domain}
          onChange={(e) => setDomain(e.target.value)}
          placeholder="example.com"
        />
      </FormField>

      <FormField label="Display name (optional)">
        <Input
          id="name"
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="My Website"
        />
      </FormField>

      {groups && groups.length > 0 && (
        <FormField label="Site group (optional)">
          <Select
            id="group"
            value={groupId}
            onChange={(e) => setGroupId(e.target.value)}
          >
            <option value="">No group</option>
            {groups.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
          </Select>
        </FormField>
      )}

      <p className="text-xs text-text-secondary">
        We'll start scanning your site for cookies as soon as it's added.
      </p>

      <div className="flex justify-end gap-3 pt-2">
        {onCancel && (
          <Button type="button" variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        )}
        <Button type="submit" disabled={mutation.isPending}>
          {mutation.isPending ? 'Creating...' : 'Create site'}
        </Button>
      </div>
    </form>
  );
}
