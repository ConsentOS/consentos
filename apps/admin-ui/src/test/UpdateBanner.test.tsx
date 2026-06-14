import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import UpdateBanner from '../components/UpdateBanner';
import type { VersionInfo } from '../types/api';

const UPDATE: VersionInfo = { current: '0.2.0', latest: '0.3.0', update_available: true };

afterEach(() => localStorage.clear());

describe('UpdateBanner', () => {
  it('shows the available version and current version when an update exists', () => {
    render(<UpdateBanner info={UPDATE} />);
    expect(screen.getByText(/ConsentOS 0\.3\.0 is available/)).toBeInTheDocument();
    expect(screen.getByText(/you are on 0\.2\.0/)).toBeInTheDocument();
    expect(screen.getByText('Release notes')).toBeInTheDocument();
    expect(screen.getByText('How to upgrade')).toBeInTheDocument();
  });

  it('renders nothing when no update is available', () => {
    const { container } = render(
      <UpdateBanner info={{ current: '0.3.0', latest: '0.3.0', update_available: false }} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when latest is null', () => {
    const { container } = render(
      <UpdateBanner info={{ current: '0.2.0', latest: null, update_available: false }} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('hides after dismissal and records the dismissed version', () => {
    render(<UpdateBanner info={UPDATE} />);
    fireEvent.click(screen.getByLabelText('Dismiss update notice'));
    expect(screen.queryByText(/is available/)).not.toBeInTheDocument();
    expect(localStorage.getItem('consentos:update-dismissed')).toBe('0.3.0');
  });

  it('stays hidden if this version was already dismissed', () => {
    localStorage.setItem('consentos:update-dismissed', '0.3.0');
    const { container } = render(<UpdateBanner info={UPDATE} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('reappears when a newer version than the dismissed one is released', () => {
    localStorage.setItem('consentos:update-dismissed', '0.3.0');
    render(<UpdateBanner info={{ current: '0.2.0', latest: '0.4.0', update_available: true }} />);
    expect(screen.getByText(/ConsentOS 0\.4\.0 is available/)).toBeInTheDocument();
  });
});
