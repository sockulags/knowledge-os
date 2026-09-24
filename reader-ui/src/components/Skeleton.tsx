export function Skeleton({ className }: { className?: string }) {
  return <div className={`animate-pulse rounded-(--radius-control) bg-(--color-bg-hover) ${className ?? ""}`} />;
}

/** Page-level skeleton shown while a route's data is loading, so
 * navigation never shows a blank flash (design brief). */
export function PageSkeleton() {
  return (
    <div className="mx-auto w-full max-w-[720px] px-6 py-12">
      <Skeleton className="mb-4 h-4 w-40" />
      <Skeleton className="mb-8 h-10 w-2/3 rounded-(--radius-card)" />
      <Skeleton className="mb-3 h-4 w-full" />
      <Skeleton className="mb-3 h-4 w-full" />
      <Skeleton className="mb-3 h-4 w-5/6" />
      <Skeleton className="mb-8 h-4 w-3/4" />
      <Skeleton className="h-32 w-full rounded-(--radius-card)" />
    </div>
  );
}
