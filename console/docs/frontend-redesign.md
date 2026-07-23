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
| Ignition accent | `#ff6b2c` |
| Success | `#68d391` |
| Warning | `#f6c85f` |
| Radius | 9 px |

Orange is reserved for focus, active state, sequence and energy. Green is used
only for real positive system state.

## Signature

Home contains one animated orbital telemetry field. Its motion communicates a
live system scan and is disabled by `prefers-reduced-motion`. No other
perpetual decorative animation competes with it.

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

Wiring uses horizontally scrollable, snap-aligned process cards on narrow
screens. The tabs separate preparation, physical assembly and the pre-power
inspection, which prevents the diagram from competing with the checklist.

## Accessibility

- Dark theme is locked across all pages.
- Focus-visible outlines use the ignition accent.
- Button, input and muted-text contrast were checked in browser captures.
- Motion and smooth scrolling honor reduced-motion preferences.
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

## Shared implementation

`core/ui.py` owns:

- global CSS and responsive rules
- sidebar navigation and live status
- page and section headers
- reusable cards and process strips
- Plotly styling
- dark schematic transformation

`.streamlit/config.toml` owns the base dark theme and native widget tokens.

This separation keeps physics, serial parsing and persistence independent from
Streamlit presentation.
