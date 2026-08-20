from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import Departement, Evaluation, User


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


class EvaluationForm(forms.ModelForm):
    """Notation par critère (sur 20 chacun) + commentaire — voir Evaluation.note (moyenne calculée)."""

    class Meta:
        model = Evaluation
        fields = [
            'type_evaluation', 'note_technique', 'note_autonomie',
            'note_communication', 'note_ponctualite', 'commentaire',
        ]
        widgets = {
            'note_technique': forms.NumberInput(attrs={'type': 'range', 'min': 0, 'max': 20, 'class': 'criteria-slider'}),
            'note_autonomie': forms.NumberInput(attrs={'type': 'range', 'min': 0, 'max': 20, 'class': 'criteria-slider'}),
            'note_communication': forms.NumberInput(attrs={'type': 'range', 'min': 0, 'max': 20, 'class': 'criteria-slider'}),
            'note_ponctualite': forms.NumberInput(attrs={'type': 'range', 'min': 0, 'max': 20, 'class': 'criteria-slider'}),
            'commentaire': forms.Textarea(attrs={'rows': 5, 'maxlength': 1000, 'placeholder': "Décrivez la performance, les points forts, les axes d'amélioration…"}),
        }
        labels = {
            'type_evaluation': "Type d'évaluation",
            'note_technique': "Compétences techniques",
            'note_autonomie': "Autonomie",
            'note_communication': "Communication",
            'note_ponctualite': "Ponctualité / Rigueur",
            'commentaire': "Commentaires détaillés",
        }


class AccepterCandidatureForm(forms.Form):
    departement = forms.ModelChoiceField(
        queryset=Departement.objects.all(), label="Département d'affectation",
        empty_label="Choisir un département…",
    )
    date_debut = forms.DateField(label="Date de début", widget=forms.DateInput(attrs={'type': 'date'}))
    date_fin = forms.DateField(label="Date de fin", widget=forms.DateInput(attrs={'type': 'date'}))
    avec_soutenance = forms.BooleanField(
        label="Stage avec soutenance / rapports / tuteur", required=False, initial=True,
    )

    def clean(self):
        cleaned = super().clean()
        debut, fin = cleaned.get('date_debut'), cleaned.get('date_fin')
        if debut and fin and fin <= debut:
            raise forms.ValidationError("La date de fin doit être postérieure à la date de début.")
        return cleaned


class RefuserCandidatureForm(forms.Form):
    motif = forms.CharField(
        label="Motif du refus", widget=forms.Textarea(attrs={'rows': 3}), required=True,
    )


class ParametresForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'telephone', 'photo']
        labels = {
            'first_name': "Prénom",
            'last_name': "Nom",
            'email': "Adresse e-mail",
            'telephone': "Téléphone",
            'photo': "Photo de profil",
        }


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
