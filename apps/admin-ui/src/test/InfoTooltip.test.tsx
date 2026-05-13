import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { InfoTooltip } from '../components/ui/info-tooltip';

describe('InfoTooltip', () => {
  it('hides the content by default', () => {
    render(<InfoTooltip content="Helpful text" />);
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
  });

  it('shows the content on hover and hides on leave', () => {
    render(<InfoTooltip content="Helpful text" />);
    const trigger = screen.getByRole('button', { name: 'More information' });

    fireEvent.mouseEnter(trigger);
    expect(screen.getByRole('tooltip')).toHaveTextContent('Helpful text');

    fireEvent.mouseLeave(trigger);
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
  });

  it('shows the content on focus and hides on blur', () => {
    render(<InfoTooltip content="Helpful text" />);
    const trigger = screen.getByRole('button', { name: 'More information' });

    fireEvent.focus(trigger);
    expect(screen.getByRole('tooltip')).toBeInTheDocument();

    fireEvent.blur(trigger);
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
  });

  it('uses a custom aria-label when provided', () => {
    render(<InfoTooltip content="Helpful text" label="Why does this matter?" />);
    expect(
      screen.getByRole('button', { name: 'Why does this matter?' }),
    ).toBeInTheDocument();
  });

  it('wires aria-describedby to the visible tooltip', () => {
    render(<InfoTooltip content="Helpful text" />);
    const trigger = screen.getByRole('button', { name: 'More information' });
    fireEvent.focus(trigger);

    const tooltip = screen.getByRole('tooltip');
    expect(trigger.getAttribute('aria-describedby')).toBe(tooltip.id);
  });
});
