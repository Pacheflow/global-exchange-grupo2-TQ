import "./integration-probe.css";

export interface IntegrationProbeProps {
  message?: string;
}

export function IntegrationProbe({
  message = "React integrado correctamente",
}: IntegrationProbeProps) {
  return (
    <span className="react-integration-probe" data-react-status="ready">
      {message}
    </span>
  );
}
