import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import type { FormEvent } from 'react';

import { changePassword, getProfile, updateProfile } from '../api/auth';
import { Alert } from '../components/ui/alert';
import { Button } from '../components/ui/button';
import { Card } from '../components/ui/card';
import { FormField } from '../components/ui/form-field';
import { Input } from '../components/ui/input';

export default function AccountPage() {
  const queryClient = useQueryClient();

  const { data: profile, isLoading } = useQuery({
    queryKey: ['profile'],
    queryFn: getProfile,
  });

  // Profile form
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [profileInit, setProfileInit] = useState(false);
  const [profileSaved, setProfileSaved] = useState(false);

  if (profile && !profileInit) {
    setEmail(profile.email);
    setFullName(profile.full_name);
    setProfileInit(true);
  }

  const profileMutation = useMutation({
    mutationFn: (body: { email?: string; full_name?: string }) => updateProfile(body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['profile'] });
      setProfileSaved(true);
      setTimeout(() => setProfileSaved(false), 2000);
    },
  });

  const handleProfileSubmit = (e: FormEvent) => {
    e.preventDefault();
    const body: { email?: string; full_name?: string } = {};
    if (email !== profile?.email) body.email = email;
    if (fullName !== profile?.full_name) body.full_name = fullName;
    if (Object.keys(body).length === 0) return;
    profileMutation.mutate(body);
  };

  // Password form
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordSaved, setPasswordSaved] = useState(false);
  const [passwordError, setPasswordError] = useState('');

  const passwordMutation = useMutation({
    mutationFn: (body: { current_password: string; new_password: string }) => changePassword(body),
    onSuccess: () => {
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      setPasswordError('');
      setPasswordSaved(true);
      setTimeout(() => setPasswordSaved(false), 2000);
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      setPasswordError(err.response?.data?.detail ?? 'Failed to change password');
    },
  });

  const handlePasswordSubmit = (e: FormEvent) => {
    e.preventDefault();
    setPasswordError('');
    if (newPassword.length < 8) {
      setPasswordError('Password must be at least 8 characters');
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordError('Passwords do not match');
      return;
    }
    passwordMutation.mutate({
      current_password: currentPassword,
      new_password: newPassword,
    });
  };

  if (isLoading) {
    return <div className="py-12 text-center text-sm text-text-secondary">Loading...</div>;
  }

  return (
    <div className="mx-auto max-w-xl">
      <div className="mb-6">
        <h1 className="font-heading text-4xl font-semibold tracking-tight text-foreground">Account</h1>
        <p className="mt-1 text-sm text-text-secondary">Manage your profile and password.</p>
      </div>

      {/* Profile */}
      <form onSubmit={handleProfileSubmit} className="mb-6">
        <Card className="p-6">
          <h3 className="font-heading mb-4 text-sm font-semibold text-foreground">Profile</h3>
          <div className="space-y-4">
            <FormField label="Email">
              <Input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </FormField>
            <FormField label="Display name">
              <Input
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                required
              />
            </FormField>
          </div>
          {profileSaved && <Alert variant="success" className="mt-4">Profile updated.</Alert>}
          {profileMutation.isError && (
            <Alert variant="error" className="mt-4">
              {(profileMutation.error as Error & { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Failed to update profile'}
            </Alert>
          )}
          <div className="mt-4">
            <Button type="submit" disabled={profileMutation.isPending}>
              {profileMutation.isPending ? 'Saving...' : 'Save profile'}
            </Button>
          </div>
        </Card>
      </form>

      {/* Password */}
      <form onSubmit={handlePasswordSubmit}>
        <Card className="p-6">
          <h3 className="font-heading mb-4 text-sm font-semibold text-foreground">Change password</h3>
          <div className="space-y-4">
            <FormField label="Current password">
              <Input
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                required
              />
            </FormField>
            <FormField label="New password">
              <Input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
                minLength={8}
              />
            </FormField>
            <FormField label="Confirm new password">
              <Input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                minLength={8}
              />
            </FormField>
          </div>
          {passwordSaved && <Alert variant="success" className="mt-4">Password changed.</Alert>}
          {passwordError && <Alert variant="error" className="mt-4">{passwordError}</Alert>}
          <div className="mt-4">
            <Button type="submit" disabled={passwordMutation.isPending}>
              {passwordMutation.isPending ? 'Changing...' : 'Change password'}
            </Button>
          </div>
        </Card>
      </form>
    </div>
  );
}
