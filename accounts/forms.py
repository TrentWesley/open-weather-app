from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


class AccessibleErrorsMixin:
    """NFR-AC-5: mark invalid fields and link them to their error list.

    Pairs with templates/includes/field.html, which renders each field's errors in
    an element with the id `<field id>_error`.
    """

    def full_clean(self) -> None:
        super().full_clean()
        for name in self.errors:
            if name not in self.fields:
                continue
            bound = self[name]
            attrs = self.fields[name].widget.attrs
            described_by = [f"{bound.auto_id}_error"]
            if self.fields[name].help_text:
                described_by.append(f"{bound.auto_id}_helptext")
            attrs["aria-invalid"] = "true"
            attrs["aria-describedby"] = " ".join(described_by)


class RegistrationForm(AccessibleErrorsMixin, UserCreationForm):
    """FR-1: username, email, password and confirmation.

    UserCreationForm already rejects usernames that differ only in case (FR-1 AC-3)
    and runs AUTH_PASSWORD_VALIDATORS on the confirmation field (FR-1 AC-4).
    """

    email = forms.EmailField(required=True)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")
