# Frontend and UX system

## Design read

Rocketry Console is an operator-facing engineering instrument. The interface
uses a dark, precise and compact language drawn from telemetry displays and
test equipment, without imitating a fictional cockpit.

Design dials:

- Variance: 6
- Motion: 4
- Density: 7

## Tokens

| Role | Value |
| --- | --- |
| Background | `#080b10` |
| Panel | `#10151d` |
| Raised panel | `#151c26` |
| Border | `#29313d` |
| Primary text | `#eef2f7` |
| Muted text | `#8d99a8` |
| Signal red accent | `#ef4444` |
| Success | `#68d391` |
| Warning | `#f6c85f` |
| Radius | 9 px |

Red is reserved for focus, active state, sequence and energy. Green is used
only for real positive system state.

## Signature

Home uses a restrained mission line: `measure → verify → decide`. A two-pixel
signal sweep communicates live status without the synthetic radar illustration
used in the first redesign.

The wordmark and icon are local SVG assets. They have no network dependency.

## Interaction model

Every work surface follows the same sequence:

```text
Context -> inputs -> execution -> result -> save or continue
```

- Bench: Connect, Capture, Review
- Wiring: Prepare, Connect, Verify
- Motor: Bound, Simulate, Evaluate
- Flight: Select, Define, Check
- History: Inspect, Compare, Manage
- Agent: Observe terminal work, inspect the latest persisted result

Wiring uses horizontally scrollable, snap-aligned steps on narrow screens. On
wider screens these are open steps separated by rules, not cards.
The tabs separate preparation, physical assembly and the pre-power inspection.

The `Language / Idioma` selector keeps English or Spanish across every page in
the current browser session. Navigation, workflows, validation messages,
tables and plot labels all follow the same selection.

## Accessibility

- Dark theme is locked across all pages.
- Focus-visible outlines use the signal-red accent.
- Button, input and muted-text contrast were checked in browser captures.
- Motion and smooth scrolling honor reduced-motion preferences.
- Page entrance, signal and button feedback use native CSS. GSAP was evaluated
  but rejected here because the existing Streamlit app has no JavaScript build
  pipeline and these simple effects do not justify a runtime dependency.
- Dynamic HTML strings are escaped before insertion.
- Status dots carry adjacent text and never communicate state alone.
- Destructive run deletion requires explicit confirmation.

## GitHub component research

The following projects were evaluated:

- Streamlit core: <https://github.com/streamlit/streamlit>
- Streamlit Extras: <https://github.com/arnaudmiribel/streamlit-extras>
- Streamlit Lottie: <https://github.com/andfanilo/streamlit-lottie>
- Streamlit scroll navigation: <https://github.com/SnpM/streamlit-scroll-navigation>
- Scroll to top component: <https://github.com/bowespublishing/streamlit-scroll-to-top>
- Phosphor icon system: <https://github.com/phosphor-icons/core>

Decisions:

- The current native `st.container(key=...)` pattern replaced the deprecated
  styled-container helper from Streamlit Extras.
- Native Streamlit Material icons are used for controls and navigation to
  avoid another runtime dependency.
- Lottie was not added because the available Streamlit wrapper is old and a
  remote animation asset would weaken offline behavior.
- The iframe-based scroll component was not added because its own description
  calls the technique fragile. CSS `scroll-snap`, native scrolling and sticky
  navigation cover the actual operator need.
- The motion treatment uses a small local SVG/CSS system with a reduced-motion
  fallback. It communicates state rather than adding decorative movement.
- Generic card containers were removed from workflow steps, metrics, forms and
  Home actions. Rules, spacing and typography now carry the hierarchy.

## Shared implementation

`core/ui.py` owns:

- global CSS and responsive rules
- sidebar navigation and live status
- page and section headers
- open action rows and process strips
- Plotly styling
- dark schematic transformation

`.streamlit/config.toml` owns the base dark theme and native widget tokens.

This separation keeps physics, serial parsing and persistence independent from
Streamlit presentation.
