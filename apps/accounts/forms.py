"""Formulários de autenticação."""

from __future__ import annotations

from django import forms


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
