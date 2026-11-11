# ADR 0006: Gateway API with Traefik, not ingress-nginx

**Status:** accepted (Phase 3). Replaces the original plan ("ingress-nginx Ingress").

## Context
The plan said ingress-nginx. When I checked the project before installing it, the GitHub
repository `kubernetes/ingress-nginx` was **archived** (last release `controller-v1.15.1`,
March 2026). An archived controller gets no security patches, and it is the component that
faces the internet.

## Decision
- Use the **Gateway API** (`Gateway` + `HTTPRoute`), the official successor to the Ingress API.
  CRDs pinned to `v1.6.3` (standard channel).
- Use **Traefik** (chart `42.3.2`, Traefik `v3.7.17`) as the controller that implements it.

## How the pieces fit
| Object | Owner | Meaning |
|---|---|---|
| `GatewayClass` traefik | platform | "Traefik implements gateways of this class" |
| `Gateway` shopflow (namespace `traefik`) | platform | Open HTTP port; which namespaces may attach routes |
| `HTTPRoute` shopflow (per app namespace) | app team (Helm chart) | hostname -> Service `web` |

With Ingress, all of this was one object plus controller-specific annotations. Gateway API
splits it by role, and the Gateway only accepts routes from namespaces labelled
`shopflow.io/gateway-access: "true"`.

## Why not the alternatives
- **ingress-nginx anyway:** unmaintained. Hard to defend in a "run it like production" project.
- **Traefik with the old Ingress API:** works, but Ingress is frozen; new features only land in Gateway API.
- **Envoy Gateway:** good, but on kind it needs extra configuration to expose its proxy without a load balancer.

## Consequences
- One more install step (Gateway API CRDs) before the controller.
- No TLS yet: the listener is plain HTTP on a local port. A real cluster adds an HTTPS listener and cert-manager.
- Phase 6 (Argo Rollouts) must use Gateway API traffic routing or replica-based canaries, not nginx annotations.
