{{/* Expand the name of the chart. */}}
{{- define "kserve-vllm-mini.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/* Create a default fully qualified app name. */}}
{{- define "kserve-vllm-mini.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/* Chart name and version label. */}}
{{- define "kserve-vllm-mini.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/* Common labels. */}}
{{- define "kserve-vllm-mini.labels" -}}
helm.sh/chart: {{ include "kserve-vllm-mini.chart" . }}
{{ include "kserve-vllm-mini.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/* Selector labels. */}}
{{- define "kserve-vllm-mini.selectorLabels" -}}
app.kubernetes.io/name: {{ include "kserve-vllm-mini.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/* Name of the service account to use. */}}
{{- define "kserve-vllm-mini.serviceAccountName" -}}
{{- if .Values.harness.serviceAccount.create }}
{{- default (include "kserve-vllm-mini.fullname" .) .Values.harness.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.harness.serviceAccount.name }}
{{- end }}
{{- end }}
