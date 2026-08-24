export const workspaces = ["overview", "logs", "events", "topology", "runtimes", "plugins", "lyf", "configuration", "developer"] as const;
export type Workspace = (typeof workspaces)[number];

/**
 * Checks whether a hash-route value names a supported workspace.
 * @param value - Untrusted route fragment to validate.
 * @returns Whether TypeScript may narrow the value to `Workspace`.
 */
export function isWorkspace(value: string): value is Workspace {
  return workspaces.includes(value as Workspace);
}
