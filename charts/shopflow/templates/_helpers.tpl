{{/*
Helpers: small named templates reused by the other files.
Call one with:  {{ include "shopflow.labels" (dict "root" . "component" "api") }}
*/}}

{{/* Labels put on every object. "selectorLabels" is the stable subset used to match pods. */}}
{{- define "shopflow.selectorLabels" -}}
app.kubernetes.io/name: shopflow
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end }}

{{- define "shopflow.labels" -}}
{{ include "shopflow.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .root.Release.Service }}
helm.sh/chart: {{ .root.Chart.Name }}-{{ .root.Chart.Version }}
{{- end }}

{{/* Full image reference for one of our three services. */}}
{{- define "shopflow.image" -}}
{{- $registry := .root.Values.image.registry -}}
{{- if $registry }}{{ $registry }}/{{ end }}shopflow-{{ .component }}:{{ .root.Values.image.tag }}
{{- end }}

{{/* Container hardening shared by api, worker, web and redis. */}}
{{- define "shopflow.containerSecurity" -}}
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
capabilities:
  drop: ["ALL"]
{{- end }}

{{/*
Database env vars. Kubernetes expands $(NAME) from variables defined earlier in
the same list, so the password comes from the Secret and never appears in the chart.
*/}}
{{- define "shopflow.databaseEnv" -}}
- name: POSTGRES_USER
  valueFrom: { secretKeyRef: { name: {{ .Values.databaseSecret }}, key: POSTGRES_USER } }
- name: POSTGRES_PASSWORD
  valueFrom: { secretKeyRef: { name: {{ .Values.databaseSecret }}, key: POSTGRES_PASSWORD } }
- name: POSTGRES_DB
  valueFrom: { secretKeyRef: { name: {{ .Values.databaseSecret }}, key: POSTGRES_DB } }
- name: DATABASE_URL
  value: postgresql+psycopg://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@postgres:5432/$(POSTGRES_DB)
{{- end }}
