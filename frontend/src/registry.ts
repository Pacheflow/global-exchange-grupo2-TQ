import type { ComponentType } from "react";

import { IntegrationProbe } from "./components/IntegrationProbe";
import { Landing } from "./components/Landing";
import { Navbar } from "./components/Navbar";

type ReactIslandProps = Record<string, unknown>;
type ReactIslandComponent = ComponentType<ReactIslandProps>;

export const componentRegistry = {
  IntegrationProbe,
  Landing,
  Navbar,
};

export type RegisteredComponentName = keyof typeof componentRegistry;

export function getRegisteredComponent(
  name: string,
): ReactIslandComponent | undefined {
  return componentRegistry[name as RegisteredComponentName] as unknown as
    | ReactIslandComponent
    | undefined;
}
