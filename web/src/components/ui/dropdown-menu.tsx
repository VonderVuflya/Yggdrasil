import * as React from "react";
import * as Menu from "@radix-ui/react-dropdown-menu";
import { Check } from "lucide-react";
import { cn } from "../../lib/utils";
export const DropdownMenu = Menu.Root;
export const DropdownMenuTrigger = Menu.Trigger;
export const DropdownMenuRadioGroup = Menu.RadioGroup;
export const DropdownMenuContent = React.forwardRef<
  React.ElementRef<typeof Menu.Content>,
  React.ComponentPropsWithoutRef<typeof Menu.Content>
>(({ className, sideOffset = 8, ...props }, ref) => (
  <Menu.Portal>
    <Menu.Content
      ref={ref}
      sideOffset={sideOffset}
      className={cn(
        "z-50 min-w-48 rounded-xl border border-border bg-card p-1.5 text-foreground shadow-xl outline-none",
        className,
      )}
      {...props}
    />
  </Menu.Portal>
));
export const DropdownMenuRadioItem = React.forwardRef<
  React.ElementRef<typeof Menu.RadioItem>,
  React.ComponentPropsWithoutRef<typeof Menu.RadioItem>
>(({ className, children, ...props }, ref) => (
  <Menu.RadioItem
    ref={ref}
    className={cn(
      "relative flex min-h-11 cursor-pointer select-none items-center gap-3 rounded-lg py-2 pl-3 pr-9 text-sm outline-none focus:bg-secondary data-[state=checked]:bg-secondary/60",
      className,
    )}
    {...props}
  >
    {children}
    <span className="absolute right-3 flex size-4 items-center justify-center">
      <Menu.ItemIndicator>
        <Check size={15} />
      </Menu.ItemIndicator>
    </span>
  </Menu.RadioItem>
));
