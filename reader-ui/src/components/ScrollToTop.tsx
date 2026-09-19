import { useEffect } from "react";
import { useLocation } from "react-router";

/** React Router does not reset scroll position on navigation by itself.
 * Without this, moving from a scrolled-down page (e.g. the bottom of a
 * long document) to a new route keeps the old scroll offset, which reads
 * as a broken page until the person scrolls up themselves. */
export function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return null;
}
