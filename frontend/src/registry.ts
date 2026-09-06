import type { ComponentType } from "react";

import { Landing } from "./components/Landing";

type ReactIslandProps = Record<string, unknown>;
type ReactIslandComponent = ComponentType<ReactIslandProps>;

export const componentRegistry = {
  Landing,
};

export type RegisteredComponentName = keyof typeof componentRegistry;

export function getRegisteredComponent(
  name: string,
): ReactIslandComponent | undefined {
  return componentRegistry[name as RegisteredComponentName] as unknown as
    | ReactIslandComponent
    | undefined;
}
