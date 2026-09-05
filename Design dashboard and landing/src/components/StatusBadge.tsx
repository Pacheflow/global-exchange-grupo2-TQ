interface StatusBadgeProps {
  status: 'PAGADA' | 'PENDIENTE' | 'CANCELADA' | 'ANULADA' | 'EMITIDA' | 'APROBADA' | 'RECHAZADA' | 'ABIERTA' | 'CERRADA';
  size?: 'sm' | 'md';
}

const styles: Record<string, { bg: string; text: string; dot: string }> = {
  PAGADA:    { bg: 'var(--success-bg)',  text: 'var(--success)',  dot: 'var(--success)' },
  APROBADA:  { bg: 'var(--success-bg)',  text: 'var(--success)',  dot: 'var(--success)' },
  ABIERTA:   { bg: 'var(--success-bg)',  text: 'var(--success)',  dot: 'var(--success)' },
  PENDIENTE: { bg: 'var(--warning-bg)',  text: 'var(--warning)',  dot: 'var(--warning)' },
  EMITIDA:   { bg: 'var(--warning-bg)',  text: 'var(--warning)',  dot: 'var(--warning)' },
  CANCELADA: { bg: 'var(--danger-bg)',   text: 'var(--danger)',   dot: 'var(--danger)'  },
  ANULADA:   { bg: 'var(--danger-bg)',   text: 'var(--danger)',   dot: 'var(--danger)'  },
  RECHAZADA: { bg: 'var(--danger-bg)',   text: 'var(--danger)',   dot: 'var(--danger)'  },
  CERRADA:   { bg: 'rgba(100,120,160,0.1)', text: 'var(--text-2)', dot: 'var(--text-2)' },
};

export default function StatusBadge({ status, size = 'md' }: StatusBadgeProps) {
  const s = styles[status] ?? styles.CERRADA;
  const pad = size === 'sm' ? '2px 8px' : '3px 10px';
  const fontSize = size === 'sm' ? '11px' : '12px';

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 5,
        background: s.bg,
        color: s.text,
        borderRadius: 6,
        padding: pad,
        fontSize,
        fontWeight: 600,
        fontFamily: 'DM Sans, sans-serif',
        letterSpacing: '0.04em',
        whiteSpace: 'nowrap',
      }}
    >
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: '50%',
          background: s.dot,
          flexShrink: 0,
        }}
      />
      {status}
    </span>
  );
}
