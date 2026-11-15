# ParcelGuard: interface and motion

The operations workspace uses a charcoal and amber default palette, a light alternative, and a transaction map derived from the current order/outbox snapshot. Reserved, consumed, and acknowledged counts describe actual stored state.

## Interactions

- Use the sticky sidebar or mobile section bar to reach failure controls, orders, experiments, and research. Section selection and the header progress line follow scroll position.
- Press **Ctrl+K** or **Cmd+K** for section search, with arrow keys, Enter, and Escape support.
- Switch between dark and light themes. The header theme preference persists locally.
- Pause animations or use the system reduced-motion preference. Content and controls remain available with motion disabled.
- Watch the transaction map change when an order is reserved, an effect commits, and an event is acknowledged. Diagram wire motion stops when no event awaits acknowledgement.
- Retry-completion bars animate when a new experiment result is rendered. The tables retain completion and failure counts alongside conditional latency.
- Use the back-to-top control after scrolling through delivery logs and experiment results.

## Implementation choices

`web/studio.js` provides navigation, preference storage, native dialog search, scroll progress, and motion primitives. It is kept in sync with the other standalone workspaces. `web/app.js` owns the transaction map and experiment results; `web/style.css` defines the palette and responsive layouts.

Animations use CSS, the Web Animations API, and IntersectionObserver. requestAnimationFrame coalesces scroll/pointer updates rather than running a permanent idle JavaScript loop. Transforms and opacity handle most transitions. The diagram is a local transaction model; animation is not evidence of a network request or external fulfillment.

Forms preserve labels, busy states, and focus outlines. Native scrolling remains available. The API's idempotency, lease, retry, and stock semantics are unchanged. No external animation framework, font CDN, or runtime package is required.

## Verification

The browser harness exercises create/replay/conflict, lost-ACK recovery, experiment controls, export, matching pipeline counts, keyboard search, section tracking, theme/motion persistence, reduced motion, card-value fit, and three viewport sizes. See [browser-checks.json](../artifacts/browser-checks.json) for the actual run.

The report records a short local headless requestAnimationFrame timing sample. It is diagnostic evidence for that run, not a guaranteed frame rate, a production interaction benchmark, or cross-browser certification. Chromium was used for the browser checks.
