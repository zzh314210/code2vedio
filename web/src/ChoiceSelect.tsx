import {Children, isValidElement, type ReactNode} from 'react';
import {Select, SelectContent, SelectItem, SelectTrigger, SelectValue} from '@/components/ui/select';

type Option = {value: string; label: ReactNode; disabled?: boolean};
// Share the existing Radix menu with ordinary form fields, including empty values.
export default function ChoiceSelect({value='', onChange, children, disabled, id, 'aria-label': label}: {
  value?: string; onChange: (value: string) => void; children: ReactNode;
  disabled?: boolean; id?: string; 'aria-label': string;
}) {
  const options: Option[] = [];
  Children.forEach(children, child => {
    if (isValidElement<{value: string; children: ReactNode; disabled?: boolean}>(child))
      options.push({value: String(child.props.value), label: child.props.children, disabled: child.props.disabled});
  });
  const selected = options.find(option => option.value === value);
  return <Select value={selected ? 'option:' + value : ''} onValueChange={next => onChange(next.slice(7))} disabled={disabled}>
    <SelectTrigger id={id} aria-label={label} className="choice-select-trigger"><SelectValue placeholder="请选择"/></SelectTrigger>
    <SelectContent className="choice-select-menu" sideOffset={5} collisionPadding={12}>
      {options.map(option => <SelectItem key={option.value} value={'option:' + option.value} disabled={option.disabled} className="choice-select-option">{option.label}</SelectItem>)}
    </SelectContent>
  </Select>;
}
