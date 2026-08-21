export const workspaces = ["overview", "events", "topology", "runtimes", "plugins", "lyf", "configuration"] as const;
export type Workspace = (typeof workspaces)[number];

export function isWorkspace(value: string): value is Workspace {
  return workspaces.includes(value as Workspace);
}
