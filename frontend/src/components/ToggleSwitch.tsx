import { Check } from "lucide-react";
import { forwardRef, type InputHTMLAttributes } from "react";

type ToggleSwitchProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & {
  className?: string;
};

export const ToggleSwitch = forwardRef<HTMLInputElement, ToggleSwitchProps>(
  function ToggleSwitch({ className = "", ...inputProps }, ref) {
    return (
      <label className={`toggle-switch${className ? ` ${className}` : ""}`}>
        <input ref={ref} type="checkbox" {...inputProps} />
        <span className="toggle-switch__track" aria-hidden="true">
          <Check />
        </span>
      </label>
    );
  },
);
