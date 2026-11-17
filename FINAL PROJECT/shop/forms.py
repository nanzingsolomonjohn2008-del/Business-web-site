from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm


User = get_user_model()


class AccountCreationForm(UserCreationForm):
    email = forms.EmailField(max_length=150)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("email",)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "An account with this email address already exists."
            )
        if User.objects.filter(username__iexact=email).exists():
            raise forms.ValidationError(
                "This email address cannot be used for a new account."
            )
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data["email"].lower()
        user.email = self.cleaned_data["email"].lower()
        if commit:
            user.save()
            self.save_m2m()
        return user
