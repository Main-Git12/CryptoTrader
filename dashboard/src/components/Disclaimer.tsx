export default function Disclaimer() {
  return (
    <div
      role="note"
      style={{
        background: "var(--diverging-neutral)",
        color: "var(--text-secondary)",
        border: "1px solid var(--border)",
        borderRadius: 8,
        padding: "10px 16px",
        fontSize: 13,
        marginBottom: 24,
      }}
    >
      <strong style={{ color: "var(--text-primary)" }}>Informational only.</strong> This tracks public
      mention volume and a simple automated sentiment score. It is not financial advice, does not
      recommend buying or selling anything, and does not know anything about your circumstances.
    </div>
  );
}
