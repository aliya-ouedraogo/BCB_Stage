import datetime

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .decorators import role_required
from .forms import InscriptionForm
from .models import (
    Candidature,
    DemandeEncadrement,
    DocumentStage,
    Evaluation,
    Presence,
    ProfilMaitreStage,
    ProfilRH,
    ProfilStagiaire,
    RapportHebdomadaire,
    Stage,
    User,
)


# =========================================================
# Authentification / onboarding (inchangé)
# =========================================================

def onboarding(request):
    if request.user.is_authenticated:
        return redirect(request.user.get_dashboard_url_name())
    return render(request, 'appStage/onboarding.html')


class ConnexionView(LoginView):
    template_name = 'appStage/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse(self.request.user.get_dashboard_url_name())


def register(request):
    if request.user.is_authenticated:
        return redirect(request.user.get_dashboard_url_name())

    if request.method == 'POST':
        form = InscriptionForm(request.POST)
        if form.is_valid():
            user = form.save()

            if user.role == User.Role.STAGIAIRE:
                ProfilStagiaire.objects.create(user=user)
            elif user.role == User.Role.RH:
                ProfilRH.objects.create(user=user)
            elif user.role == User.Role.MAITRE_STAGE:
                ProfilMaitreStage.objects.create(user=user)

            login(request, user)
            return redirect(user.get_dashboard_url_name())
    else:
        form = InscriptionForm()

    return render(request, 'appStage/register.html', {'form': form})


def deconnexion(request):
    logout(request)
    return redirect('appStage:onboarding')


# =========================================================
# Tableau de bord RH
# =========================================================

@role_required(User.Role.RH)
def dashboard_rh(request):
    aujourdhui = timezone.now().date()
    debut_mois = aujourdhui.replace(day=1)

    stagiaires_actifs = Stage.objects.filter(statut=Stage.Statut.EN_COURS)
    nouveaux_stagiaires_ce_mois = stagiaires_actifs.filter(date_debut__gte=debut_mois).count()

    candidatures_en_attente = Candidature.objects.filter(statut=Candidature.Statut.EN_ATTENTE)
    nouvelles_candidatures_semaine = candidatures_en_attente.filter(
        date_soumission__gte=timezone.now() - datetime.timedelta(days=7)
    ).count()

    conventions = DocumentStage.objects.filter(type_document=DocumentStage.TypeDocument.CONVENTION)
    conventions_signees = conventions.filter(statut_signature=DocumentStage.StatutSignature.SIGNE)
    conventions_en_attente = conventions.filter(statut_signature=DocumentStage.StatutSignature.EN_ATTENTE) \
        .select_related('stage__stagiaire__user')

    fins_de_stage_ce_mois = Stage.objects.filter(
        date_fin__year=aujourdhui.year, date_fin__month=aujourdhui.month
    )

    stagiaires_recents = Stage.objects.select_related('stagiaire__user', 'departement') \
        .order_by('-date_debut')[:6]

    # Stages nécessitant une évaluation mi-parcours pas encore faite
    stages_sans_eval = Stage.objects.filter(
        statut=Stage.Statut.EN_COURS, avec_soutenance=True
    ).exclude(evaluations__type_evaluation=Evaluation.TypeEvaluation.MI_PARCOURS) \
     .select_related('stagiaire__user')

    context = {
        'nb_stagiaires_actifs': stagiaires_actifs.count(),
        'nouveaux_stagiaires_ce_mois': nouveaux_stagiaires_ce_mois,
        'nb_candidatures_en_attente': candidatures_en_attente.count(),
        'nouvelles_candidatures_semaine': nouvelles_candidatures_semaine,
        'nb_conventions_signees': conventions_signees.count(),
        'nb_conventions_en_attente': conventions_en_attente.count(),
        'nb_fins_de_stage_ce_mois': fins_de_stage_ce_mois.count(),
        'stagiaires_recents': stagiaires_recents,
        'conventions_en_attente': conventions_en_attente[:3],
        'stages_sans_eval': stages_sans_eval[:3],
    }
    return render(request, 'appStage/dashboard_rh.html', context)


# =========================================================
# Espace Maître de Stage
# =========================================================

@role_required(User.Role.MAITRE_STAGE)
def dashboard_tuteur(request):
    profil = request.user.profil_maitre_stage
    aujourdhui = timezone.now().date()

    stages_encadres = Stage.objects.filter(
        maitre_de_stage=profil, statut=Stage.Statut.EN_COURS
    ).select_related('stagiaire__user')

    rapports_a_valider = RapportHebdomadaire.objects.filter(
        stage__maitre_de_stage=profil, statut=RapportHebdomadaire.Statut.EN_ATTENTE
    ).select_related('stage__stagiaire__user').order_by('-date_soumission')

    demandes_en_attente = DemandeEncadrement.objects.filter(
        maitre_de_stage_demande=profil, statut=DemandeEncadrement.Statut.EN_ATTENTE
    ).select_related('stage__stagiaire__user')

    # Stage(s) dont la fin approche (30 jours) et sans évaluation finale
    fin_de_periode = stages_encadres.filter(
        date_fin__lte=aujourdhui + datetime.timedelta(days=30), avec_soutenance=True
    ).exclude(evaluations__type_evaluation=Evaluation.TypeEvaluation.FINALE).first()

    context = {
        'stages_encadres': stages_encadres,
        'rapports_a_valider': rapports_a_valider[:4],
        'demandes_en_attente': demandes_en_attente,
        'nb_a_valider': rapports_a_valider.count() + demandes_en_attente.count(),
        'fin_de_periode': fin_de_periode,
    }
    return render(request, 'appStage/dashboard_tuteur.html', context)


# =========================================================
# Portail Stagiaire
# =========================================================

@role_required(User.Role.STAGIAIRE)
def dashboard_stagiaire(request):
    profil = request.user.profil_stagiaire
    stage = profil.stage_actif

    context = {'stage': stage}

    if stage:
        aujourdhui = timezone.now().date()
        presences = stage.presences.all()

        context.update({
            'mission_actuelle': stage.missions.exclude(statut='TERMINEE').first(),
            'documents_recents': stage.documents.all()[:3],
            'derniere_evaluation': stage.evaluations.first(),
            'nb_presences_totales': presences.count(),
            'nb_jours_presents': presences.filter(present=True).count(),
            'nb_absences': presences.filter(present=False).count(),
            'nb_absences_justifiees': presences.filter(present=False, justifie=True).count(),
            'taux_presence': stage.taux_presence,
            'deja_pointe_aujourdhui': presences.filter(date=aujourdhui).exists(),
        })

        derniere_eval = context['derniere_evaluation']
        if derniere_eval and derniere_eval.note is not None:
            # Note sur 20 convertie en étoiles sur 5
            context['etoiles_pleines'] = round(float(derniere_eval.note) / 20 * 5)

    return render(request, 'appStage/dashboard_stagiaire.html', context)


@require_POST
@role_required(User.Role.STAGIAIRE)
def pointer_presence(request):
    """Auto-déclaration de présence du jour par le stagiaire (à confirmer ensuite par le tuteur)."""
    stage = request.user.profil_stagiaire.stage_actif
    if stage:
        Presence.objects.get_or_create(
            stage=stage, date=timezone.now().date(),
            defaults={'present': True},
        )
        messages.success(request, "Présence enregistrée pour aujourd'hui.")
    return redirect('appStage:dashboard_stagiaire')
