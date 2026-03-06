"use client";

type ErrorProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function Error({ error, reset }: ErrorProps) {
  return (
    <main
      style={{
        minHeight: "100vh",
        display: "grid",
        placeItems: "center",
        padding: "24px",
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
        <h1 style={{ margin: 0, fontSize: "1.2rem" }}>Something went wrong</h1>
        <p style={{ margin: "10px 0 0", color: "#5e6a7d" }}>
          {error.message || "Unexpected application error."}
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
          Try again
        </button>
      </section>
    </main>
  );
}
