export interface Command {
  name: string;
  description: string;
  group: string;
  interactive: boolean;
  confirmation: boolean;
  example: string[];
}
// Curated browser tasks. Aliases, stdio servers, raw tokens and UI launch commands
// remain in the CLI/API catalog; config and updates have dedicated UI flows.
export const commandGroups = [
  {
    label: "Import & sync",
    primary: ["seed", "import", "distill", "sync"],
    advanced: [],
  },
  {
    label: "Inspect & search",
    primary: ["stats", "doctor", "status", "providers", "search", "recall"],
    advanced: ["health", "bootstrap", "quality", "relations"],
  },
  {
    label: "Maintenance",
    primary: ["reindex", "start", "restart", "logs"],
    advanced: ["stop", "redeploy", "register"],
  },
  {
    label: "Memory management",
    primary: [],
    advanced: [
      "remember",
      "materialize",
      "export-native",
      "review",
      "pin",
      "unpin",
      "supersede",
      "unarchive",
      "relate",
      "delete",
      "reset",
      "migrate",
    ],
  },
  {
    label: "Setup & integrations",
    primary: [],
    advanced: [
      "install",
      "setup",
      "recommend",
      "hooks",
      "unhooks",
      "stophooks",
      "unstophooks",
      "consolidate",
      "unconsolidate",
      "uninstall",
    ],
  },
  { label: "CLI help", primary: [], advanced: ["help", "version"] },
];
export function groupedCommands(catalog: Command[], advanced: boolean) {
  const byName = new Map(catalog.map((command) => [command.name, command]));
  return commandGroups
    .map((group) => ({
      label: group.label,
      commands: [...group.primary, ...(advanced ? group.advanced : [])].flatMap(
        (name) => (byName.has(name) ? [byName.get(name)!] : []),
      ),
    }))
    .filter((group) => group.commands.length > 0);
}
