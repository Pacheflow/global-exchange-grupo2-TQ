import { createElement } from "react";
import { createRoot } from "react-dom/client";

import { getRegisteredComponent } from "./registry";

const islandSelector = "[data-react-component]";

function parseProps(element: HTMLElement): Record<string, unknown> {
  const attributeProps = Object.entries(element.dataset).reduce<
    Record<string, string>
  >((props, [key, value]) => {
    const prefix = "reactProp";
    if (key.startsWith(prefix) && value !== undefined) {
      const propName = key.slice(prefix.length);
      if (propName) {
        props[`${propName[0].toLowerCase()}${propName.slice(1)}`] = value;
      }
    }
    return props;
  }, {});

  const propsSourceId = element.dataset.reactPropsId;
  const serializedProps = propsSourceId
    ? document.getElementById(propsSourceId)?.textContent
    : undefined;

  if (!serializedProps) {
    return attributeProps;
  }

  const parsedProps: unknown = JSON.parse(serializedProps);
  if (
    typeof parsedProps !== "object" ||
    parsedProps === null ||
    Array.isArray(parsedProps)
  ) {
    throw new TypeError(
      "Las propiedades de una isla React deben ser un objeto JSON.",
    );
  }

  return {
    ...(parsedProps as Record<string, unknown>),
    ...attributeProps,
  };
}

function mountReactIsland(element: HTMLElement): void {
  if (element.dataset.reactMounted === "true") {
    return;
  }

  const componentName = element.dataset.reactComponent;
  const Component = componentName
    ? getRegisteredComponent(componentName)
    : undefined;

  if (!Component) {
    console.error(
      `[Global Exchange] Componente React no registrado: ${componentName ?? "(vacío)"}`,
    );
    return;
  }

  try {
    const props = parseProps(element);
    createRoot(element).render(createElement(Component, props));
    element.dataset.reactMounted = "true";
  } catch (error) {
    console.error(
      `[Global Exchange] No se pudo montar ${componentName}.`,
      error,
    );
  }
}

function mountReactIslands(): void {
  document
    .querySelectorAll<HTMLElement>(islandSelector)
    .forEach(mountReactIsland);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mountReactIslands, { once: true });
} else {
  mountReactIslands();
}
