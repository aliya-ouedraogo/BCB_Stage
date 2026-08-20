import datetime

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .decorators import role_required
from .forms import AccepterCandidatureForm, EvaluationForm, InscriptionForm, ParametresForm, RefuserCandidatureForm
from .models import (
    Candidature,
    Departement,
    DemandeEncadrement,
    DocumentStage,
    Evaluation,
    Mission,
    Presence,
    ProfilMaitreStage,
    ProfilRH,
    ProfilStagiaire,
    RapportHebdomadaire,
    Stage,
    User,
)


# =========================================================
# Authentification / onboarding
# =========================================================

@never_cache
def onboarding(request):
    if request.user.is_authenticated:
        return redirect(request.user.get_dashboard_url_name())
    return render(request, 'appStage/onboarding.html')


@method_decorator(never_cache, name='dispatch')
class ConnexionView(LoginView):
    template_name = 'appStage/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse(self.request.user.get_dashboard_url_name())


@never_cache
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


@require_POST
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

    stagiaires_recents = Stage.objects.select_related('stagiaire__user', 'departement')

    filtre_statut = request.GET.get('statut', '')
    if filtre_statut in dict(Stage.Statut.choices):
        stagiaires_recents = stagiaires_recents.filter(statut=filtre_statut)

    stagiaires_recents = stagiaires_recents.order_by('-date_debut')[:6]

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
        'filtre_statut': filtre_statut,
    }
    return render(request, 'appStage/dashboard_rh.html', context)


@role_required(User.Role.RH)
def liste_stagiaires(request):
    stages = Stage.objects.select_related('stagiaire__user', 'departement', 'maitre_de_stage__user') \
        .order_by('-date_debut')
    return render(request, 'appStage/liste_stagiaires.html', {'stages': stages})


@role_required(User.Role.RH)
def candidatures(request):
    qs = Candidature.objects.select_related('departement_affecte', 'traite_par__user') \
        .order_by('-date_soumission')
    return render(request, 'appStage/candidatures.html', {
        'candidatures': qs,
        'departements': Departement.objects.all(),
    })


@require_POST
@role_required(User.Role.RH)
def accepter_candidature(request, candidature_id):
    candidature = get_object_or_404(Candidature, pk=candidature_id, statut=Candidature.Statut.EN_ATTENTE)
    form = AccepterCandidatureForm(request.POST)
    if form.is_valid():
        candidature.accepter(
            departement=form.cleaned_data['departement'],
            traite_par=request.user.profil_rh,
            date_debut=form.cleaned_data['date_debut'],
            date_fin=form.cleaned_data['date_fin'],
            avec_soutenance=form.cleaned_data['avec_soutenance'],
        )
        messages.success(request, f"Candidature de {candidature.nom_complet} acceptée — compte stagiaire créé.")
    else:
        messages.error(request, "Formulaire invalide : " + " ".join(
            f"{champ} : {', '.join(erreurs)}" for champ, erreurs in form.errors.items()
        ))
    return redirect('appStage:candidatures')


@require_POST
@role_required(User.Role.RH)
def refuser_candidature(request, candidature_id):
    candidature = get_object_or_404(Candidature, pk=candidature_id, statut=Candidature.Statut.EN_ATTENTE)
    form = RefuserCandidatureForm(request.POST)
    if form.is_valid():
        candidature.refuser(form.cleaned_data['motif'], request.user.profil_rh)
        messages.success(request, f"Candidature de {candidature.nom_complet} refusée.")
    else:
        messages.error(request, "Le motif de refus est obligatoire.")
    return redirect('appStage:candidatures')


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


@role_required(User.Role.MAITRE_STAGE)
def mes_stagiaires(request):
    profil = request.user.profil_maitre_stage
    stages = Stage.objects.filter(maitre_de_stage=profil) \
        .select_related('stagiaire__user', 'departement').order_by('-date_debut')
    return render(request, 'appStage/mes_stagiaires.html', {'stages': stages})


def _get_stage_ou_403(request, stage_id):
    """Charge un Stage en vérifiant que le tuteur connecté l'encadre bien (le RH a accès à tous)."""
    stage = get_object_or_404(
        Stage.objects.select_related('stagiaire__user', 'departement', 'maitre_de_stage__user'),
        pk=stage_id,
    )
    if request.user.role == User.Role.MAITRE_STAGE:
        if stage.maitre_de_stage_id != request.user.profil_maitre_stage.id:
            raise PermissionDenied("Ce stagiaire n'est pas sous votre encadrement.")
    return stage


@role_required(User.Role.MAITRE_STAGE, User.Role.RH)
def fiche_stagiaire(request, stage_id):
    stage = _get_stage_ou_403(request, stage_id)
    context = {
        'stage': stage,
        'missions': stage.missions.all(),
        'documents': stage.documents.all(),
        'presences': stage.presences.all()[:14],
        'evaluations': stage.evaluations.all(),
        'peut_evaluer': request.user.role == User.Role.MAITRE_STAGE,
    }
    return render(request, 'appStage/fiche_stagiaire.html', context)


@role_required(User.Role.MAITRE_STAGE)
def evaluer(request, stage_id):
    stage = _get_stage_ou_403(request, stage_id)

    if request.method == 'POST':
        form = EvaluationForm(request.POST)
        if form.is_valid():
            evaluation = form.save(commit=False)
            evaluation.stage = stage
            evaluation.save()
            messages.success(request, "Évaluation enregistrée.")
            return redirect('appStage:fiche_stagiaire', stage_id=stage.id)
    else:
        form = EvaluationForm(initial={'type_evaluation': Evaluation.TypeEvaluation.MI_PARCOURS})

    return render(request, 'appStage/evaluer.html', {'stage': stage, 'form': form})


@require_POST
@role_required(User.Role.MAITRE_STAGE)
def repondre_demande_encadrement(request, demande_id, reponse):
    demande = get_object_or_404(
        DemandeEncadrement, pk=demande_id,
        maitre_de_stage_demande=request.user.profil_maitre_stage,
        statut=DemandeEncadrement.Statut.EN_ATTENTE,
    )
    if reponse == 'accepter':
        demande.accepter()
        messages.success(request, f"Vous encadrez désormais {demande.stage.stagiaire.user.get_full_name()}.")
    else:
        demande.refuser()
        messages.success(request, "Demande refusée.")
    return redirect('appStage:dashboard_tuteur')


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
        if derniere_eval:
            context['etoiles_pleines'] = round(float(derniere_eval.note) / 20 * 5)

    return render(request, 'appStage/dashboard_stagiaire.html', context)


@role_required(User.Role.STAGIAIRE)
def mes_missions(request):
    stage = request.user.profil_stagiaire.stage_actif
    missions = stage.missions.all() if stage else []
    return render(request, 'appStage/mes_missions.html', {'stage': stage, 'missions': missions})


@role_required(User.Role.STAGIAIRE)
def mes_documents(request):
    stage = request.user.profil_stagiaire.stage_actif
    documents = stage.documents.all() if stage else []
    return render(request, 'appStage/mes_documents.html', {'stage': stage, 'documents': documents})


@role_required(User.Role.STAGIAIRE)
def choisir_tuteur(request):
    stage = request.user.profil_stagiaire.stage_actif
    tuteurs = ProfilMaitreStage.objects.select_related('user').all()
    demande_existante = None
    if stage:
        demande_existante = stage.demandes_encadrement.filter(
            statut=DemandeEncadrement.Statut.EN_ATTENTE
        ).select_related('maitre_de_stage_demande__user').first()

    if request.method == 'POST' and stage and not stage.maitre_de_stage and not demande_existante:
        tuteur_id = request.POST.get('tuteur_id')
        tuteur = get_object_or_404(ProfilMaitreStage, pk=tuteur_id)
        DemandeEncadrement.objects.create(stage=stage, maitre_de_stage_demande=tuteur)
        messages.success(request, f"Demande envoyée à {tuteur.user.get_full_name()}.")
        return redirect('appStage:choisir_tuteur')

    return render(request, 'appStage/choisir_tuteur.html', {
        'stage': stage, 'tuteurs': tuteurs, 'demande_existante': demande_existante,
    })


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


@require_POST
@role_required(User.Role.STAGIAIRE)
def avancer_mission(request, mission_id):
    """Fait avancer une mission d'une étape : À faire → En cours → Terminée."""
    mission = get_object_or_404(Mission, pk=mission_id, stage__stagiaire=request.user.profil_stagiaire)
    ordre = [Mission.Statut.A_FAIRE, Mission.Statut.EN_COURS, Mission.Statut.TERMINEE]
    idx = ordre.index(mission.statut)
    if idx < len(ordre) - 1:
        mission.statut = ordre[idx + 1]
        mission.save(update_fields=['statut'])
        messages.success(request, f"Mission « {mission.titre} » marquée « {mission.get_statut_display()} ».")
    return redirect(request.POST.get('retour') or 'appStage:dashboard_stagiaire')


# =========================================================
# Paramètres (commun aux 3 rôles)
# =========================================================

@role_required(User.Role.STAGIAIRE, User.Role.RH, User.Role.MAITRE_STAGE)
def parametres(request):
    if request.method == 'POST':
        form = ParametresForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Vos informations ont été mises à jour.")
            return redirect('appStage:parametres')
    else:
        form = ParametresForm(instance=request.user)

    return render(request, 'appStage/parametres.html', {'form': form})
