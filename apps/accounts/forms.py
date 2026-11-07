"""Formulários de contas e autenticação."""

from __future__ import annotations

from django import forms

from apps.accounts.models import User


class ParticipantLoginForm(forms.Form):
    username = forms.CharField(
        label="Username",
        max_length=150,
        strip=True,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "autocomplete": "username",
                "autocapitalize": "none",
                "spellcheck": "false",
                "placeholder": "Seu username",
            }
        ),
    )

    def clean_username(self) -> str:
        username = self.cleaned_data["username"].strip()
        if not username:
            raise forms.ValidationError("Informe seu username.")
        return username


class AdminLoginForm(ParticipantLoginForm):
    password = forms.CharField(
        label="Senha",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "autocomplete": "current-password",
            }
        ),
    )


class ParticipantImportForm(forms.Form):
    file = forms.FileField(
        label="Arquivo CSV",
        widget=forms.ClearableFileInput(
            attrs={
                "class": "form-control",
                "accept": ".csv,text/csv",
            }
        ),
    )


class ParticipantForm(forms.Form):
    username = forms.CharField(
        label="Username",
        max_length=150,
        strip=True,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "autocomplete": "off",
                "autocapitalize": "none",
                "spellcheck": "false",
                "placeholder": "Ex.: SpecialWeek",
            }
        ),
    )

    def __init__(self, *args, instance=None, **kwargs):
        self.instance = instance
        super().__init__(*args, **kwargs)
        if instance is not None and not self.is_bound:
            self.initial["username"] = instance.username

    def clean_username(self) -> str:
        username = self.cleaned_data["username"].strip()
        if not username:
            raise forms.ValidationError("Informe o username.")

        queryset = User.objects.filter(username__iexact=username)
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise forms.ValidationError("Já existe um usuário com esse username.")
        return username
