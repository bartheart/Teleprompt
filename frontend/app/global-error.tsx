"use client";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          display: "grid",
          placeItems: "center",
          padding: "24px",
          background: "#f5f7fa",
          fontFamily: "var(--font-geist-sans), sans-serif",
        }}
      >
        <section
          style={{
            width: "min(560px, 100%)",
            border: "1px solid #d8e0ea",
            borderRadius: 14,
            background: "#ffffff",
            padding: "20px",
          }}
        >
          <h1 style={{ margin: 0, fontSize: "1.2rem" }}>Application error</h1>
          <p style={{ margin: "10px 0 0", color: "#5e6a7d" }}>
            {error.message || "Unexpected fatal error."}
          </p>
          <button
            type="button"
            onClick={reset}
            style={{
              marginTop: 14,
              borderRadius: 10,
              border: "1px solid #d4dde8",
              padding: "8px 12px",
              cursor: "pointer",
            }}
          >
            Reload
          </button>
        </section>
      </body>
    </html>
  );
}
