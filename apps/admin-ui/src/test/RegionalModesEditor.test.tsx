import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import RegionalModesEditor from '../components/RegionalModesEditor';

describe('RegionalModesEditor', () => {
  it('renders empty-state copy when value is null', () => {
    render(<RegionalModesEditor value={null} onChange={vi.fn()} />);
    expect(screen.getByText(/No regional overrides/)).toBeInTheDocument();
    expect(screen.queryByLabelText('Region code')).not.toBeInTheDocument();
  });

  it('renders one row per entry in value', () => {
    render(
      <RegionalModesEditor
        value={{ 'US-CA': 'opt_out', GB: 'opt_in' }}
        onChange={vi.fn()}
      />,
    );
    const codes = screen.getAllByLabelText('Region code') as HTMLInputElement[];
    expect(codes.map((c) => c.value).sort()).toEqual(['GB', 'US-CA']);
  });

  it('emits the new map when a row is added and a code is typed', () => {
    const onChange = vi.fn();
    render(<RegionalModesEditor value={null} onChange={onChange} />);

    fireEvent.click(screen.getByText('+ Add region'));
    fireEvent.change(screen.getByLabelText('Region code'), {
      target: { value: 'US-CA' },
    });

    expect(onChange).toHaveBeenLastCalledWith({ 'US-CA': 'opt_in' });
  });

  it('emits null when the last row is removed', () => {
    const onChange = vi.fn();
    render(
      <RegionalModesEditor
        value={{ 'US-CA': 'opt_out' }}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByLabelText('Remove US-CA'));
    expect(onChange).toHaveBeenLastCalledWith(null);
  });

  it('updates the blocking mode for an existing row', () => {
    const onChange = vi.fn();
    render(
      <RegionalModesEditor
        value={{ 'US-CA': 'opt_in' }}
        onChange={onChange}
      />,
    );
    fireEvent.change(screen.getByLabelText('Blocking mode'), {
      target: { value: 'opt_out' },
    });
    expect(onChange).toHaveBeenLastCalledWith({ 'US-CA': 'opt_out' });
  });

  it('warns when the same region code is used twice', () => {
    render(<RegionalModesEditor value={null} onChange={vi.fn()} />);
    fireEvent.click(screen.getByText('+ Add region'));
    fireEvent.click(screen.getByText('+ Add region'));
    const codes = screen.getAllByLabelText('Region code');
    fireEvent.change(codes[0], { target: { value: 'GB' } });
    fireEvent.change(codes[1], { target: { value: 'GB' } });
    expect(screen.getByText(/Duplicate region code/)).toBeInTheDocument();
  });
});
