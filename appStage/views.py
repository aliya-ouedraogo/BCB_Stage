import datetime

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied
from django.conf import settings
from django.db.models import Q
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
    AccepterCandidatureForm,
    AssignerMissionForm,
    CandidaturePubliqueForm,
    ChangerMotDePasseForm,
    EnvoyerDocumentRHForm,
    EvaluationForm,
    ParametresForm,
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
    Presence,
    ProfilMaitreStage,
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
def candidature_publique(request):
    """
    Formulaire public de dépôt de candidature — remplace l'ancienne
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
        form = SetPasswordForm(user, request.POST)
        if form.is_valid():
            form.save()
            login(request, user)
            messages.success(request, "Votre mot de passe est défini. Bienvenue sur BCBStageFlow !")
            return redirect(user.get_dashboard_url_name())
    else:
        form = SetPasswordForm(user)

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

    # --- Alertes de fin de période de stage ---
    stages_en_cours = Stage.objects.filter(statut=Stage.Statut.EN_COURS).select_related('stagiaire__user')
    stages_fin_proche = [s for s in stages_en_cours if s.se_termine_bientot]
    stages_periode_depassee = [s for s in stages_en_cours if s.periode_depassee]

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
        'filtre_statut': filtre_statut,
        'chart_data': chart_data,
        'annee_courante': aujourdhui.year,
    }
    return render(request, 'appStage/dashboard_rh.html', context)


@role_required(User.Role.RH)
def liste_stagiaires(request):
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

    return render(request, 'appStage/liste_stagiaires.html', {
        'stages': stages,
        'recherche': recherche,
        'filtre_statut': filtre_statut,
    })


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
        _, _, lien_activation = candidature.accepter(
            departement=form.cleaned_data['departement'],
            traite_par=request.user.profil_rh,
            date_debut=form.cleaned_data['date_debut'],
            date_fin=form.cleaned_data['date_fin'],
            avec_soutenance=form.cleaned_data['avec_soutenance'],
        )
        if not settings.EMAIL_REELLEMENT_CONFIGURE:
            # Filet de sécurité tant qu'aucun SMTP réel n'est configuré : le
            # lien s'affiche directement dans l'UI, pas besoin de dépendre du
            # terminal où tourne runserver pour voir l'email envoyé. Dès que
            # EMAIL_HOST est défini, un vrai email part et ce filet disparaît.
            #
            # IMPORTANT : nom_complet vient d'un formulaire PUBLIC (saisie
            # non fiable) — on l'échappe explicitement avant de l'insérer
            # dans du HTML marqué safe, pour éviter toute injection XSS.
            from django.utils.html import escape
            nom_echappe = escape(candidature.nom_complet)
            messages.success(
                request,
                mark_safe(
                    f"Candidature de {nom_echappe} acceptée, compte créé. "
                    f"<strong>Lien d'activation (aucun SMTP configuré pour l'instant)&nbsp;:</strong> "
                    f"<a href=\"{lien_activation}\">{lien_activation}</a>"
                ),
            )
        else:
            messages.success(request, f"Candidature de {candidature.nom_complet} acceptée, email envoyé.")
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
        # attendent la signature du stagiaire — pas les documents adressés au tuteur.
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
    stage = _get_stage_ou_403(request, stage_id)
    context = {
        'stage': stage,
        'missions': stage.missions.all(),
        'documents': stage.documents.all(),
        'presences': stage.presences.all()[:14],
        'evaluations': stage.evaluations.all(),
        'peut_evaluer': request.user.role == User.Role.MAITRE_STAGE,
        'peut_envoyer_document': request.user.role == User.Role.RH,
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


@require_POST
@role_required(User.Role.STAGIAIRE, User.Role.MAITRE_STAGE)
def signer_document(request, document_id):
    """
    Le destinataire réel d'un document (le stagiaire s'il lui est adressé,
    le tuteur si c'est lui) le marque comme signé. C'est la seule façon
    pour l'app de savoir qu'un accord/contrat envoyé a bien été traité —
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
            doc.ajoute_par = request.user
            doc.save()

            if doc.mission and doc.mission.statut != Mission.Statut.TERMINEE:
                doc.mission.statut = Mission.Statut.TERMINEE
                doc.mission.save(update_fields=['statut'])
                messages.success(
                    request,
                    f"Document « {doc.nom} » envoyé, la mission « {doc.mission.titre} » a été marquée terminée.",
                )
            else:
                destinataire_label = "au RH" if doc.destinataire == DocumentStage.Destinataire.RH else "à votre maître de stage"
                messages.success(request, f"Document « {doc.nom} » envoyé {destinataire_label}.")
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
    if request.method == 'POST' and request.POST.get('form_type') == 'securite':
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

    return render(request, 'appStage/parametres.html', {'form': profil_form, 'securite_form': securite_form})
