"""Formulários administrativos do catálogo."""

from __future__ import annotations

from django import forms

from apps.catalog.models import CatalogSource


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
