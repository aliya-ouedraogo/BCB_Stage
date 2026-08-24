from django import forms

from .models import Candidature, Departement, Evaluation, User


class CandidaturePubliqueForm(forms.ModelForm):
    """
    Formulaire public de dépôt de candidature — remplace l'ancienne
    inscription libre. Aucun compte n'est créé ici : seul le RH, en
    acceptant la candidature, déclenche la création du compte stagiaire.
    """

    class Meta:
        model = Candidature
        fields = ['nom_complet', 'email', 'telephone', 'poste_souhaite', 'cv', 'lettre_motivation', 'piece_identite']
        labels = {
            'nom_complet': "Nom complet",
            'email': "Adresse e-mail",
            'telephone': "Téléphone",
            'poste_souhaite': "Poste souhaité",
            'cv': "CV",
            'lettre_motivation': "Lettre de motivation",
            'piece_identite': "Copie de la CNIB",
        }


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
