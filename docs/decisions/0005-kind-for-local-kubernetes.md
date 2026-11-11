# ADR 0005: kind for local Kubernetes

**Status:** accepted (Phase 3)

## Decision
Run Kubernetes locally with kind (Kubernetes in Docker). Cluster definition is in
`k8s/kind/cluster.yaml`, with the node image pinned by version and digest.

## Why kind
- Free, and it only needs Docker, which is already installed.
- The cluster is a file in git: anyone can recreate the same cluster with one command.
- It runs real upstream Kubernetes, so manifests behave the same on a cloud cluster.
- Create and delete take about two minutes, so breaking it on purpose is cheap.

## Why not the alternatives
- **Docker Desktop's built-in Kubernetes:** one click, but the version and settings live in a GUI, not in git.
- **minikube:** fine too; more features than needed (drivers, addons) and one more tool to learn.
- **k3d / k3s:** k3s swaps some upstream parts (for example the datastore). Good for edge, less "standard" for learning.
- **A cloud cluster (EKS):** costs money. Optional in Phase 9.

## Consequences
- One node only. No real node failure or multi-zone tests. Enough for Phases 3 to 8.
- No cloud load balancer. The gateway uses a `hostPort` plus a kind port mapping (`localhost:8090`).
- Images are copied into the node with `kind load docker-image`; there is no registry pull yet (Phase 4 uses GHCR).
- Two laptop-specific patches were needed in `cluster.yaml` (cgroup v1 and a longer kubeadm timeout). See docs/lessons-learned.md.
