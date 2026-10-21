// jsdom brings its own AbortController, but `Request` is Node's, which
// refuses a signal it did not make. The data router builds a Request for
// every navigation, so a component test that navigates (a blocked
// navigation that then proceeds) would fail. No test route has a loader to
// cancel, so the router's signal can be dropped.
const NodeRequest = globalThis.Request;
globalThis.Request = class extends NodeRequest {
  constructor(input: RequestInfo | URL, init?: RequestInit) {
    const { signal: _signal, ...rest } = init ?? {};
    super(input, rest);
  }
} as typeof Request;
