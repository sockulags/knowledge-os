import { EmptyState } from "../components/EmptyState";

export function NotFound() {
  return (
    <EmptyState
      title="Not found"
      body="Nothing lives at this address any more, or it never did."
    />
  );
}
