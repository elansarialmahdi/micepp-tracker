import { Check, ChevronDown } from "lucide-react";
import { useId, useRef, useState } from "react";

import { useOutsideClick } from "../hooks/useOutsideClick";

export type SelectOption = {
  value: string;
  label: string;
};

export function CustomSelect({
  id,
  value,
  options,
  onChange,
  ariaLabel,
  disabled = false,
  placeholder = "Sélectionner",
  className = "",
}: {
  id?: string;
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  ariaLabel?: string;
  disabled?: boolean;
  placeholder?: string;
  className?: string;
}) {
  const generatedId = useId();
  const selectId = id ?? generatedId;
  const listId = `${selectId}-options`;
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  useOutsideClick(rootRef, open, () => setOpen(false));
  const selected = options.find((option) => option.value === value);

  return (
    <div className={`custom-select ${className}`.trim()} ref={rootRef}>
      <button
        id={selectId}
        className="custom-select__trigger"
        type="button"
        role="combobox"
        aria-label={ariaLabel}
        aria-expanded={open}
        aria-controls={listId}
        aria-haspopup="listbox"
        disabled={disabled}
        onClick={() => setOpen((current) => !current)}
        onKeyDown={(event) => {
          if (["ArrowDown", "ArrowUp"].includes(event.key)) {
            event.preventDefault();
            setOpen(true);
          }
          if (event.key === "Escape") setOpen(false);
        }}
      >
        <span>{selected?.label ?? placeholder}</span>
        <ChevronDown aria-hidden="true" />
      </button>
      {open && (
        <div className="custom-select__menu" id={listId} role="listbox">
          {options.map((option) => (
            <button
              key={option.value}
              className="custom-select__option"
              type="button"
              role="option"
              aria-selected={option.value === value}
              onClick={() => {
                onChange(option.value);
                setOpen(false);
              }}
            >
              <span>{option.label}</span>
              {option.value === value && <Check aria-hidden="true" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
