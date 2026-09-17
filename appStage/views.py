import csv
import datetime
from collections import Counter

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied
from django.conf import settings
from django.db import IntegrityError
from django.db.models import Case, Count, IntegerField, ProtectedError, Q, Value, When
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.http import urlsafe_base64_decode
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.safestring import mark_safe
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .decorators import role_required
from .forms import (
    ActiverCompteForm,
    AffecterMaitreStageForm,
    AffecterServiceForm,
    AssignerMissionForm,
    CandidaturePubliqueForm,
    ChangerMotDePasseForm,
    CreerDepartementForm,
    CreerDirecteurForm,
    CreerTuteurForm,
    EnvoyerDocumentRHForm,
    EvaluationForm,
    ParametresForm,
    PlanifierStageForm,
    ProgrammerEntretienForm,
    RefuserCandidatureForm,
    SoumettreDocumentForm,
)
from .models import (
    Candidature,
    Departement,
    DemandeEncadrement,
    DocumentStage,
    Evaluation,
    Mission,
    Notification,
    Presence,
    ProfilDirecteur,
    ProfilMaitreStage,
    ProfilStagiaire,
    RapportHebdomadaire,
    Stage,
    User,
)


# =========================================================
# Utilitaires : export CSV & répartitions en donut
# =========================================================

def _reponse_csv(nom_fichier, entetes, lignes):
    """
    Construit une réponse CSV téléchargeable (séparateur ';' et BOM UTF-8,
    pour qu'Excel en français affiche correctement les accents sans réglage
    manuel de l'utilisateur).
    """
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{nom_fichier}"'
    response.write('\ufeff')
    writer = csv.writer(response, delimiter=';')
    writer.writerow(entetes)
    writer.writerows(lignes)
    return response


def _repartition_donut(paires, palette=None):
    """
    Transforme une liste de (label, effectif) déjà regroupée en données prêtes
    pour un graphique en anneau CSS (conic-gradient) : segments avec couleur
    et pourcentage, plus la chaîne de dégradé toute faite.
    """
    palette = palette or ['#6d5ef8', '#16a34a', '#f59e0b', '#0ea5e9', '#f43f5e', '#94a3b8']
    paires = [(label, count) for label, count in paires if count]
    total = sum(count for _, count in paires)

    if not total:
        return {'total': 0, 'segments': [], 'gradient_css': 'conic-gradient(#e9e9ee 0% 100%)'}

    segments, stops, cumul = [], [], 0.0
    for i, (label, count) in enumerate(paires):
        couleur = palette[i % len(palette)]
        debut = cumul
        cumul += count * 100 / total
        segments.append({
            'label': label, 'count': count,
            'pourcentage': round(count * 100 / total),
            'couleur': couleur,
        })
        stops.append(f"{couleur} {debut:.2f}% {cumul:.2f}%")

    return {'total': total, 'segments': segments, 'gradient_css': "conic-gradient(" + ", ".join(stops) + ")"}


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
def candidature_publique(request):
    """
    Formulaire public de dépôt de candidature, remplace l'ancienne
    inscription libre. Ne nécessite aucun compte : le RH créera le
    compte automatiquement s'il accepte la candidature.
    """
    if request.user.is_authenticated:
        return redirect(request.user.get_dashboard_url_name())

    if request.method == 'POST':
        form = CandidaturePubliqueForm(request.POST, request.FILES)
        if form.is_valid():
            candidature = form.save()
            candidature.notifier_rh()
            return render(request, 'appStage/candidature_envoyee.html')
    else:
        form = CandidaturePubliqueForm()

    return render(request, 'appStage/candidature_publique.html', {'form': form})


@never_cache
def activer_compte(request, uidb64, token):
    """
    Lien reçu par email après acceptation d'une candidature : permet au
    stagiaire de définir lui-même son mot de passe (jamais généré/envoyé
    en clair) et active son compte.
    """
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = User.objects.get(pk=uid)
    except (User.DoesNotExist, ValueError, TypeError, OverflowError):
        user = None

    lien_valide = user is not None and default_token_generator.check_token(user, token)

    if not lien_valide:
        return render(request, 'appStage/activation_invalide.html', status=400)

    if request.method == 'POST':
        form = ActiverCompteForm(user, request.POST)
        if form.is_valid():
            form.save()
            login(request, user)
            messages.success(request, "Votre compte est activé. Bienvenue sur BCBStageFlow !")
            return redirect(user.get_dashboard_url_name())
    else:
        form = ActiverCompteForm(user)

    return render(request, 'appStage/activer_compte.html', {'form': form})


@require_POST
def deconnexion(request):
    logout(request)
    return redirect('appStage:onboarding')


# =========================================================
# Tableau de bord RH
# =========================================================

NOMS_MOIS_COURTS = [
    'Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin',
    'Juil', 'Août', 'Sep', 'Oct', 'Nov', 'Déc',
]


def _premier_jour_mois_glissant(date_reference, n_mois_avant):
    """1er jour du mois situé n_mois_avant avant date_reference (0 = mois courant)."""
    index_mois_total = date_reference.month - 1 - n_mois_avant
    annee = date_reference.year + index_mois_total // 12
    mois = index_mois_total % 12 + 1
    return datetime.date(annee, mois, 1)


@role_required(User.Role.RH)
def dashboard_rh(request):
    Stage.synchroniser_statuts()
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

    # --- Alertes de fin (et de début) de période de stage ---
    stages_en_cours = Stage.objects.filter(statut=Stage.Statut.EN_COURS).select_related('stagiaire__user')
    stages_fin_proche = [s for s in stages_en_cours if s.se_termine_bientot]
    stages_periode_depassee = [s for s in stages_en_cours if s.periode_depassee]

    stages_a_venir = Stage.objects.filter(statut=Stage.Statut.A_VENIR).select_related('stagiaire__user')
    stages_debut_proche = [s for s in stages_a_venir if s.demarre_bientot]

    # --- Graphique : candidatures reçues et nouveaux stagiaires, 6 derniers mois ---
    mois_glissants = [_premier_jour_mois_glissant(aujourdhui, n) for n in range(5, -1, -1)]
    chart_data = {
        'labels': [f"{NOMS_MOIS_COURTS[m.month - 1]} {m.year}" for m in mois_glissants],
        'candidatures': [
            Candidature.objects.filter(date_soumission__year=m.year, date_soumission__month=m.month).count()
            for m in mois_glissants
        ],
        'stagiaires': [
            Stage.objects.filter(date_debut__year=m.year, date_debut__month=m.month).count()
            for m in mois_glissants
        ],
    }

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
        'stages_periode_depassee': stages_periode_depassee[:3],
        'stages_fin_proche': stages_fin_proche[:3],
        'stages_debut_proche': stages_debut_proche[:3],
        'filtre_statut': filtre_statut,
        'chart_data': chart_data,
        'annee_courante': aujourdhui.year,
    }
    return render(request, 'appStage/dashboard_rh.html', context)


def _stages_filtres(request):
    """Requête + filtres partagés entre la page Stagiaires (RH) et son export CSV."""
    Stage.synchroniser_statuts()
    stages = Stage.objects.select_related('stagiaire__user', 'departement', 'maitre_de_stage__user') \
        .order_by('-date_debut')

    recherche = request.GET.get('q', '').strip()
    if recherche:
        stages = stages.filter(
            Q(stagiaire__user__first_name__icontains=recherche) |
            Q(stagiaire__user__last_name__icontains=recherche) |
            Q(intitule_poste__icontains=recherche) |
            Q(departement__nom__icontains=recherche)
        )

    filtre_statut = request.GET.get('statut', '')
    if filtre_statut in dict(Stage.Statut.choices):
        stages = stages.filter(statut=filtre_statut)

    return stages, recherche, filtre_statut


@role_required(User.Role.RH)
def liste_stagiaires(request):
    stages, recherche, filtre_statut = _stages_filtres(request)

    # Pagination "voir plus" (pas de vraie pagination par pages : on charge
    # juste davantage de lignes à chaque clic, dans la même liste).
    total_stagiaires = stages.count()
    try:
        limite = max(10, int(request.GET.get('limite', 10)))
    except (TypeError, ValueError):
        limite = 10

    context = {
        'stages': stages[:limite],
        'recherche': recherche,
        'filtre_statut': filtre_statut,
        'limite': limite,
        'total_stagiaires': total_stagiaires,
        'restants': max(0, total_stagiaires - limite),
    }

    # Requête de recherche en direct (voir script dans liste_stagiaires.html) :
    # on ne renvoie que le fragment de résultats, sans recharger toute la page.
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render(request, 'appStage/_resultats_stagiaires.html', context)

    return render(request, 'appStage/liste_stagiaires.html', context)


@role_required(User.Role.RH)
def exporter_stagiaires_csv(request):
    """Export CSV de la liste Stagiaires, respecte la recherche/le filtre de statut en cours."""
    stages, _, _ = _stages_filtres(request)
    lignes = [
        [
            stage.stagiaire.user.get_full_name(), stage.stagiaire.user.email,
            stage.intitule_poste, stage.departement.nom if stage.departement else 'Non affecté',
            stage.maitre_de_stage.user.get_full_name() if stage.maitre_de_stage else '',
            stage.get_statut_display(),
            stage.date_debut.strftime('%d/%m/%Y') if stage.date_debut else '',
            stage.date_fin.strftime('%d/%m/%Y') if stage.date_fin else '',
        ]
        for stage in stages
    ]
    return _reponse_csv(
        'stagiaires.csv',
        ['Nom complet', 'E-mail', 'Poste', 'Service', 'Maître de stage', 'Statut', 'Date de début', 'Date de fin'],
        lignes,
    )


@role_required(User.Role.RH)
def affecter_service(request):
    """
    Page dédiée à l'affectation des stagiaires à un service. Depuis
    l'acceptation d'une candidature, le stage est créé sans service : c'est
    ici, et uniquement ici, que le RH lui en choisit un (première
    affectation) ou en change (réaffectation), ce qui redémarre le
    processus d'encadrement : le maître de stage éventuel est désassigné et
    le nouveau directeur de service est notifié pour en choisir un.
    """
    Stage.synchroniser_statuts()
    stages = Stage.objects.select_related('stagiaire__user', 'departement', 'maitre_de_stage__user') \
        .exclude(statut=Stage.Statut.RESILIE) \
        .annotate(
            _a_affecter=Case(
                When(departement__isnull=True, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        ) \
        .order_by('_a_affecter', '-date_debut')

    recherche = request.GET.get('q', '').strip()
    if recherche:
        stages = stages.filter(
            Q(stagiaire__user__first_name__icontains=recherche) |
            Q(stagiaire__user__last_name__icontains=recherche) |
            Q(departement__nom__icontains=recherche)
        )

    if request.method == 'POST':
        form = AffecterServiceForm(request.POST)
        if form.is_valid():
            stage = get_object_or_404(Stage.objects.select_related('departement', 'stagiaire__user'), pk=form.cleaned_data['stage_id'])
            nouveau_departement = form.cleaned_data['departement']
            premiere_affectation = stage.departement_id is None
            if not premiere_affectation and nouveau_departement.id == stage.departement_id:
                messages.info(request, f"{stage.stagiaire.user.get_full_name()} est déjà affecté(e) à ce service.")
            else:
                ancien_maitre_de_stage = stage.maitre_de_stage
                stage.departement = nouveau_departement
                stage.maitre_de_stage = None
                stage.save(update_fields=['departement', 'maitre_de_stage'])
                stage.demandes_encadrement.filter(statut=DemandeEncadrement.Statut.EN_ATTENTE).update(
                    statut=DemandeEncadrement.Statut.REFUSEE, date_reponse=timezone.now(),
                )
                # Garde la candidature d'origine (utilisée en export CSV / admin)
                # synchronisée avec le service réellement attribué.
                candidature_origine = getattr(stage.stagiaire, 'candidature_origine', None)
                if candidature_origine:
                    candidature_origine.departement_affecte = nouveau_departement
                    candidature_origine.save(update_fields=['departement_affecte'])
                stage.notifier_directeur_affectation()
                if premiere_affectation:
                    message = f"{stage.stagiaire.user.get_full_name()} affecté(e) au service {nouveau_departement.nom}."
                else:
                    message = f"{stage.stagiaire.user.get_full_name()} affecté(e) au service {nouveau_departement.nom}."
                    if ancien_maitre_de_stage:
                        message += " Son ancien maître de stage a été désassigné : le nouveau directeur doit en choisir un autre."
                messages.success(request, message)
            return redirect(f"{reverse('appStage:affecter_service')}?maj={stage.id}")
        messages.error(request, "Formulaire invalide, réessayez.")

    total_stagiaires = stages.count()
    try:
        limite = max(10, int(request.GET.get('limite', 10)))
    except (TypeError, ValueError):
        limite = 10

    context = {
        'stages': stages[:limite],
        'recherche': recherche,
        'limite': limite,
        'total_stagiaires': total_stagiaires,
        'restants': max(0, total_stagiaires - limite),
        'departements': Departement.objects.all(),
        'stage_maj': request.GET.get('maj', ''),
    }

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render(request, 'appStage/_resultats_affecter_service.html', context)

    return render(request, 'appStage/affecter_service.html', context)


@role_required(User.Role.RH)
def candidatures(request):
    # Les candidatures pas encore traitées remontent toujours en premier
    # (ce sont elles qui demandent une action), les autres suivent par
    # date de soumission décroissante.
    qs = Candidature.objects.select_related('departement_affecte', 'traite_par__user') \
        .annotate(
            deja_traitee=Case(
                When(statut=Candidature.Statut.EN_ATTENTE, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        ).order_by('deja_traitee', '-date_soumission')
    return render(request, 'appStage/candidatures.html', {
        'candidatures': qs,
    })


@role_required(User.Role.RH)
def exporter_candidatures_csv(request):
    candidats = Candidature.objects.select_related('departement_affecte').order_by('-date_soumission')
    lignes = [
        [
            c.nom_complet, c.email, c.telephone, c.filiere, c.get_statut_display(),
            c.departement_affecte.nom if c.departement_affecte else '',
            c.date_soumission.strftime('%d/%m/%Y %H:%M') if c.date_soumission else '',
        ]
        for c in candidats
    ]
    return _reponse_csv(
        'candidatures.csv',
        ['Nom complet', 'E-mail', 'Téléphone', 'Filière', 'Statut', 'Service affecté', 'Date de soumission'],
        lignes,
    )


@require_POST
@role_required(User.Role.RH)
def accepter_candidature(request, candidature_id):
    """
    Première étape de l'acceptation : programme un entretien et prévient le
    candidat par email. La période de stage n'est plus demandée ici, elle
    se renseigne ensuite sur la page Planification, une fois l'entretien
    passé (voir planifier_stages).
    """
    candidature = get_object_or_404(Candidature, pk=candidature_id, statut=Candidature.Statut.EN_ATTENTE)
    form = ProgrammerEntretienForm(request.POST)
    if form.is_valid():
        candidature.programmer_entretien(
            traite_par=request.user.profil_rh,
            date_entretien=form.cleaned_data['date_entretien'],
            avec_soutenance=form.cleaned_data['avec_soutenance'],
        )
        messages.success(
            request,
            f"Candidature de {candidature.nom_complet} acceptée, entretien programmé et email envoyé.",
        )
    else:
        messages.error(request, "Formulaire invalide : " + " ".join(
            f"{champ} : {', '.join(erreurs)}" for champ, erreurs in form.errors.items()
        ))
    return redirect('appStage:candidatures')


@require_POST
@role_required(User.Role.RH)
def refuser_candidature(request, candidature_id):
    candidature = get_object_or_404(
        Candidature, pk=candidature_id,
        statut__in=[Candidature.Statut.EN_ATTENTE, Candidature.Statut.ENTRETIEN],
    )
    form = RefuserCandidatureForm(request.POST)
    if form.is_valid():
        candidature.refuser(form.cleaned_data['motif'], request.user.profil_rh)
        messages.success(request, f"Candidature de {candidature.nom_complet} refusée.")
    else:
        messages.error(request, "Le motif de refus est obligatoire.")
    return redirect('appStage:candidatures')


@role_required(User.Role.RH)
def planifier_stages(request):
    """
    Espace dédié du RH pour renseigner la période de stage des candidats
    dont l'entretien a été programmé. C'est cette étape qui crée
    effectivement le compte du stagiaire et son stage.
    """
    candidatures_qs = Candidature.objects.filter(statut=Candidature.Statut.ENTRETIEN) \
        .order_by('date_entretien', '-date_soumission')
    return render(request, 'appStage/planifier_stages.html', {
        'candidatures': candidatures_qs,
    })


@require_POST
@role_required(User.Role.RH)
def finaliser_stage_candidature(request, candidature_id):
    candidature = get_object_or_404(Candidature, pk=candidature_id, statut=Candidature.Statut.ENTRETIEN)
    form = PlanifierStageForm(request.POST)
    if form.is_valid():
        _, _, lien_activation = candidature.finaliser_stage(
            date_debut=form.cleaned_data['date_debut'],
            date_fin=form.cleaned_data['date_fin'],
        )
        if not settings.EMAIL_REELLEMENT_CONFIGURE:
            # Filet de sécurité tant qu'aucun SMTP réel n'est configuré : le
            # lien s'affiche directement dans l'UI, pas besoin de dépendre du
            # terminal où tourne runserver pour voir l'email envoyé. Dès que
            # EMAIL_HOST est défini, un vrai email part et ce filet disparaît.
            #
            # IMPORTANT : nom_complet vient d'un formulaire PUBLIC (saisie
            # non fiable), on l'échappe explicitement avant de l'insérer
            # dans du HTML marqué safe, pour éviter toute injection XSS.
            from django.utils.html import escape
            nom_echappe = escape(candidature.nom_complet)
            messages.success(
                request,
                mark_safe(
                    f"Stage de {nom_echappe} confirmé, compte créé. "
                    f"<strong>Lien d'activation (aucun SMTP configuré pour l'instant) :</strong> "
                    f"<a href=\"{lien_activation}\">{lien_activation}</a>"
                ),
            )
        else:
            messages.success(request, f"Stage de {candidature.nom_complet} confirmé, email envoyé.")
    else:
        messages.error(request, "Formulaire invalide : " + " ".join(
            f"{champ} : {', '.join(erreurs)}" for champ, erreurs in form.errors.items()
        ))
    return redirect('appStage:planifier_stages')


@require_POST
@role_required(User.Role.RH)
def supprimer_candidature(request, candidature_id):
    """
    Supprime définitivement une candidature déjà traitée (acceptée ou refusée),
    utile pour nettoyer les doublons de test. Le compte stagiaire éventuellement
    créé lors de l'acceptation n'est PAS supprimé (le lien est simplement détaché).
    """
    candidature = get_object_or_404(
        Candidature, pk=candidature_id, statut__in=[Candidature.Statut.ACCEPTEE, Candidature.Statut.REFUSEE]
    )
    nom = candidature.nom_complet
    candidature.delete()
    messages.success(request, f"Candidature de {nom} supprimée.")
    return redirect('appStage:candidatures')


# =========================================================
# Espace Maître de Stage
# =========================================================

@role_required(User.Role.MAITRE_STAGE)
def dashboard_tuteur(request):
    Stage.synchroniser_statuts()
    profil = request.user.profil_maitre_stage
    aujourdhui = timezone.now().date()

    stages_encadres = Stage.objects.filter(maitre_de_stage=profil).filter(
        Q(statut=Stage.Statut.EN_COURS) |
        Q(statut=Stage.Statut.TERMINE, date_fin__gte=aujourdhui - datetime.timedelta(days=3))
    ).select_related('stagiaire__user').order_by('statut', '-date_debut')

    rapports_a_valider = RapportHebdomadaire.objects.filter(
        stage__maitre_de_stage=profil, statut=RapportHebdomadaire.Statut.EN_ATTENTE
    ).select_related('stage__stagiaire__user').order_by('-date_soumission')

    demandes_en_attente = DemandeEncadrement.objects.filter(
        maitre_de_stage_demande=profil, statut=DemandeEncadrement.Statut.EN_ATTENTE
    ).select_related('stage__stagiaire__user')

    fin_de_periode = stages_encadres.filter(
        date_fin__lte=aujourdhui + datetime.timedelta(days=30), avec_soutenance=True
    ).exclude(evaluations__type_evaluation=Evaluation.TypeEvaluation.FINALE).first()

    # Présences en attente de confirmation, groupées par stagiaire (un seul
    # geste hebdomadaire plutôt qu'une ligne par jour dans le "À faire").
    presences_a_confirmer = []
    for stage in stages_encadres:
        stage.synchroniser_presences()
        nb = stage.presences.filter(valide_par_tuteur=False).count()
        if nb:
            presences_a_confirmer.append({'stage': stage, 'nb': nb})

    # Répartition par filière pour le petit graphique en anneau du tableau de bord.
    compteur_filieres = Counter(
        (stage.stagiaire.filiere or 'Non renseignée').strip().title() or 'Non renseignée'
        for stage in stages_encadres
    )
    paires_filieres = compteur_filieres.most_common(4)
    reste = sum(compteur_filieres.values()) - sum(c for _, c in paires_filieres)
    if reste > 0:
        paires_filieres.append(('Autres', reste))
    stats_filieres = _repartition_donut(paires_filieres)

    context = {
        'stages_encadres': stages_encadres,
        'rapports_a_valider': rapports_a_valider[:4],
        'demandes_en_attente': demandes_en_attente,
        'presences_a_confirmer': presences_a_confirmer,
        'nb_a_valider': rapports_a_valider.count() + demandes_en_attente.count() + len(presences_a_confirmer),
        'fin_de_periode': fin_de_periode,
        'stats_filieres': stats_filieres,
    }
    return render(request, 'appStage/dashboard_tuteur.html', context)


@role_required(User.Role.MAITRE_STAGE)
def documents_recus(request):
    profil = request.user.profil_maitre_stage
    stages = Stage.objects.filter(maitre_de_stage=profil) \
        .select_related('stagiaire__user') \
        .prefetch_related('documents') \
        .order_by('-date_debut')

    # Uniquement les documents que le stagiaire a explicitement adressés au
    # tuteur (les conventions/contrats déposés par le RH, ou les documents
    # adressés au RH, n'ont pas leur place ici).
    stages_avec_docs = []
    for stage in stages:
        docs = [d for d in stage.documents.all() if d.destinataire == DocumentStage.Destinataire.TUTEUR]
        stages_avec_docs.append({'stage': stage, 'documents': docs})

    return render(request, 'appStage/documents_recus.html', {'stages_avec_docs': stages_avec_docs})


@role_required(User.Role.RH)
def documents_recus_rh(request):
    """
    Vue globale (tous stagiaires confondus) des documents adressés au RH,
    plus un second bloc listant ce que le RH a lui-même envoyé aux
    stagiaires (conventions, contrats...).
    """
    type_filtre = request.GET.get('type', '')

    stages = Stage.objects.select_related('stagiaire__user', 'departement') \
        .prefetch_related('documents').order_by('-date_debut')

    stages_avec_docs = []
    stages_avec_envois = []
    total_documents = 0
    total_en_attente_signature = 0
    for stage in stages:
        tous_docs = list(stage.documents.all())
        recus = [d for d in tous_docs if d.destinataire == DocumentStage.Destinataire.RH]
        envoyes = [d for d in tous_docs if d.destinataire == DocumentStage.Destinataire.STAGIAIRE]

        total_documents += len(recus)
        # "En attente de signature" ne doit compter que ce qui concerne le RH :
        # les documents qu'il a lui-même envoyés (conventions/contrats) et qui
        # attendent la signature du stagiaire, pas les documents adressés au tuteur.
        total_en_attente_signature += sum(
            1 for d in envoyes if d.statut_signature == DocumentStage.StatutSignature.EN_ATTENTE
        )

        docs_filtres = [d for d in recus if d.type_document == type_filtre] if type_filtre else recus
        stages_avec_docs.append({'stage': stage, 'documents': docs_filtres})
        if envoyes:
            stages_avec_envois.append({'stage': stage, 'documents': envoyes})

    return render(request, 'appStage/documents_recus_rh.html', {
        'stages_avec_docs': stages_avec_docs,
        'stages_avec_envois': stages_avec_envois,
        'type_filtre': type_filtre,
        'total_documents': total_documents,
        'total_en_attente_signature': total_en_attente_signature,
        'documents_trouves': any(entry['documents'] for entry in stages_avec_docs),
    })


@role_required(User.Role.RH)
def envoyer_document_rh(request, stage_id):
    """Le RH envoie un document administratif (convention, contrat...) à un stagiaire."""
    stage = get_object_or_404(Stage.objects.select_related('stagiaire__user'), pk=stage_id)

    if request.method == 'POST':
        form = EnvoyerDocumentRHForm(request.POST, request.FILES)
        if form.is_valid():
            doc = form.save(commit=False)
            doc.stage = stage
            doc.destinataire = DocumentStage.Destinataire.STAGIAIRE
            doc.ajoute_par = request.user
            if doc.type_document in (DocumentStage.TypeDocument.CONVENTION, DocumentStage.TypeDocument.CONTRAT):
                doc.statut_signature = DocumentStage.StatutSignature.EN_ATTENTE
            doc.save()
            messages.success(
                request, f"Document « {doc.nom} » envoyé à {stage.stagiaire.user.get_full_name()}.",
            )
            return redirect('appStage:documents_recus_rh')
    else:
        form = EnvoyerDocumentRHForm()

    return render(request, 'appStage/envoyer_document_rh.html', {'form': form, 'stage': stage})


@role_required(User.Role.RH)
def gestion_tuteurs(request):
    """Vue d'ensemble RH de tous les tuteurs (maîtres de stage), avec création directe."""
    if request.method == 'POST':
        form = CreerTuteurForm(request.POST)
        if form.is_valid():
            try:
                ProfilMaitreStage.creer_et_inviter(
                    nom_complet=form.cleaned_data['nom_complet'],
                    email=form.cleaned_data['email'],
                    poste=form.cleaned_data['poste'],
                    departement_affiliation=form.cleaned_data['departement_affiliation'],
                )
            except IntegrityError as e:
                detail = f" Détail technique : {e}" if settings.DEBUG else ""
                form.add_error(
                    None,
                    "Impossible de créer ce compte à cause d'un conflit en base de données. "
                    "Réessayez ; si le problème persiste, contactez la personne qui gère le serveur."
                    + detail,
                )
            except Exception:
                form.add_error(
                    None,
                    "Le compte n'a pas pu être créé (l'e-mail d'invitation n'a probablement pas pu être envoyé). "
                    "Vérifiez la configuration d'envoi d'e-mails et réessayez.",
                )
            else:
                messages.success(
                    request,
                    f"Compte tuteur créé pour {form.cleaned_data['nom_complet']}. "
                    f"Un e-mail d'activation lui a été envoyé.",
                )
                return redirect('appStage:gestion_tuteurs')
    else:
        form = CreerTuteurForm()

    tuteurs = ProfilMaitreStage.objects.select_related('user') \
        .annotate(nb_en_cours=Count('stages_encadres', filter=Q(stages_encadres__statut=Stage.Statut.EN_COURS))) \
        .order_by('user__first_name', 'user__last_name')

    return render(request, 'appStage/gestion_tuteurs.html', {'form': form, 'tuteurs': tuteurs})


@role_required(User.Role.RH)
def exporter_tuteurs_csv(request):
    tuteurs = ProfilMaitreStage.objects.select_related('user') \
        .annotate(nb_en_cours=Count('stages_encadres', filter=Q(stages_encadres__statut=Stage.Statut.EN_COURS))) \
        .order_by('user__first_name', 'user__last_name')
    lignes = [
        [t.user.get_full_name(), t.user.email, t.poste, t.departement_affiliation, t.nb_en_cours]
        for t in tuteurs
    ]
    return _reponse_csv(
        'maitres_de_stage.csv',
        ['Nom complet', 'E-mail', 'Poste', 'Département affiliation', 'Stagiaires en cours'],
        lignes,
    )


@require_POST
@role_required(User.Role.RH)
def supprimer_tuteur(request, tuteur_id):
    """Supprime définitivement un compte tuteur. Ses stages encadrés sont automatiquement désassignés (non supprimés)."""
    tuteur = get_object_or_404(ProfilMaitreStage.objects.select_related('user'), pk=tuteur_id)
    nom = tuteur.user.get_full_name()
    tuteur.user.delete()  # cascade sur ProfilMaitreStage ; Stage.maitre_de_stage passe à NULL (SET_NULL)
    messages.success(request, f"Compte tuteur de {nom} supprimé.")
    return redirect('appStage:gestion_tuteurs')


@role_required(User.Role.RH)
def gestion_departements(request):
    """Vue d'ensemble RH de tous les services/départements, avec création directe."""
    if request.method == 'POST':
        form = CreerDepartementForm(request.POST)
        if form.is_valid():
            Departement.objects.create(nom=form.cleaned_data['nom'], agence=form.cleaned_data['agence'])
            messages.success(request, f"Service « {form.cleaned_data['nom']} » créé.")
            return redirect('appStage:gestion_departements')
    else:
        form = CreerDepartementForm()

    departements = Departement.objects.select_related('directeur__user').annotate(
        nb_stagiaires=Count('stages', filter=Q(stages__statut=Stage.Statut.EN_COURS))
    ).order_by('nom')

    return render(request, 'appStage/gestion_departements.html', {'form': form, 'departements': departements})


@role_required(User.Role.RH)
def exporter_departements_csv(request):
    departements = Departement.objects.select_related('directeur__user').annotate(
        nb_stagiaires=Count('stages', filter=Q(stages__statut=Stage.Statut.EN_COURS))
    ).order_by('nom')
    lignes = [
        [d.nom, d.agence, d.directeur.user.get_full_name() if d.directeur else '', d.nb_stagiaires]
        for d in departements
    ]
    return _reponse_csv(
        'services.csv',
        ['Nom du service', 'Agence', 'Directeur', 'Stagiaires en cours'],
        lignes,
    )


@require_POST
@role_required(User.Role.RH)
def supprimer_departement(request, departement_id):
    """Supprime un service, uniquement s'il n'a plus aucun stage rattaché (protection en base)."""
    departement = get_object_or_404(Departement, pk=departement_id)
    nom = departement.nom
    try:
        departement.delete()
    except ProtectedError:
        messages.error(
            request,
            f"Impossible de supprimer « {nom} » : des stagiaires y sont (ou y ont été) affectés. "
            f"Réaffectez-les d'abord à un autre service."
        )
    else:
        messages.success(request, f"Service « {nom} » supprimé.")
    return redirect('appStage:gestion_departements')


@role_required(User.Role.RH)
def gestion_directeurs(request):
    """Vue d'ensemble RH de tous les directeurs de service, avec création directe."""
    if request.method == 'POST':
        form = CreerDirecteurForm(request.POST)
        if form.is_valid():
            try:
                ProfilDirecteur.creer_et_inviter(
                    nom_complet=form.cleaned_data['nom_complet'],
                    email=form.cleaned_data['email'],
                    departement=form.cleaned_data['departement'],
                    poste=form.cleaned_data['poste'],
                )
            except IntegrityError as e:
                detail = f" Détail technique : {e}" if settings.DEBUG else ""
                form.add_error(
                    None,
                    "Impossible de créer ce compte à cause d'un conflit en base de données. "
                    "Réessayez ; si le problème persiste, contactez la personne qui gère le serveur."
                    + detail,
                )
            except Exception:
                form.add_error(
                    None,
                    "Le compte n'a pas pu être créé (l'e-mail d'invitation n'a probablement pas pu être envoyé). "
                    "Vérifiez la configuration d'envoi d'e-mails et réessayez.",
                )
            else:
                messages.success(
                    request,
                    f"Compte directeur créé pour {form.cleaned_data['nom_complet']}. "
                    f"Un e-mail d'activation lui a été envoyé.",
                )
                return redirect('appStage:gestion_directeurs')
    else:
        form = CreerDirecteurForm()

    directeurs = ProfilDirecteur.objects.select_related('user', 'departement').order_by(
        'user__first_name', 'user__last_name'
    )

    return render(request, 'appStage/gestion_directeurs.html', {'form': form, 'directeurs': directeurs})


@role_required(User.Role.RH)
def exporter_directeurs_csv(request):
    directeurs = ProfilDirecteur.objects.select_related('user', 'departement').order_by(
        'user__first_name', 'user__last_name'
    )
    lignes = [
        [d.user.get_full_name(), d.user.email, d.poste, d.departement.nom if d.departement else '']
        for d in directeurs
    ]
    return _reponse_csv(
        'directeurs.csv',
        ['Nom complet', 'E-mail', 'Poste', 'Service dirigé'],
        lignes,
    )


@require_POST
@role_required(User.Role.RH)
def supprimer_directeur(request, directeur_id):
    """Supprime définitivement un compte directeur. Le département concerné se retrouve sans directeur (SET_NULL)."""
    directeur = get_object_or_404(ProfilDirecteur.objects.select_related('user'), pk=directeur_id)
    nom = directeur.user.get_full_name()
    directeur.user.delete()  # cascade sur ProfilDirecteur ; Departement.directeur passe à NULL (SET_NULL)
    messages.success(request, f"Compte directeur de {nom} supprimé.")
    return redirect('appStage:gestion_directeurs')


@role_required(User.Role.MAITRE_STAGE)
def mes_stagiaires(request):
    profil = request.user.profil_maitre_stage
    stages = Stage.objects.filter(maitre_de_stage=profil) \
        .select_related('stagiaire__user', 'departement').order_by('-date_debut')
    return render(request, 'appStage/mes_stagiaires.html', {'stages': stages})


@role_required(User.Role.MAITRE_STAGE)
def assigner_mission(request):
    profil = request.user.profil_maitre_stage
    stages_encadres = Stage.objects.filter(maitre_de_stage=profil, statut=Stage.Statut.EN_COURS) \
        .select_related('stagiaire__user')

    if request.method == 'POST':
        form = AssignerMissionForm(request.POST, request.FILES)
        form.fields['stage'].queryset = stages_encadres
        if form.is_valid():
            mission = form.save()
            mission.notifier_stagiaire()
            messages.success(request, f"Mission « {mission.titre} » assignée à {mission.stage.stagiaire.user.get_full_name()}.")
            return redirect('appStage:assigner_mission')
    else:
        stage_id_prerempli = request.GET.get('stage')
        form = AssignerMissionForm(initial={'stage': stage_id_prerempli} if stage_id_prerempli else None)
        form.fields['stage'].queryset = stages_encadres

    return render(request, 'appStage/assigner_mission.html', {'form': form, 'stages_encadres': stages_encadres})


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
    Stage.synchroniser_statuts()
    stage = _get_stage_ou_403(request, stage_id)
    stage.synchroniser_presences()
    context = {
        'stage': stage,
        'missions': stage.missions.all(),
        'documents': stage.documents.all(),
        'presences': stage.presences.all()[:14],
        'presences_a_confirmer': stage.presences.filter(valide_par_tuteur=False).count(),
        'evaluations': stage.evaluations.all(),
        'peut_evaluer': request.user.role == User.Role.MAITRE_STAGE,
        'peut_envoyer_document': request.user.role == User.Role.RH,
        'peut_gerer_presence': (
            request.user.role == User.Role.MAITRE_STAGE
            and stage.maitre_de_stage_id and stage.maitre_de_stage.user_id == request.user.id
        ),
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
        # Suggestion intelligente : proche de la fin du stage -> Finale par défaut.
        type_suggere = (
            Evaluation.TypeEvaluation.FINALE if stage.semaines_restantes <= 2
            else Evaluation.TypeEvaluation.MI_PARCOURS
        )
        form = EvaluationForm(initial={'type_evaluation': type_suggere})

    eval_mi_parcours = stage.evaluations.filter(type_evaluation=Evaluation.TypeEvaluation.MI_PARCOURS).first()
    eval_finale = stage.evaluations.filter(type_evaluation=Evaluation.TypeEvaluation.FINALE).first()

    def _valeurs_evaluation(evaluation):
        if not evaluation:
            return None
        return {
            'note_technique': evaluation.note_technique,
            'note_autonomie': evaluation.note_autonomie,
            'note_communication': evaluation.note_communication,
            'note_ponctualite': evaluation.note_ponctualite,
            'commentaire': evaluation.commentaire,
            'note': str(evaluation.note),
            'date': evaluation.date_evaluation.strftime('%d %b %Y'),
        }

    # Permet au formulaire de recharger les notes d'une évaluation déjà
    # enregistrée quand on bascule sur Mi-parcours / Finale, au lieu
    # d'afficher un simple message statique inutile.
    evaluations_existantes = {
        'MI_PARCOURS': _valeurs_evaluation(eval_mi_parcours),
        'FINALE': _valeurs_evaluation(eval_finale),
    }

    return render(request, 'appStage/evaluer.html', {
        'stage': stage, 'form': form,
        'eval_mi_parcours': eval_mi_parcours, 'eval_finale': eval_finale,
        'evaluations_existantes': evaluations_existantes,
    })


@role_required(User.Role.MAITRE_STAGE)
def mes_affectations(request):
    """
    Page dédiée du maître de stage pour répondre aux propositions
    d'encadrement (affectations de stagiaires) : c'est ici, et non plus
    seulement dans le tableau de bord, qu'il accepte ou refuse, et c'est
    vers cette page que pointe désormais l'email reçu lors d'une nouvelle
    proposition.
    """
    profil = request.user.profil_maitre_stage

    demandes_en_attente = DemandeEncadrement.objects.filter(
        maitre_de_stage_demande=profil, statut=DemandeEncadrement.Statut.EN_ATTENTE,
    ).select_related('stage__stagiaire__user', 'stage__departement').order_by('-date_demande')

    historique = DemandeEncadrement.objects.filter(
        maitre_de_stage_demande=profil,
    ).exclude(statut=DemandeEncadrement.Statut.EN_ATTENTE) \
     .select_related('stage__stagiaire__user', 'stage__departement') \
     .order_by('-date_reponse')[:20]

    return render(request, 'appStage/mes_affectations.html', {
        'demandes_en_attente': demandes_en_attente,
        'historique': historique,
    })


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
        motif = request.POST.get('motif', '').strip()
        if not motif:
            messages.error(request, "Merci d'indiquer un motif de refus : il sera transmis au directeur.")
            return redirect('appStage:mes_affectations')
        demande.refuser(motif)
        messages.success(request, "Refus transmis au directeur.")
    return redirect('appStage:mes_affectations')


# =========================================================
# Portail Stagiaire
# =========================================================

@role_required(User.Role.STAGIAIRE)
def dashboard_stagiaire(request):
    profil = request.user.profil_stagiaire
    stage = profil.stage_actif

    context = {'stage': stage}

    if stage:
        stage.synchroniser_presences()
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


@require_POST
@role_required(User.Role.STAGIAIRE, User.Role.MAITRE_STAGE)
def signer_document(request, document_id):
    """
    Le destinataire réel d'un document (le stagiaire s'il lui est adressé,
    le tuteur si c'est lui) le marque comme signé. C'est la seule façon
    pour l'app de savoir qu'un accord/contrat envoyé a bien été traité,
    avant ça, "en attente de signature" ne changeait jamais tout seul.
    """
    doc = get_object_or_404(DocumentStage.objects.select_related('stage__stagiaire__user', 'stage__maitre_de_stage__user'), pk=document_id)
    stage = doc.stage

    est_destinataire = (
        (doc.destinataire == DocumentStage.Destinataire.STAGIAIRE and stage.stagiaire.user_id == request.user.id) or
        (doc.destinataire == DocumentStage.Destinataire.TUTEUR and stage.maitre_de_stage_id
         and stage.maitre_de_stage.user_id == request.user.id)
    )
    if not est_destinataire:
        raise PermissionDenied("Vous n'êtes pas destinataire de ce document.")

    if doc.statut_signature == DocumentStage.StatutSignature.EN_ATTENTE:
        doc.statut_signature = DocumentStage.StatutSignature.SIGNE
        doc.date_signature = timezone.now().date()
        doc.save(update_fields=['statut_signature', 'date_signature'])
        messages.success(request, f"Document « {doc.nom} » marqué comme signé.")

    page_retour = request.POST.get('next')
    if page_retour and url_has_allowed_host_and_scheme(page_retour, allowed_hosts={request.get_host()}):
        return redirect(page_retour)
    return redirect('appStage:mes_documents' if request.user.role == User.Role.STAGIAIRE else 'appStage:documents_recus')


@role_required(User.Role.STAGIAIRE)
def soumettre_document(request):
    stage = request.user.profil_stagiaire.stage_actif
    if not stage:
        messages.error(request, "Vous devez avoir un stage actif pour soumettre un document.")
        return redirect('appStage:mes_documents')

    if request.method == 'POST':
        form = SoumettreDocumentForm(request.POST, request.FILES, stage=stage)
        if form.is_valid():
            doc = form.save(commit=False)
            doc.stage = stage
            doc.destinataire = DocumentStage.Destinataire.TUTEUR
            doc.ajoute_par = request.user
            doc.save()
            doc.notifier_depot_stagiaire()

            if doc.mission and doc.mission.statut != Mission.Statut.TERMINEE:
                doc.mission.statut = Mission.Statut.TERMINEE
                doc.mission.save(update_fields=['statut'])
                messages.success(
                    request,
                    f"Document « {doc.nom} » déposé, la mission « {doc.mission.titre} » a été marquée terminée.",
                )
            else:
                messages.success(request, f"Document « {doc.nom} » déposé avec succès.")
            return redirect('appStage:mes_documents')
    else:
        mission_id_prerempli = request.GET.get('mission')
        form = SoumettreDocumentForm(stage=stage, initial={'mission': mission_id_prerempli} if mission_id_prerempli else None)

    return render(request, 'appStage/soumettre_document.html', {'form': form, 'stage': stage})


@role_required(User.Role.STAGIAIRE)
def modifier_document(request, document_id):
    """Permet au stagiaire de remplacer un document qu'il a lui-même envoyé (pas les documents émis par le RH)."""
    document = get_object_or_404(
        DocumentStage, pk=document_id, ajoute_par=request.user, stage__stagiaire=request.user.profil_stagiaire,
    )

    if request.method == 'POST':
        form = SoumettreDocumentForm(request.POST, request.FILES, instance=document, stage=document.stage)
        if form.is_valid():
            form.save()
            messages.success(request, f"Document « {document.nom} » mis à jour.")
            return redirect('appStage:mes_documents')
    else:
        form = SoumettreDocumentForm(instance=document, stage=document.stage)

    return render(request, 'appStage/soumettre_document.html', {
        'form': form, 'stage': document.stage, 'document': document,
    })


# =========================================================
# Espace Directeur de service
# =========================================================

@role_required(User.Role.DIRECTEUR)
def dashboard_directeur(request):
    Stage.synchroniser_statuts()
    profil = request.user.profil_directeur
    departement = getattr(profil, 'departement', None)

    if departement is None:
        return render(request, 'appStage/dashboard_directeur.html', {'departement': None})

    stages_service = Stage.objects.filter(departement=departement, statut=Stage.Statut.EN_COURS) \
        .select_related('stagiaire__user', 'maitre_de_stage__user')

    # Un stage "à venir" peut déjà se voir proposer un maître de stage à
    # l'avance (voir affecter_maitre_stage), donc le compte "à traiter" et
    # le bandeau d'alerte couvrent aussi bien les stages en cours que ceux
    # qui démarrent bientôt, pas seulement les stages déjà actifs.
    stages_sans_tuteur = Stage.objects.filter(
        departement=departement,
        statut__in=[Stage.Statut.A_VENIR, Stage.Statut.EN_COURS],
        maitre_de_stage__isnull=True,
    ).exclude(demandes_encadrement__statut=DemandeEncadrement.Statut.EN_ATTENTE)
    demandes_en_attente = DemandeEncadrement.objects.filter(
        stage__departement=departement, statut=DemandeEncadrement.Statut.EN_ATTENTE,
    ).select_related('stage__stagiaire__user', 'maitre_de_stage_demande__user')

    documents_recents = DocumentStage.objects.filter(
        stage__departement=departement, destinataire=DocumentStage.Destinataire.TUTEUR,
    ).select_related('stage__stagiaire__user').order_by('-date_ajout')[:5]

    nb_encadres = stages_service.filter(maitre_de_stage__isnull=False).count()
    nb_service_sans_tuteur = stages_service.filter(maitre_de_stage__isnull=True).exclude(
        demandes_encadrement__statut=DemandeEncadrement.Statut.EN_ATTENTE
    ).count()
    stats_encadrement = _repartition_donut(
        [('Avec maître de stage', nb_encadres), ('Sans maître de stage', nb_service_sans_tuteur)],
        palette=['#16a34a', '#f59e0b'],
    )

    context = {
        'departement': departement,
        'stages_service': stages_service,
        'stages_sans_tuteur': stages_sans_tuteur,
        'demandes_en_attente': demandes_en_attente,
        'documents_recents': documents_recents,
        'nb_a_traiter': stages_sans_tuteur.count(),
        'stats_encadrement': stats_encadrement,
    }
    return render(request, 'appStage/dashboard_directeur.html', context)


@role_required(User.Role.DIRECTEUR)
def affecter_maitre_stage(request):
    """
    Le directeur propose un maître de stage à un stagiaire de son service.
    L'affectation ne devient effective qu'après acceptation du tuteur
    (voir DemandeEncadrement.accepter, via repondre_demande_encadrement).
    """
    profil = request.user.profil_directeur
    departement = getattr(profil, 'departement', None)
    if departement is None:
        messages.error(request, "Vous n'êtes rattaché(e) à aucun département pour le moment.")
        return redirect('appStage:dashboard_directeur')

    # Un stage "à venir" est inclus, pas seulement "en cours" : le directeur
    # peut ainsi déjà préparer l'arrivée d'un stagiaire en lui choisissant un
    # maître de stage avant même la date de début (voir aussi le mail envoyé
    # par le RH lors de l'affectation au service, qui pointe vers cette page).
    stages_en_attente = Stage.objects.filter(
        departement=departement, statut__in=[Stage.Statut.A_VENIR, Stage.Statut.EN_COURS], maitre_de_stage__isnull=True,
    ).exclude(
        demandes_encadrement__statut=DemandeEncadrement.Statut.EN_ATTENTE
    ).select_related('stagiaire__user')

    if request.method == 'POST':
        form = AffecterMaitreStageForm(request.POST)
        if form.is_valid():
            stage = get_object_or_404(stages_en_attente, pk=form.cleaned_data['stage_id'])
            tuteur = form.cleaned_data['tuteur']
            demande = DemandeEncadrement.objects.create(
                stage=stage, maitre_de_stage_demande=tuteur, proposee_par=profil,
            )
            demande.notifier_tuteur()
            messages.success(
                request,
                f"Proposition envoyée à {tuteur.user.get_full_name()} pour encadrer "
                f"{stage.stagiaire.user.get_full_name()}.",
            )
            return redirect('appStage:affecter_maitre_stage')
        messages.error(request, "Formulaire invalide, réessayez.")

    demandes_en_cours = DemandeEncadrement.objects.filter(
        stage__departement=departement, statut=DemandeEncadrement.Statut.EN_ATTENTE,
    ).select_related('stage__stagiaire__user', 'maitre_de_stage_demande__user')

    tuteurs = ProfilMaitreStage.objects.select_related('user').all()

    return render(request, 'appStage/affecter_maitre_stage.html', {
        'stages_en_attente': stages_en_attente,
        'demandes_en_cours': demandes_en_cours,
        'tuteurs': tuteurs,
        'departement': departement,
    })


@role_required(User.Role.DIRECTEUR)
def documents_recus_directeur(request):
    """
    Page "Documents" du directeur : recherche d'un stagiaire de son service,
    puis accès (par stagiaire) aux documents qu'il a déposés ("Reçus") ou à
    ceux que le RH lui a envoyés, ex. contrat de travail ("Envoyés").
    """
    profil = request.user.profil_directeur
    departement = getattr(profil, 'departement', None)

    onglet = request.GET.get('onglet', 'recus')
    if onglet not in ('recus', 'envoyes'):
        onglet = 'recus'
    destinataire_cible = (
        DocumentStage.Destinataire.TUTEUR if onglet == 'recus' else DocumentStage.Destinataire.STAGIAIRE
    )

    stages = Stage.objects.filter(departement=departement) \
        .select_related('stagiaire__user') \
        .prefetch_related('documents') \
        .order_by('-date_debut') if departement else Stage.objects.none()

    recherche = request.GET.get('q', '').strip()
    if recherche:
        stages = stages.filter(
            Q(stagiaire__user__first_name__icontains=recherche) |
            Q(stagiaire__user__last_name__icontains=recherche)
        )

    stages_avec_docs = []
    for stage in stages:
        docs = sorted(
            (d for d in stage.documents.all() if d.destinataire == destinataire_cible),
            key=lambda d: d.date_ajout, reverse=True,
        )
        if docs:
            stages_avec_docs.append({'stage': stage, 'documents': docs})

    total_stagiaires = len(stages_avec_docs)
    try:
        limite = max(10, int(request.GET.get('limite', 10)))
    except (TypeError, ValueError):
        limite = 10

    context = {
        'stages_avec_docs': stages_avec_docs[:limite],
        'departement': departement,
        'onglet': onglet,
        'recherche': recherche,
        'limite': limite,
        'total_stagiaires': total_stagiaires,
        'restants': max(0, total_stagiaires - limite),
    }

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render(request, 'appStage/_resultats_documents_directeur.html', context)

    return render(request, 'appStage/documents_recus_directeur.html', context)


@require_POST
@role_required(User.Role.STAGIAIRE)
def pointer_presence(request):
    """Auto-déclaration de présence du jour par le stagiaire (à confirmer ensuite par le tuteur)."""
    stage = request.user.profil_stagiaire.stage_actif
    if stage:
        note = request.POST.get('note_activite', '').strip()[:280]
        Presence.objects.get_or_create(
            stage=stage, date=timezone.now().date(),
            defaults={'present': True, 'note_activite': note},
        )
        messages.success(request, "Présence enregistrée pour aujourd'hui.")
    return redirect('appStage:dashboard_stagiaire')


def _presence_appartient_au_tuteur(request, presence):
    stage = presence.stage
    return stage.maitre_de_stage_id and stage.maitre_de_stage.user_id == request.user.id


@require_POST
@role_required(User.Role.MAITRE_STAGE)
def confirmer_presence(request, presence_id, action):
    """
    Le tuteur traite un jour auto-déclaré ou auto-marqué absent :
    - confirmer  : entérine tel quel (présent reste présent, absent reste absent)
    - contester  : le stagiaire avait pointé présent, mais ce n'était pas le cas
    - justifier  : le jour était marqué absent, mais l'absence est justifiée
    """
    presence = get_object_or_404(
        Presence.objects.select_related('stage__maitre_de_stage__user'), pk=presence_id
    )
    if not _presence_appartient_au_tuteur(request, presence):
        raise PermissionDenied("Vous n'encadrez pas ce stagiaire.")

    if action == 'contester':
        presence.present = False
        presence.justifie = False
    elif action == 'justifier':
        presence.justifie = True
    elif action != 'confirmer':
        raise Http404

    presence.valide_par_tuteur = True
    presence.save()
    messages.success(request, "Présence mise à jour.")
    return redirect(reverse('appStage:fiche_stagiaire', kwargs={'stage_id': presence.stage_id}) + '#presence')


@require_POST
@role_required(User.Role.MAITRE_STAGE)
def confirmer_semaine_presence(request, stage_id):
    """Confirme en un clic toutes les présences en attente d'un stagiaire, telles quelles."""
    stage = get_object_or_404(Stage.objects.select_related('maitre_de_stage__user'), pk=stage_id)
    if not stage.maitre_de_stage_id or stage.maitre_de_stage.user_id != request.user.id:
        raise PermissionDenied("Vous n'encadrez pas ce stagiaire.")

    nb = stage.presences.filter(valide_par_tuteur=False).update(valide_par_tuteur=True)
    if nb:
        messages.success(request, f"{nb} jour{'s' if nb > 1 else ''} de présence confirmé{'s' if nb > 1 else ''}.")
    return redirect(reverse('appStage:fiche_stagiaire', kwargs={'stage_id': stage.id}) + '#presence')


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
# Notifications (communes à tous les rôles)
# =========================================================

@require_POST
@role_required(User.Role.STAGIAIRE, User.Role.RH, User.Role.MAITRE_STAGE, User.Role.DIRECTEUR)
def marquer_notification_lue(request, notification_id):
    """Marque une notification comme lue, puis redirige vers sa cible (ou le dashboard à défaut)."""
    notification = get_object_or_404(Notification, pk=notification_id, destinataire=request.user)
    notification.lu = True
    notification.save(update_fields=['lu'])
    if notification.lien:
        return redirect(notification.lien)
    return redirect(request.user.get_dashboard_url_name())


@require_POST
@role_required(User.Role.STAGIAIRE, User.Role.RH, User.Role.MAITRE_STAGE, User.Role.DIRECTEUR)
def marquer_toutes_notifications_lues(request):
    request.user.notifications.filter(lu=False).update(lu=True)
    return redirect(request.POST.get('next') or request.user.get_dashboard_url_name())


# =========================================================
# Paramètres (commun aux 3 rôles)
# =========================================================

@role_required(User.Role.STAGIAIRE, User.Role.RH, User.Role.MAITRE_STAGE, User.Role.DIRECTEUR)
def parametres(request):
    onglet_actif = 'profil'
    if request.method == 'POST' and request.POST.get('form_type') == 'securite':
        onglet_actif = 'securite'
        securite_form = ChangerMotDePasseForm(request.user, request.POST)
        if securite_form.is_valid():
            from django.contrib.auth import update_session_auth_hash
            user = securite_form.save()
            update_session_auth_hash(request, user)  # évite d'être déconnecté après le changement
            messages.success(request, "Votre mot de passe a été mis à jour.")
            return redirect('appStage:parametres')
        profil_form = ParametresForm(instance=request.user)
    elif request.method == 'POST':
        profil_form = ParametresForm(request.POST, request.FILES, instance=request.user)
        securite_form = ChangerMotDePasseForm(request.user)
        if profil_form.is_valid():
            profil_form.save()
            messages.success(request, "Vos informations ont été mises à jour.")
            return redirect('appStage:parametres')
    else:
        profil_form = ParametresForm(instance=request.user)
        securite_form = ChangerMotDePasseForm(request.user)

    return render(request, 'appStage/parametres.html', {
        'form': profil_form, 'securite_form': securite_form, 'onglet_actif': onglet_actif,
    })
