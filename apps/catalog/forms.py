"""Formulários administrativos do catálogo."""

from __future__ import annotations

from django import forms
from django.conf import settings

from apps.catalog.models import CatalogSource, ImportJob
from apps.catalog.services.sources.registry import available_sources


class CatalogSyncForm(forms.Form):
    source = forms.ModelChoiceField(
        label="Fonte",
        queryset=CatalogSource.objects.filter(enabled=True),
        empty_label=None,
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    file = forms.FileField(
        label="Arquivo de catálogo (CSV)",
        widget=forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".csv,text/csv"}),
    )


class ImportJobForm(forms.Form):
    """Formulário de criação de importação externa (sem upload)."""

    source = forms.ModelChoiceField(
        label="Fonte externa",
        queryset=CatalogSource.objects.none(),
        empty_label="Selecione uma fonte habilitada",
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    kind = forms.ChoiceField(
        label="Modo",
        choices=ImportJob.Kind.choices,
        initial=ImportJob.Kind.CATALOG,
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    image_scope = forms.CharField(
        label="Escopo das imagens",
        required=False,
        initial="missing",
        widget=forms.Select(
            choices=[
                ("missing", "Somente personagens sem imagem válida"),
                ("all", "Todas as personagens"),
            ],
            attrs={"class": "form-control"},
        ),
    )
    license_ack = forms.BooleanField(
        label="Li e revisei a nota de licença da fonte",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Avaliado por requisição: o registry pode mudar entre deploys/testes.
        self.fields["source"].queryset = available_sources()

    def clean(self):
        cleaned = super().clean()
        if not settings.EXTERNAL_IMPORT_ENABLED:
            raise forms.ValidationError("Importação externa desabilitada.")

        kind = cleaned.get("kind")
        scope = cleaned.get("image_scope") or "missing"
        cleaned["image_scope"] = scope if scope in {"missing", "all"} else "missing"

        if kind in {ImportJob.Kind.IMAGES, ImportJob.Kind.FULL} and not cleaned.get("license_ack"):
            self.add_error(
                "license_ack",
                "Confirme a leitura da nota de licença para importar imagens.",
            )
        return cleaned

    def clean_source(self):
        source = self.cleaned_data["source"]
        if not source.enabled:
            raise forms.ValidationError("A fonte selecionada está desabilitada.")
        return source
