import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { createSiteGroup, deleteSiteGroup, listSiteGroups } from '../api/site-groups';
import { listSites, updateSite } from '../api/sites';
import CreateSiteModal from '../components/CreateSiteModal';
import { Button } from '../components/ui/button.tsx';
import { Badge } from '../components/ui/badge.tsx';
import { Modal } from '../components/ui/modal.tsx';
import { FormField } from '../components/ui/form-field.tsx';
import { Input } from '../components/ui/input.tsx';
import { Alert } from '../components/ui/alert.tsx';
import { EmptyState } from '../components/ui/empty-state.tsx';
import { LoadingState } from '../components/ui/loading-state.tsx';
import type { Site, SiteGroup } from '../types/api';

export default function SitesPage() {
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [showCreateGroup, setShowCreateGroup] = useState(false);
  const [newGroupName, setNewGroupName] = useState('');
  const [createGroupError, setCreateGroupError] = useState('');
  const { data: sites, isLoading: sitesLoading, error: sitesError } = useQuery({
    queryKey: ['sites'],
    queryFn: listSites,
  });

  const { data: groups, isLoading: groupsLoading } = useQuery({
    queryKey: ['site-groups'],
    queryFn: listSiteGroups,
  });

  const createGroupMutation = useMutation({
    mutationFn: createSiteGroup,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['site-groups'] });
      setShowCreateGroup(false);
      setNewGroupName('');
      setCreateGroupError('');
    },
    onError: () => {
      setCreateGroupError('Failed to create group. Name may already exist.');
    },
  });

  const deleteGroupMutation = useMutation({
    mutationFn: deleteSiteGroup,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['site-groups'] });
      queryClient.invalidateQueries({ queryKey: ['sites'] });
    },
  });

  const assignGroupMutation = useMutation({
    mutationFn: ({ siteId, groupId }: { siteId: string; groupId: string | null }) =>
      updateSite(siteId, { site_group_id: groupId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sites'] });
      queryClient.invalidateQueries({ queryKey: ['site-groups'] });
    },
  });

  // Group sites by site_group_id
  const { groupedSites, ungroupedSites } = useMemo(() => {
    if (!sites) return { groupedSites: new Map<string, Site[]>(), ungroupedSites: [] };
    const grouped = new Map<string, Site[]>();
    const ungrouped: Site[] = [];
    for (const site of sites) {
      if (site.site_group_id) {
        const list = grouped.get(site.site_group_id) ?? [];
        list.push(site);
        grouped.set(site.site_group_id, list);
      } else {
        ungrouped.push(site);
      }
    }
    return { groupedSites: grouped, ungroupedSites: ungrouped };
  }, [sites]);

  const isLoading = sitesLoading || groupsLoading;

  return (
    <div>
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="font-heading text-4xl font-semibold tracking-tight text-foreground">Sites</h1>
          <p className="mt-1 text-sm text-text-secondary">
            Manage your consent-enabled websites
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setShowCreateGroup(true)}>
            New group
          </Button>
          <Button onClick={() => setShowCreate(true)}>
            Add site
          </Button>
        </div>
      </div>

      {isLoading && <LoadingState />}

      {sitesError && (
        <Alert variant="error">
          Failed to load sites. Please try again.
        </Alert>
      )}

      {!isLoading && sites && sites.length === 0 && (!groups || groups.length === 0) && (
        <EmptyState message="No sites yet. Add your first site to get started." />
      )}

      {!isLoading && (
        <div className="space-y-6">
          {/* Render each group */}
          {groups?.map((group) => (
            <GroupSection
              key={group.id}
              group={group}
              sites={groupedSites.get(group.id) ?? []}
              allGroups={groups}
              groupId={group.id}
              onDelete={() => {
                if (confirm(`Delete group "${group.name}"? Sites will become ungrouped.`)) {
                  deleteGroupMutation.mutate(group.id);
                }
              }}
              onRemoveSite={(siteId) =>
                assignGroupMutation.mutate({ siteId, groupId: null })
              }
              onMoveSite={(siteId, groupId) =>
                assignGroupMutation.mutate({ siteId, groupId })
              }
            />
          ))}

          {/* Ungrouped sites */}
          {ungroupedSites.length > 0 && (
            <div>
              {groups && groups.length > 0 && (
                <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-text-secondary">
                  Ungrouped sites
                </h2>
              )}
              <SiteTable
                sites={ungroupedSites}
                groups={groups ?? []}
                onAssignGroup={(siteId, groupId) =>
                  assignGroupMutation.mutate({ siteId, groupId })
                }
              />
            </div>
          )}
        </div>
      )}

      {showCreate && <CreateSiteModal onClose={() => setShowCreate(false)} />}

      <Modal
        open={showCreateGroup}
        onClose={() => {
          setShowCreateGroup(false);
          setNewGroupName('');
          setCreateGroupError('');
        }}
        title="Create site group"
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            createGroupMutation.mutate({ name: newGroupName });
          }}
          className="space-y-4"
        >
          {createGroupError && <Alert variant="error">{createGroupError}</Alert>}

          <FormField label="Group name">
            <Input
              id="group-name"
              type="text"
              required
              value={newGroupName}
              onChange={(e) => setNewGroupName(e.target.value)}
              placeholder="e.g. EU Storefront"
            />
          </FormField>

          <div className="flex justify-end gap-3 pt-2">
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setShowCreateGroup(false);
                setNewGroupName('');
                setCreateGroupError('');
              }}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={createGroupMutation.isPending}>
              {createGroupMutation.isPending ? 'Creating...' : 'Create group'}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

/* ── Group section component ───────────────────────────────────────── */

function GroupSection({
  group,
  sites,
  allGroups,
  groupId,
  onDelete,
  onRemoveSite,
  onMoveSite,
}: {
  group: SiteGroup;
  sites: Site[];
  allGroups: SiteGroup[];
  groupId: string;
  onDelete: () => void;
  onRemoveSite: (siteId: string) => void;
  onMoveSite: (siteId: string, groupId: string) => void;
}) {
  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="font-heading text-sm font-semibold text-foreground">{group.name}</h2>
          <Badge variant="neutral">
            {sites.length} {sites.length === 1 ? 'site' : 'sites'}
          </Badge>
        </div>
        <div className="flex items-center gap-3">
          <Link
            to={`/groups/${groupId}`}
            className="text-xs font-medium text-copper hover:text-copper/80"
          >
            Group defaults
          </Link>
          <button
            onClick={onDelete}
            className="text-xs text-status-error-fg hover:text-status-error-fg/80"
          >
            Delete group
          </button>
        </div>
      </div>
      {sites.length > 0 ? (
        <SiteTable
          sites={sites}
          groups={allGroups}
          currentGroupId={group.id}
          onRemoveFromGroup={onRemoveSite}
          onAssignGroup={onMoveSite}
        />
      ) : (
        <EmptyState message="No sites in this group yet" />
      )}
    </div>
  );
}

/* ── Shared site table component ───────────────────────────────────── */

function SiteTable({
  sites,
  groups,
  currentGroupId,
  onRemoveFromGroup,
  onAssignGroup,
}: {
  sites: Site[];
  groups: SiteGroup[];
  currentGroupId?: string;
  onRemoveFromGroup?: (siteId: string) => void;
  onAssignGroup?: (siteId: string, groupId: string) => void;
}) {
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card shadow-sm">
      {/* Desktop table */}
      <div className="hidden overflow-x-auto sm:block">
        <table className="w-full">
          <thead>
            <tr className="border-b border-border bg-surface text-left text-xs font-medium uppercase tracking-wide text-text-secondary">
              <th className="px-4 py-3 lg:px-6">Domain</th>
              <th className="px-4 py-3 lg:px-6">Name</th>
              <th className="px-4 py-3 lg:px-6">Status</th>
              <th className="hidden px-4 py-3 md:table-cell lg:px-6">Created</th>
              <th className="px-4 py-3 lg:px-6">Group</th>
              <th className="px-4 py-3 lg:px-6"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {sites.map((site: Site) => (
              <tr key={site.id} className="transition hover:bg-mist">
                <td className="px-4 py-3 text-sm font-medium text-foreground lg:px-6">
                  {site.domain}
                </td>
                <td className="px-4 py-3 text-sm text-text-secondary lg:px-6">
                  {site.display_name ?? site.name ?? '-'}
                </td>
                <td className="px-4 py-3 lg:px-6">
                  <Badge variant={site.is_active ? 'success' : 'neutral'}>
                    {site.is_active ? 'Active' : 'Inactive'}
                  </Badge>
                </td>
                <td className="hidden px-4 py-3 text-sm text-text-secondary md:table-cell lg:px-6">
                  {new Date(site.created_at).toLocaleDateString()}
                </td>
                <td className="px-4 py-3 lg:px-6">
                  <GroupAssigner
                    site={site}
                    groups={groups}
                    currentGroupId={currentGroupId}
                    onRemove={onRemoveFromGroup}
                    onAssign={onAssignGroup}
                  />
                </td>
                <td className="px-4 py-3 text-right lg:px-6">
                  <Link
                    to={`/sites/${site.id}`}
                    className="text-sm font-medium text-copper hover:text-copper/80"
                  >
                    Manage
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile card layout */}
      <div className="divide-y divide-border sm:hidden">
        {sites.map((site: Site) => (
          <div key={site.id} className="p-4">
            <div className="flex items-start justify-between">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-foreground">{site.domain}</p>
                <p className="mt-0.5 text-xs text-text-secondary">
                  {site.display_name ?? site.name ?? '-'}
                </p>
              </div>
              <Badge variant={site.is_active ? 'success' : 'neutral'} className="ml-2 shrink-0">
                {site.is_active ? 'Active' : 'Inactive'}
              </Badge>
            </div>
            <div className="mt-3 flex items-center justify-between">
              <GroupAssigner
                site={site}
                groups={groups}
                currentGroupId={currentGroupId}
                onRemove={onRemoveFromGroup}
                onAssign={onAssignGroup}
              />
              <Link
                to={`/sites/${site.id}`}
                className="text-sm font-medium text-copper hover:text-copper/80"
              >
                Manage
              </Link>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── Group assigner inline component ─────────────────────────────── */

function GroupAssigner({
  site,
  groups,
  currentGroupId,
  onRemove,
  onAssign,
}: {
  site: Site;
  groups: SiteGroup[];
  currentGroupId?: string;
  onRemove?: (siteId: string) => void;
  onAssign?: (siteId: string, groupId: string) => void;
}) {
  // Available groups to move to (exclude current group)
  const otherGroups = groups.filter((g) => g.id !== currentGroupId);

  if (currentGroupId && onRemove) {
    // Site is in a group — show remove + move options
    return (
      <select
        value=""
        onChange={(e) => {
          const val = e.target.value;
          if (val === '__remove__') {
            onRemove(site.id);
          } else if (val && onAssign) {
            onAssign(site.id, val);
          }
        }}
        className="rounded-md border border-border px-2 py-1 text-xs text-text-secondary outline-none focus:border-copper"
      >
        <option value="" disabled>
          Move...
        </option>
        <option value="__remove__">Remove from group</option>
        {otherGroups.map((g) => (
          <option key={g.id} value={g.id}>
            Move to {g.name}
          </option>
        ))}
      </select>
    );
  }

  if (!currentGroupId && groups.length > 0 && onAssign) {
    // Site is ungrouped — show assign options
    return (
      <select
        value=""
        onChange={(e) => {
          if (e.target.value && onAssign) {
            onAssign(site.id, e.target.value);
          }
        }}
        className="rounded-md border border-border px-2 py-1 text-xs text-text-secondary outline-none focus:border-copper"
      >
        <option value="" disabled>
          Add to group...
        </option>
        {groups.map((g) => (
          <option key={g.id} value={g.id}>
            {g.name}
          </option>
        ))}
      </select>
    );
  }

  return <span className="text-xs text-text-tertiary">&mdash;</span>;
}
