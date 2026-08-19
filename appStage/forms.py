from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import User


class InscriptionForm(UserCreationForm):
    """
    Formulaire d'inscription. Le rôle choisi ici détermine l'espace
    (stagiaire / RH / maître de stage) auquel la personne aura accès,
    et déclenche la création automatique du profil correspondant
    (voir views.register).
    """

    first_name = forms.CharField(label="Prénom", max_length=150, required=True)
    last_name = forms.CharField(label="Nom", max_length=150, required=True)
    email = forms.EmailField(label="Adresse e-mail", required=True)
    role = forms.ChoiceField(label="Vous êtes", choices=User.Role.choices, required=True)

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'role', 'username', 'password1', 'password2']

    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Un compte existe déjà avec cette adresse e-mail.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.role = self.cleaned_data['role']
        if commit:
            user.save()
        return user
