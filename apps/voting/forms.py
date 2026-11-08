"""Formulários administrativos de votações."""

from __future__ import annotations

from django import forms

from apps.accounts.models import User
from apps.voting.models import Voting
from apps.voting.services.lifecycle import VotingConfigError, validate_configuration

FORM_CONTROL = {"class": "form-control"}


class VotingForm(forms.ModelForm):
    opens_at = forms.DateTimeField(
        label="Abertura",
        required=False,
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={"type": "datetime-local", **FORM_CONTROL},
        ),
        help_text="Obrigatória no modo automático; informativa no modo manual.",
    )
    closes_at = forms.DateTimeField(
        label="Encerramento",
        required=False,
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={"type": "datetime-local", **FORM_CONTROL},
        ),
        help_text="Obrigatória no modo automático; informativa no modo manual.",
    )

    class Meta:
        model = Voting
        fields = [
            "title",
            "description",
            "choices_count",
            "catalog_cutoff_date",
            "open_mode",
            "close_mode",
            "opens_at",
            "closes_at",
        ]
        widgets = {
            "title": forms.TextInput(attrs=FORM_CONTROL),
            "description": forms.Textarea(attrs={"rows": 4, **FORM_CONTROL}),
            "choices_count": forms.NumberInput(attrs={"min": 1, "step": 1, **FORM_CONTROL}),
            "catalog_cutoff_date": forms.DateInput(attrs={"type": "date", **FORM_CONTROL}),
            "open_mode": forms.Select(attrs=FORM_CONTROL),
            "close_mode": forms.Select(attrs=FORM_CONTROL),
        }
        help_texts = {
            "choices_count": "Quantidade exata de personagens por cédula.",
            "catalog_cutoff_date": "Somente versões lançadas até esta data entram na votação.",
            "open_mode": "Manual permite abrir explicitamente; automático usa o agendador.",
            "close_mode": "Manual permite encerrar explicitamente; automático usa o agendador.",
        }

    def clean(self):
        cleaned = super().clean()
        try:
            validate_configuration(cleaned, instance=self.instance)
        except VotingConfigError as exc:
            raise forms.ValidationError(exc.message) from exc
        return cleaned


class EligibleAddForm(forms.Form):
    users = forms.ModelMultipleChoiceField(
        label="Adicionar participantes elegíveis",
        queryset=User.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, voting: Voting, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["users"].queryset = (
            User.objects.filter(is_active=True)
            .exclude(voting_eligibilities__voting=voting)
            .order_by("username")
        )
