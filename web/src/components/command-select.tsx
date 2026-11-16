import * as Select from "@radix-ui/react-select";
import { Check, ChevronDown, ChevronUp } from "lucide-react";
import { groupedCommands, type Command } from "../lib/commands";
import { useI18n } from "../lib/i18n";
export function CommandSelect({
  commands,
  value,
  advanced,
  onChange,
}: {
  commands: Command[];
  value: string;
  advanced: boolean;
  onChange: (value: string) => void;
}) {
  const { t } = useI18n();
  return (
    <Select.Root value={value} onValueChange={onChange}>
      <Select.Trigger
        id="operation-command"
        className="command-trigger"
        aria-label={t("Command")}
      >
        <Select.Value />
        <Select.Icon>
          <ChevronDown size={17} />
        </Select.Icon>
      </Select.Trigger>
      <Select.Portal>
        <Select.Content
          position="popper"
          sideOffset={6}
          align="start"
          className="command-menu"
        >
          <Select.ScrollUpButton className="command-scroll">
            <ChevronUp size={16} />
          </Select.ScrollUpButton>
          <Select.Viewport>
            {groupedCommands(commands, advanced).map((group) => (
              <Select.Group key={group.label}>
                <Select.Label className="command-group-label">
                  {t(group.label)}
                </Select.Label>
                {group.commands.map((command) => (
                  <Select.Item
                    className="command-option"
                    key={command.name}
                    value={command.name}
                    textValue={command.name}
                    aria-describedby={`command-desc-${command.name}`}
                  >
                    <span className="command-option-copy">
                      <Select.ItemText>
                        <span className="font-mono">ygg {command.name}</span>
                      </Select.ItemText>
                      <span
                        className="command-description"
                        id={`command-desc-${command.name}`}
                      >
                        {t(command.description)}
                      </span>
                    </span>
                    <Select.ItemIndicator>
                      <Check size={16} />
                    </Select.ItemIndicator>
                  </Select.Item>
                ))}
              </Select.Group>
            ))}
          </Select.Viewport>
          <Select.ScrollDownButton className="command-scroll">
            <ChevronDown size={16} />
          </Select.ScrollDownButton>
        </Select.Content>
      </Select.Portal>
    </Select.Root>
  );
}
